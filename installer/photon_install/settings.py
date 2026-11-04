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
