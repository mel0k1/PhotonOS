#!/usr/bin/env python3
"""Тесты логики установщика без Qt: парсер lsblk, план разметки, валидация.

Запуск: python3 scripts/installer_tests.py
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "installer"))

from photon_install import disk                      # noqa: E402
from photon_install.settings import (DE_OPTIONS,     # noqa: E402
                                     InstallSettings, valid_hostname,
                                     valid_login)

fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL") + " " + name)
    if not cond:
        fails.append(name)


disks = disk.parse_lsblk_json(disk.FAKE_LSBLK)
check("три диска из примера", len(disks) == 3)
sda = next(d for d in disks if d.name == "sda")
sdb = next(d for d in disks if d.name == "sdb")
nvme = next(d for d in disks if d.name == "nvme0n1")

check("sda: 2 раздела", len(sda.parts) == 2)
check("sda: есть данные", sda.has_data)
check("sdb: пуст", not sdb.has_data)
check("sdb: USB-флаг", sdb.removable)
check("nvme: 2 раздела ntfs", len(nvme.parts) == 2 and nvme.parts[0].fstype == "ntfs")
check("размеры в человекочитаемом виде", sda.size_h.endswith("ГиБ") and "238" in sda.size_h)
check("модель подтянута", "Samsung" in sda.model)

plan = disk.auto_plan(sda.size, swap=False)
check("план без swap: ESP+корень", len(plan) == 2)
check("ESP = 512 МиБ", plan[0]["size"] == 512 * disk.MIB)
check("корень = остаток", plan[1]["size"] == sda.size - 512 * disk.MIB)

plan_sw = disk.auto_plan(sda.size, swap=True)
check("план со swap: 3 раздела", len(plan_sw) == 3)
check("swap = 4 ГиБ", plan_sw[1]["size"] == 4 * disk.GIB)

plan_small = disk.auto_plan(8 * disk.GIB, swap=True)
check("на малом диске swap отпадает", len(plan_small) == 2 and plan_small[-1]["fs"] == "ext4")

check("логин ок", valid_login("anya"))
check("логин с цифрой в начале — нет", not valid_login("1anya"))
check("логин с заглавной — нет", not valid_login("Anya"))
check("hostname ок", valid_hostname("photon-pc"))
check("hostname с точкой — нет", not valid_hostname("ph.o ton".replace(" ", "")))

s = InstallSettings()
s.de = "macshell"
check("de_title для MacShell", s.de_title() == "MacShell")
check("все DE имеют бейджи", all("badge" in o and "desc" in o for o in DE_OPTIONS))
check("MacShell в списке", any(o["id"] == "macshell" for o in DE_OPTIONS))
check("LXQt по умолчанию", InstallSettings().de == "lxqt")

# ── M2: бэкенд установки (dry-run) ──────────────────────────────────
from photon_install.backend import (BASE_PKGS, DE_PKGS, Installer,  # noqa: E402
                                    part_path)

check("суффикс sda", part_path("sda", 3) == "/dev/sda3")
check("суффикс nvme", part_path("nvme0n1", 1) == "/dev/nvme0n1p1")
check("суффикс mmcblk", part_path("mmcblk0", 2) == "/dev/mmcblk0p2")

def build_settings(de, swap):
    s = InstallSettings(lang="ru")
    s.disks = disks
    s.disk = sda.path
    s.disk_size = sda.size_h
    s.swap = swap
    s.username, s.fullname = "anya", "Аня Волкова"
    s.password = "hunter2"
    s.hostname = "photon-pc"
    s.tz = "Europe/Moscow"
    s.de = de
    return s

def dry_run(s):
    lines = []
    inst = Installer(s, dry_run=True)
    inst.on_log = lines.append
    inst.run()
    return lines, inst

lines, inst = dry_run(build_settings("lxqt", True))
cmds = [l for l in lines if l.startswith(("[",) ) and "$ " in l]
plain = "\n".join(lines)
text_cmds = [l.split("$ ", 1)[1] for l in lines if "$ " in l]

check("sfdisk вызван на /dev/sda", any(c.startswith("sfdisk -f /dev/sda") for c in text_cmds))
check("sfdisk: gpt + ESP + swap + linux",
      all(x in plain for x in ("label: gpt", "type=U", "type=S", "type=L")))
check("mkfs.vfat на sda1", any(c.startswith("mkfs.vfat") and c.endswith("/dev/sda1")
                               for c in text_cmds))
check("swap на sda2", any(c.startswith("mkswap") and c.endswith("/dev/sda2")
                          for c in text_cmds))
check("корень на sda3", any(c.startswith("mkfs.ext4") and c.endswith("/dev/sda3")
                            for c in text_cmds))
check("xbps-install с набором LXQt",
      any(c.startswith("xbps-install -r /target -Sy") and "lxqt" in c and "sddm" in c
          for c in text_cmds))
check("grub-install UEFI", any("grub-install --target=x86_64-efi" in c for c in text_cmds))
check("grub-mkconfig", any("grub-mkconfig -o /boot/grub/grub.cfg" in c for c in text_cmds))
check("xbps-reconfigure linux-lts", any("xbps-reconfigure -fa linux-lts" in c for c in text_cmds))
check("umount -R /target", any(c == "umount -R /target" for c in text_cmds))
check("пользователь создан в chroot",
      any("useradd -m -s /bin/bash -G wheel,audio,video,storage,input,cdrom anya" in c
          for c in text_cmds))
check("пароли не попадают в журнал", "hunter2" not in plain)
check("stdin с паролями скрыт", any("пароли скрыты" in l for l in lines))

lines2, _ = dry_run(build_settings("none", False))
plain2 = "\n".join(lines2)
text2 = [l.split("$ ", 1)[1] for l in lines2 if "$ " in l]
check("без swap: корень сразу sda2", any(c.startswith("mkfs.ext4") and c.endswith("/dev/sda2")
                                         for c in text2))
check("без swap: нет mkswap", "mkswap" not in plain2)
check("без DE: нет sddm в пакетах",
      any(c.startswith("xbps-install") and "sddm" not in c and " lxqt" not in c
          for c in text2))
check("без DE: нет sddm-сервиса",
      any(c.startswith("ln -sf /etc/sv/") and c.endswith("/default/sddm")
          for c in text2) is False)

nvme_s = build_settings("lxqt", False)
nvme_s.disk = nvme.path
nvme_s.disks = disks
lines3, _ = dry_run(nvme_s)
text3 = [l.split("$ ", 1)[1] for l in lines3 if "$ " in l]
check("nvme: корень p2", any(c.startswith("mkfs.ext4") and c.endswith("/dev/nvme0n1p2")
                             for c in text3))
check("nvme: ESP p1", any(c.startswith("mkfs.vfat") and c.endswith("/dev/nvme0n1p1")
                          for c in text3))
check("macshell пока ставится как база (M3)",
      any(c.startswith("xbps-install") and "hyprland" not in c
          for c in [l.split("$ ", 1)[1] for l in
                    (lambda L: L)([x for x in lines2]) if "$ " in l]))

print()
print("ВСЕ ОК" if not fails else f"ПРОВАЛЕНО: {fails}")
sys.exit(1 if fails else 0)
