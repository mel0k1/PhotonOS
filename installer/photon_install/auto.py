"""Автоустановка PhotonOS: photon-auto.conf с live-носителя, без GUI.

Ключи: DISK (обязателен), USERNAME, PASSWORD, FULLNAME, HOSTNAME, TZ,
LOCALE (ru|en), LAYOUT, VARIANT, SWAP, DE (lxqt|none), MAIL, REBOOT.
Пароль лежит в конфиге открытым текстом - файл на носителе админа.
"""
from __future__ import annotations

import os
import subprocess
import sys

from . import disk
from .backend import BackendError, Installer
from .settings import _TRUE, auto_settings, parse_auto_conf, validate_auto

AUTO_CANDIDATES = [
    "/run/live/medium/photon-auto.conf",
    "/lib/live/mount/medium/photon-auto.conf",
]


def run_auto(explicit: str = "") -> int:
    path = explicit
    if not path:
        path = next((c for c in AUTO_CANDIDATES if os.path.isfile(c)), "")
        if not path:
            print("автоустановка: photon-auto.conf не найден "
                  f"({' , '.join(AUTO_CANDIDATES)})", file=sys.stderr)
            return 2
    try:
        with open(path, encoding="utf-8") as f:
            kv = parse_auto_conf(f.read())
    except (OSError, ValueError) as e:
        print(f"автоустановка: {e}", file=sys.stderr)
        return 2

    s = auto_settings(kv)
    if err := validate_auto(s):
        print(f"автоустановка: {err}", file=sys.stderr)
        return 2

    # бэкенд сверяет settings.disk с опросом; здесь - автоподстановка
    s.disks = disk.list_disks()
    if not next((d for d in s.disks if d.path == s.disk), None):
        known = ", ".join(d.path for d in s.disks) or "нет дисков"
        print(f"автоустановка: диск {s.disk} не найден ({known})",
              file=sys.stderr)
        return 2

    print(f"автоустановка: {s.disk} ({s.disk_size}), "
          f"пользователь {s.username}, {s.de_title()}, "
          f"swap={'да' if s.swap else 'нет'}")
    try:
        Installer(s, on_log=print).run()
    except BackendError as e:
        print(f"автоустановка: {e}", file=sys.stderr)
        return 3
    print("готово.")
    if kv.get("REBOOT", "yes").lower() in _TRUE:
        print("перезагрузка...")
        subprocess.run(["reboot"])
    return 0
