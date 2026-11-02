#!/usr/bin/env python3
"""Обои PhotonOS: авторские изображения -> /usr/share/backgrounds.

Источник: design/wallpapers-src/*.jpg (1280x720).
Результат: overlay/usr/share/backgrounds/photon-*.jpg (1920x1080).
Дефолт задаётся в /etc/skel/.config/pcmanfm-qt/lxqt/settings.conf.

Все обои лежат в /usr/share/backgrounds — их видно в «Настройках рабочего
стола» PCManFM-Qt и в «Настройках внешнего вида» LXQt (вкладка «Обои»),
переключение — через эти же настройки без правки файлов.

Требуется Pillow (на хосте разработки, не в ISO).
"""
import os
import sys
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "design", "wallpapers-src")
OUT = os.path.join(ROOT, "overlay", "usr", "share", "backgrounds")

W, H = 1920, 1080

# исходник -> имя в системе
MAP = {
    "1000033605.jpg": "photon-maze.jpg",    # тёмная геометрия (лабиринт)
    "1000033606.jpg": "photon-flow.jpg",    # розовое «стекло» — обои по умолчанию
    "1000033607.jpg": "photon-cone.jpg",    # оранжевый конус
    "1000033608.jpg": "photon-shadow.jpg",  # тёмные блоки
}


def main() -> int:
    ok = True
    for src, dst in MAP.items():
        path = os.path.join(SRC, src)
        if not os.path.isfile(path):
            print(f"!! нет исходника {path}")
            ok = False
            continue
        im = Image.open(path).convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=48, threshold=2))
        im.save(os.path.join(OUT, dst), quality=92, optimize=True)
        print(f"ok: {src} -> {dst} {W}x{H}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
