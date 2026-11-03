#!/usr/bin/env python3
"""Фон GRUB-меню PhotonOS: кадр фирменного ролика (чёрный квадрат с глазами),
вписанный в 1024x768. Результат: design/boot/bg.png (коммитится в репо,
сборка не требует Pillow). Запуск: python3 scripts/make_bootbg.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "branding", "plymouth", "photon-boot", "frame0.png")
OUT = os.path.join(ROOT, "design", "boot", "bg.png")

# 1024x768 — самый «безопасный» gfxmode GRUB (VESA), тянется на всё
W, H = 1024, 768

os.makedirs(os.path.dirname(OUT), exist_ok=True)
im = Image.open(SRC).convert("RGB")
# вписываем с сохранением пропорций на холст #030303 (как в plymouth-теме)
scale = min(W / im.width, H / im.height)
nw, nh = round(im.width * scale), round(im.height * scale)
canvas = Image.new("RGB", (W, H), (3, 3, 3))
canvas.paste(im.resize((nw, nh), Image.LANCZOS), ((W - nw) // 2, (H - nh) // 2))
canvas.save(OUT, optimize=True)
print(OUT, canvas.size, os.path.getsize(OUT), "bytes")
