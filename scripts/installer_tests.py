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
s.de = "lxqt"
check("de_title для LXQt", s.de_title() == "LXQt")
check("все DE имеют бейджи", all("badge" in o and "desc" in o for o in DE_OPTIONS))
check("MacShell убран из списка (отменён)",
      all(o["id"] != "macshell" for o in DE_OPTIONS))
check("LXQt по умолчанию", InstallSettings().de == "lxqt")
check("дефолтный lang=ru", InstallSettings().lang == "ru")

# ── бэкенд установки (Debian-порт, dry-run) ─────────────────────────
from photon_install.backend import (COPY_EXCLUDES, PURGE_PKGS,  # noqa: E402
                                    Installer, find_squashfs, part_path)

check("суффикс sda", part_path("sda", 3) == "/dev/sda3")
check("суффикс nvme", part_path("nvme0n1", 1) == "/dev/nvme0n1p1")
check("суффикс mmcblk", part_path("mmcblk0", 2) == "/dev/mmcblk0p2")

check("purge: live-boot и live-config",
      "live-boot" in PURGE_PKGS and "live-config" in PURGE_PKGS)
check("excludes: machine-id и fstab из squashfs не копируются",
      "./etc/machine-id" in COPY_EXCLUDES and "./etc/fstab" in COPY_EXCLUDES)
check("excludes: псевдо-ФС не копируются",
      all(x in COPY_EXCLUDES for x in ("./proc", "./sys", "./dev", "./run")))
check("find_squashfs вне live вернёт None", find_squashfs() is None)


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
check("squashfs смонтирован loop,ro",
      any(c.startswith("mount -o loop,ro") and "filesystem.squashfs" in c
          for c in text_cmds))
check("purge live-пакетов в chroot",
      any(c.startswith("chroot /target dpkg --purge") and "live-boot" in c
          for c in text_cmds))
check("grub-install UEFI", any("grub-install --target=x86_64-efi" in c for c in text_cmds))
check("grub-mkconfig", any("grub-mkconfig -o /boot/grub/grub.cfg" in c for c in text_cmds))
check("шаг initramfs есть (call-операция)",
      any(key == "kernel" for key, _t, _o in inst.steps))
check("umount -R /target", any(c == "umount -R /target" for c in text_cmds))
check("пользователь создан в chroot (группа sudo)",
      any("useradd -m -s /bin/bash -G sudo,audio,video,storage,input,cdrom,netdev anya" in c
          for c in text_cmds))
check("пароли не попадают в журнал", "hunter2" not in plain)
check("stdin с паролями скрыт", any("пароли скрыты" in l for l in lines))
check("12 шагов установки", len(inst.steps) == 12)

lines2, _ = dry_run(build_settings("none", False))
plain2 = "\n".join(lines2)
text2 = [l.split("$ ", 1)[1] for l in lines2 if "$ " in l]
check("без swap: корень сразу sda2", any(c.startswith("mkfs.ext4") and c.endswith("/dev/sda2")
                                         for c in text2))
check("без swap: нет mkswap", "mkswap" not in plain2)
check("окружение не влияет на копию squashfs (одна система)",
      len([c for c in text2 if c.startswith("mount -o loop,ro")]) == 1)

lines_none, inst_none = dry_run(build_settings("none", False))
ops_clean = [o for k, _t, os_ in inst_none.steps if k == "clean" for o in os_]
check("без DE: бэкенд добавляет очистку десктоп-стека",
      any(getattr(o[1], "__name__", "") == "_purge_desktop"
          for o in ops_clean if o[0] == "call"))
lines_lxqt, inst_lxqt = dry_run(build_settings("lxqt", True))
ops_clean_l = [o for k, _t, os_ in inst_lxqt.steps if k == "clean" for o in os_]
check("с LXQt десктоп не снимается",
      not any(getattr(o[1], "__name__", "") == "_purge_desktop"
              for o in ops_clean_l if o[0] == "call"))

nvme_s = build_settings("lxqt", False)
nvme_s.disk = nvme.path
nvme_s.disks = disks
lines3, _ = dry_run(nvme_s)
text3 = [l.split("$ ", 1)[1] for l in lines3 if "$ " in l]
check("nvme: корень p2", any(c.startswith("mkfs.ext4") and c.endswith("/dev/nvme0n1p2")
                             for c in text3))
check("nvme: ESP p1", any(c.startswith("mkfs.vfat") and c.endswith("/dev/nvme0n1p1")
                          for c in text3))

print()
print("ВСЕ ОК" if not fails else f"ПРОВАЛЕНО: {fails}")
sys.exit(1 if fails else 0)
