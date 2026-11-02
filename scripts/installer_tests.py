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

print()
print("ВСЕ ОК" if not fails else f"ПРОВАЛЕНО: {fails}")
sys.exit(1 if fails else 0)
