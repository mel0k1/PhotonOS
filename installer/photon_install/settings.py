"""Конфигурация установки и варианты окружения рабочего стола."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LOGIN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
HOST_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$")


# Варианты DE. available=False — выбор виден, но помечен бейджем;
# бэкенд-реализация появляется по мере вех (см. docs/INSTALLER.md).
DE_OPTIONS = [
    {
        "id": "lxqt",
        "title": "LXQt",
        "badge": "de_badge_default",
        "desc": "Фирменный вариант PhotonOS: лёгкий, в духе Deepin — тема "
                "Onyxian-Rounded, док снизу.",
        "available": True,
    },
    {
        "id": "none",
        "title": "Без окружения",
        "badge": "de_badge_min",
        "desc": "Базовая система с сетью и терминалом; графику поставите сами.",
        "available": True,
    },
    {
        "id": "xfce",
        "title": "XFCE",
        "badge": "de_badge_soon",
        "desc": "Классический лёгкий десктоп.",
        "available": False,
    },
    {
        "id": "kde",
        "title": "KDE Plasma",
        "badge": "de_badge_soon",
        "desc": "Полноценный десктоп с эффектами.",
        "available": False,
    },
    {
        "id": "gnome",
        "title": "GNOME",
        "badge": "de_badge_soon",
        "desc": "Строгий десктоп с фокусом на рабочие пространства.",
        "available": False,
    },
]


@dataclass
class InstallSettings:
    lang: str = "ru"
    tz: str = ""
    layout: str = "us"
    variant: str = ""
    disk: str = ""          # /dev/sda
    disk_size: str = ""
    swap: bool = False
    fullname: str = ""
    username: str = ""
    password: str = ""
    hostname: str = ""
    de: str = "lxqt"
    mail: bool = True       # Claws Mail входит в образ; галочка снимает его при установке
    disks: list = field(default_factory=list)   # кэш опроса для сводки

    def de_title(self) -> str:
        for opt in DE_OPTIONS:
            if opt["id"] == self.de:
                return opt["title"]
        return self.de


def valid_login(s: str) -> bool:
    return bool(LOGIN_RE.match(s))


def valid_hostname(s: str) -> bool:
    return bool(HOST_RE.match(s))


# ── автоустановка: photon-auto.conf на live-носителе ────────────────────

_TRUE = ("yes", "true", "1", "y")


def parse_auto_conf(text: str) -> dict:
    """KEY=VALUE построчно; '#' - комментарий. Ключи верхним регистром."""
    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"строка без '=': {line!r}")
        k, v = (x.strip() for x in line.split("=", 1))
        if not k:
            raise ValueError("пустой ключ")
        kv[k.upper()] = v
    return kv


def auto_settings(kv: dict) -> InstallSettings:
    s = InstallSettings()
    if kv.get("LOCALE") in ("ru", "en"):
        s.lang = kv["LOCALE"]
    s.tz = kv.get("TZ", "")
    s.layout = kv.get("LAYOUT", "us")
    s.variant = kv.get("VARIANT", "")
    s.disk = kv.get("DISK", "")
    s.swap = kv.get("SWAP", "no").lower() in _TRUE
    s.fullname = kv.get("FULLNAME", "")
    s.username = kv.get("USERNAME", "")
    s.password = kv.get("PASSWORD", "")
    s.hostname = kv.get("HOSTNAME", "photon")
    if kv.get("DE") in ("lxqt", "none"):
        s.de = kv["DE"]
    s.mail = kv.get("MAIL", "yes").lower() in _TRUE
    return s


def validate_auto(s: InstallSettings) -> str:
    """'' или текст ошибки (для serial/TTY - только печатный вывод)."""
    if not s.disk:
        return "DISK не задан (например DISK=/dev/sda)"
    if not s.username:
        return "USERNAME не задан"
    if not valid_login(s.username):
        return f"USERNAME некорректен: {s.username}"
    if len(s.password) < 6:
        return "PASSWORD короче 6 символов"
    if not valid_hostname(s.hostname):
        return f"HOSTNAME некорректен: {s.hostname}"
    return ""
