#!/usr/bin/env python3
"""Иконка меню PhotonOS: чёрный квадрат с двумя белыми глазками-квадратиками.

Генерирует start-here-photon.png во всех нужных размерах темы photon
(кнопка главного меню LXQt — Papirus не содержит start-here-lxqt).

Запуск: python3 scripts/make_menu_icon.py
"""

from PIL import Image, ImageDraw
import os

REPO = "/home/z/my-project/PhotonOS"
SIZES = [24, 32, 48, 64, 128, 256]


def draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # чёрный квадрат с лёгкой рамкой — читается на светлом панели
    m = max(1, size // 16)
    border = (70, 76, 92, 255)
    d.rectangle((0, 0, size - 1, size - 1), fill=border)
    d.rectangle((m, m, size - 1 - m, size - 1 - m), fill=(8, 9, 12, 255))
    # глазки — белые квадратики в верхней части
    eye = max(2, size * 22 // 150)
    top = size * 26 // 150
    gap = size * 30 // 150
    for ex in (m + gap, size - m - gap - eye):
        d.rectangle((ex, top, ex + eye - 1, top + eye - 1),
                    fill=(245, 246, 248, 255))
    return img


for s in SIZES:
    out = f"{REPO}/overlay/usr/share/icons/photon/{s}x{s}/apps/start-here-photon.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    draw(s).save(out, "PNG", optimize=True)
    print("OK:", out)
