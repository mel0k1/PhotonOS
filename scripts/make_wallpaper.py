#!/usr/bin/env python3
"""Генератор фирменных обоев PhotonOS (стиль Deepin: светлый градиент).

Чистый python (zlib + struct), без внешних зависимостей.
Результат: overlay/usr/share/backgrounds/photon-deepin.png, 1920x1080, RGB.
"""
import struct, zlib, os

W, H = 1920, 1080
OUT = os.path.join(os.path.dirname(__file__), "..",
                   "overlay/usr/share/backgrounds/photon-deepin.png")

# Углы диагонального градиента (светло-голубая гамма, как у Deepin)
TL = (0xDF, 0xEF, 0xFB)  # верх-лево: почти белый голубой
TR = (0xB4, 0xD6, 0xF0)  # верх-право: светло-голубой
BL = (0xC2, 0xDE, 0xF4)  # низ-лево: голубой
BR = (0x8F, 0xBA, 0xE0)  # низ-право: насыщенный светло-синий

GLOW = (255, 255, 255)   # мягкое белое свечение (боке)


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo=0, hi=255):
    return int(max(lo, min(hi, v)))


rows = []
tx_step = 1.0 / (W - 1)
for y in range(H):
    ty = y / (H - 1)
    row = bytearray()
    row.append(0)  # PNG-фильтр строки: None
    for x in range(W):
        tx = x * tx_step
        # билинейный градиент по 4 углам
        r_t = lerp(TL[0], TR[0], tx); g_t = lerp(TL[1], TR[1], tx); b_t = lerp(TL[2], TR[2], tx)
        r_b = lerp(BL[0], BR[0], tx); g_b = lerp(BL[1], BR[1], tx); b_b = lerp(BL[2], BR[2], tx)
        r = lerp(r_t, r_b, ty); g = lerp(g_t, g_b, ty); b = lerp(b_t, b_b, ty)
        # мягкое свечение-боке: большое пятно в левом верхнем квадранте
        dx = (x - W * 0.28) / (W * 0.42)
        dy = (y - H * 0.30) / (H * 0.42)
        k = 0.55 * pow(2.718281828, -(dx * dx + dy * dy) * 2.2)
        # второе, слабее — правый низ
        dx2 = (x - W * 0.80) / (W * 0.35)
        dy2 = (y - H * 0.85) / (H * 0.35)
        k += 0.30 * pow(2.718281828, -(dx2 * dx2 + dy2 * dy2) * 2.0)
        r = lerp(r, GLOW[0], k); g = lerp(g, GLOW[1], k); b = lerp(b, GLOW[2], k)
        # лёгкая виньетка по краям (глубина)
        vx = tx - 0.5
        vy = ty - 0.5
        vig = 1.0 - 0.10 * (vx * vx + vy * vy) ** 1.2
        row.append(clamp(r * vig))
        row.append(clamp(g * vig))
        row.append(clamp(b * vig))
    rows.append(bytes(row))

raw = b"".join(rows)


def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return c


png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(raw, 9))
png += chunk(b"IEND", b"")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "wb") as f:
    f.write(png)
print("OK:", os.path.abspath(OUT), len(png), "bytes")
