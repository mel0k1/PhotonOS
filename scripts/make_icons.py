#!/usr/bin/env python3
"""Генератор фирменной темы иконок PhotonOS из авторских артов.

Источник: design/icons-src/*.png (полноразмерные арты на чёрном фоне).
Результат: overlay/usr/share/icons/photon/ — тема, наследующая Papirus.

Соответствие артов и значков:
  clock.png  -> document-open-recent          (Недавние документы)
  folder.png -> system-file-manager           (Файловый менеджер PCManFM-Qt)

Корзина (user-trash) больше НЕ переопределяется: авторский арт был
неудачным — работает значок Papirus по наследованию. Логотип меню —
не арт, а рукописный SVG (scalable/apps/start-here-photon.svg и алиасы);
растровые start-here-photon.png делает scripts/make_menu_icon.py.

Требуется Pillow (на хосте разработки, не в ISO): python3 -m pip install pillow
"""
import os
import sys
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "design", "icons-src")
OUT = os.path.join(ROOT, "overlay", "usr", "share", "icons", "photon")

# фон исходников - чёрный: в прозрачность уходит тёмное от границ холста
BG_THRESHOLD = 30
PAD_RATIO = 0.03          # поля вокруг обрезанного арта
SIZES = (24, 32, 48, 64, 128, 256)

# арт -> список (контекст, имя значка)
MAP = {
    "clock.png":  [("actions", "document-open-recent")],
    "folder.png": [("apps", "system-file-manager")],
}

CONTEXTS = ("apps", "actions")


def strip_background(im: Image.Image) -> Image.Image:
    """Прозрачный фон: заливка от краёв холста по «почти чёрным» пикселям."""
    rgb = np.array(im.convert("RGB")).astype(np.int16)
    dark = rgb.max(axis=2) <= BG_THRESHOLD

    alpha = np.full(rgb.shape[:2], 255, dtype=np.uint8)
    h, w = dark.shape
    stack = [(y, x) for y in range(h) for x in (0, w - 1) if dark[y, x]]
    stack += [(y, x) for x in range(w) for y in (0, h - 1) if dark[y, x]]

    seen = np.zeros((h, w), dtype=bool)
    for y, x in stack:
        if not seen[y, x]:
            seen[y, x] = True
            alpha[y, x] = 0
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and dark[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                alpha[ny, nx] = 0
                stack.append((ny, nx))

    rgba = np.dstack([rgb.astype(np.uint8), alpha])
    out = Image.fromarray(rgba)

    # лёгкое размытие альфа-канала снимает чёрную кайму антиалиасинга
    a = out.getchannel("A").filter(ImageFilter.GaussianBlur(1.0))
    a = np.minimum(np.array(out.getchannel("A")), np.array(a))
    out.putalpha(Image.fromarray(a))
    return out


def square_crop(im: Image.Image) -> Image.Image:
    """Обрезка по содержимому + поля, приведение к квадрату."""
    bbox = im.getchannel("A").getbbox()
    im = im.crop(bbox)
    pad = int(max(im.size) * PAD_RATIO)
    side = max(im.size) + 2 * pad
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return canvas


def main() -> int:
    ok = True
    for fname, targets in MAP.items():
        path = os.path.join(SRC, fname)
        if not os.path.isfile(path):
            print(f"!! нет исходника {path}")
            ok = False
            continue
        art = square_crop(strip_background(Image.open(path)))
        for context, name in targets:
            for size in SIZES:
                d = os.path.join(OUT, f"{size}x{size}", context)
                os.makedirs(d, exist_ok=True)
                art.resize((size, size), Image.LANCZOS).save(
                    os.path.join(d, f"{name}.png"), optimize=True)
            print(f"ok: {fname} -> {context}/{name} " + ", ".join(map(str, SIZES)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
