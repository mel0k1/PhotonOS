#!/usr/bin/env python3
"""Превью рабочего стола PhotonOS (LXQt) — отрисовка по реальным конфигам.

Оффскрин-рендер без X-сервера: обои и иконки берутся из репозитория
(overlay/), стиль панели — по overlay/etc/skel/.config/lxqt/panel.conf
(док снизу, иконки 32px), значки Papirus подтягиваются отдельно (SVG).

Запуск: python3 scripts/screens_lxqt.py  ->  docs/screens/*.png
Требует PyQt6 (QtSvg). Иконки Papirus: PAPIRUS_DIR (по умолчанию /tmp/papirus).
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "installer"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath,  # noqa: E402
                           QPen, QPixmap)
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

QGuiApplication([])  # QPixmap требует QGuiApplication даже оффскрин

W, H = 1600, 900
OUT = os.path.join(ROOT, "docs", "screens")
PAPIRUS = os.environ.get("PAPIRUS_DIR", "/tmp/papirus")
DOCK_H = 44
ACCENT = "#2f86ff"

os.makedirs(OUT, exist_ok=True)


# ── утилиты ─────────────────────────────────────────────────────────────
def svg_pix(name: str, size: int, subdir: str = "apps") -> QPixmap:
    """SVG-иконка Papirus -> QPixmap."""
    path = os.path.join(PAPIRUS, f"{name}.svg")
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    r = QSvgRenderer(path)
    p = QPainter(img)
    r.render(p)
    p.end()
    return QPixmap.fromImage(img)


def photon_icon(name: str, size: int, ctx: str = "apps") -> QPixmap:
    """Значок нашей темы photon (PNG из overlay)."""
    p = os.path.join(ROOT, f"overlay/usr/share/icons/photon/64x64/{ctx}/{name}.png")
    return QPixmap(p).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)


def wallpaper() -> QPixmap:
    p = os.path.join(ROOT, "overlay/usr/share/backgrounds/photon-flow.jpg")
    return QPixmap(p).scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation).copy(0, 0, W, H)


def round_rect(p: QPainter, rect: QRect, radius: int, fill: QColor,
               border: QColor | None = None) -> None:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.setRenderHint(QPainter.Antialiasing)
    p.fillPath(path, fill)
    if border:
        p.setPen(QPen(border, 1))
        p.drawPath(path)


def text(p: QPainter, x: int, y: int, s: str, size: int, color: str,
         bold: bool = False, mono: bool = False, shadow: bool = False) -> None:
    f = QFont("DejaVu Sans Mono" if mono else "DejaVu Sans", size)
    f.setBold(bold)
    p.setFont(f)
    if shadow:
        p.setPen(QColor(0, 0, 0, 150))
        p.drawText(QPoint(x + 1, y + 1), s)
    p.setPen(QColor(color))
    p.drawText(QPoint(x, y), s)


# ── блоки интерфейса ────────────────────────────────────────────────────
def brand_mark(size: int) -> QPixmap:
    """Кнопка меню: фирменный знак Photon (синий круг с 'P')."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, size - 1, size - 1)
    f = QFont("DejaVu Sans", int(size * 0.58))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRect(0, -1, size, size), Qt.AlignCenter, "P")
    p.end()
    return pm


def draw_dock(p: QPainter) -> None:
    rect = QRect(0, H - DOCK_H, W, DOCK_H)
    p.fillRect(rect, QColor(247, 250, 254, 234))
    p.setPen(QPen(QColor(0, 0, 0, 45), 1))
    p.drawLine(0, H - DOCK_H, W, H - DOCK_H)

    # слева: меню + приложения (panel.conf: mainmenu, taskbar iconOnly)
    x = 16
    p.drawPixmap(x, H - DOCK_H + 6, brand_mark(32)); x += 44
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))
    p.drawLine(x - 8, H - DOCK_H + 10, x - 8, H - 10)
    for icon in (photon_icon("system-file-manager", 32),
                 svg_pix("utilities-terminal", 32),
                 svg_pix("multimedia-photo-viewer", 32),
                 svg_pix("ark", 32),
                 svg_pix("preferences-desktop", 32)):
        p.drawPixmap(x, H - DOCK_H + 6, icon)
        x += 42

    # справа: трей и часы (tray, volume, clock)
    clock_w = 52
    rx = W - 14
    text(p, rx - clock_w, H - 15, "15:04", 11, "#3c4650", shadow=True)
    rx -= clock_w + 14
    p.drawPixmap(rx - 22, H - DOCK_H + 11,
                 svg_pix("network-wireless-signal-excellent", 22, "panel"))
    rx -= 26
    p.drawPixmap(rx - 22, H - DOCK_H + 11,
                 svg_pix("audio-volume-high", 22, "panel"))


def draw_desktop(p: QPainter) -> None:
    p.drawPixmap(0, 0, wallpaper())
    # значок «Корзина» (ярлык из /etc/skel/Desktop/Корзина.desktop)
    icon = photon_icon("user-trash", 72, "places")
    p.drawPixmap(26, 22, icon)
    f = QFont("DejaVu Sans", 11)
    p.setFont(f)
    label = "Корзина"
    lw = p.fontMetrics().horizontalAdvance(label)
    lx = 26 + 36 - lw // 2
    p.setPen(QColor(0, 0, 0, 170))
    for dx, dy in ((1, 1), (0, 1), (1, 0)):
        p.drawText(QPoint(lx + dx, 124 + dy), label)
    p.setPen(QColor("white"))
    p.drawText(QPoint(lx, 124), label)


def menu_scene() -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    draw_desktop(p)

    mx, my, mw, mh = 14, H - DOCK_H - 476, 348, 468
    p.fillRect(QRect(mx + 3, my + 4, mw, mh), QColor(0, 0, 0, 45))  # тень
    round_rect(p, QRect(mx, my, mw, mh), 12, QColor("white"),
               QColor("#d8e2ef"))

    # поиск
    sf = QRect(mx + 12, my + 12, mw - 24, 34)
    round_rect(p, sf, 8, QColor("#f2f5fa"), QColor("#d8e2ef"))
    text(p, sf.x() + 12, sf.y() + 23, "Поиск…", 11, "#8a97a6")

    apps = [
        (photon_icon("system-file-manager", 30), "Файловый менеджер"),
        (svg_pix("utilities-terminal", 30), "QTerminal"),
        (svg_pix("multimedia-photo-viewer", 30), "Просмотр изображений"),
        (svg_pix("ark", 30), "Архиватор LXQt"),
        (svg_pix("preferences-desktop", 30), "Настройки рабочего стола"),
        (brand_mark(30), "Установить PhotonOS"),
    ]
    y = my + 66
    for icon, name in apps:
        p.fillRect(QRect(mx + 8, y - 22, mw - 16, 40), QColor("#f5f8fc"))
        p.drawPixmap(mx + 14, y - 19, icon)
        text(p, mx + 56, y + 4, name, 12, "#20262e")
        y += 48

    p.setPen(QPen(QColor("#e3eaf3"), 1))
    p.drawLine(mx + 12, my + mh - 46, mx + mw - 12, my + mh - 46)
    text(p, mx + 14, my + mh - 16, "Настройки", 11, "#6b7787")
    text(p, mx + mw - 128, my + mh - 16, "Завершить сеанс", 11, "#6b7787")

    draw_dock(p)
    p.end()
    return img


def terminal_scene() -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    draw_desktop(p)

    tw, th = 880, 540
    tx, ty = (W - tw) // 2, (H - DOCK_H - th) // 2 - 10
    p.fillRect(QRect(tx + 4, ty + 6, tw, th), QColor(0, 0, 0, 60))
    round_rect(p, QRect(tx, ty, tw, th), 10, QColor("#2b3038"),
               QColor("#1d2229"))
    # заголовок
    tb = QRect(tx, ty, tw, 34)
    p.setClipRect(QRect(tx, ty, tw, 20))
    round_rect(p, tb, 10, QColor("#eceff4"), None)
    p.setClipping(False)
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        p.setBrush(QColor(c)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(tx + 14 + i * 22, ty + 11, 12, 12)
    text(p, tx + 90, ty + 22, "anya@photon-pc: ~", 11, "#5c6b7a")

    # содержимое: photon-fetch
    p.setClipRect(QRect(tx, ty + 34, tw, th - 34))
    text(p, tx + 18, ty + 66, "anya@photon-pc ~ $ ./photon-fetch", 11,
         "#d8dee9", mono=True)

    art = [
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@* ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@*.....@@@@@@@@@@@@@@@@.....%@@% ",
        " @@*.....@@@@@@@@@@@@@@@@.....%@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@% ",
        " +@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@  ",
    ]
    f = QFont("DejaVu Sans Mono", 7)
    p.setFont(f)
    p.setPen(QColor("#4f9cff"))
    ay = ty + 106
    for line in art:
        p.drawText(QPoint(tx + 24, ay), line)
        ay += 11

    info = [
        ("ОС", "PhotonOS 0.1 (glibc) x86_64"),
        ("Хост", "photon-pc"),
        ("Ядро", "6.12.44_1 (linux-lts)"),
        ("Аптайм", "7 мин"),
        ("Пакеты", "412 (xbps-query)"),
        ("Оболочка", "bash"),
        ("ДЕ", "LXQt 2.1"),
        ("Терминал", "qterminal"),
    ]
    iy = ty + 104
    for k, v in info:
        text(p, tx + 330, iy, f"{k}", 11, "#8899aa", bold=True, mono=True)
        text(p, tx + 420, iy, v, 11, "#e5ecf3", mono=True)
        iy += 24

    # палитра
    colors = ["#17191d", "#dc322f", "#859900", "#b58900", "#268bd2",
              "#d33682", "#2aa198", "#d8dee9"]
    px = tx + 330
    for c in colors:
        p.fillRect(QRect(px, iy + 2, 24, 14), QColor(c))
        px += 28

    p.setClipping(False)
    draw_dock(p)
    p.end()
    return img


def wallpaper_scene() -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    draw_desktop(p)
    p.fillRect(0, 0, W, H, QColor(10, 14, 20, 110))  # затемнение

    dw, dh = 660, 470
    dx, dy = (W - dw) // 2, (H - DOCK_H - dh) // 2
    p.fillRect(QRect(dx + 4, dy + 6, dw, dh), QColor(0, 0, 0, 70))
    round_rect(p, QRect(dx, dy, dw, dh), 12, QColor("#f3f6fb"),
               QColor("#d8e2ef"))
    text(p, dx + 20, dy + 34, "Настройки рабочего стола", 14, "#20262e",
         bold=True)

    # левая колонка: разделы
    for i, item in enumerate(("Обои", "Значки", "Меню", "Дополнительно")):
        on = i == 0
        r = QRect(dx + 16, dy + 58 + i * 40, 150, 34)
        if on:
            round_rect(p, r, 8, QColor(ACCENT), None)
        text(p, r.x() + 12, r.y() + 22, item, 11,
             "white" if on else "#5c6b7a", bold=on)

    # сетка обоев
    bgs = ["photon-flow.jpg", "photon-maze.jpg", "photon-cone.jpg",
           "photon-shadow.jpg", "photon-deepin.png"]
    gx, gy, tw, th, gap = dx + 190, dy + 58, 140, 79, 12
    for i, name in enumerate(bgs):
        col, row = i % 3, i // 3
        r = QRect(gx + col * (tw + gap), gy + row * (th + gap), tw, th)
        pm = QPixmap(os.path.join(ROOT, "overlay/usr/share/backgrounds", name))
        pm = pm.scaled(tw, th, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation).copy(0, 0, tw, th)
        p.drawPixmap(r.x(), r.y(), pm)
        if i == 0:  # выбранные обои
            pen = QPen(QColor(ACCENT), 3)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 4, 4)
        path = os.path.join(ROOT, "overlay/usr/share/backgrounds", name)
        if not os.path.exists(path):
            p.fillRect(r, QColor("#dde6f2"))

    # режим и кнопки
    cb = QRect(gx, dy + dh - 92, 200, 32)
    round_rect(p, cb, 8, QColor("white"), QColor("#d8e2ef"))
    text(p, cb.x() + 12, cb.y() + 21, "Режим: Растянуть", 11, "#20262e")
    ok = QRect(dx + dw - 190, dy + dh - 50, 82, 34)
    round_rect(p, ok, 8, QColor(ACCENT), None)
    text(p, ok.x() + 28, ok.y() + 22, "ОК", 11, "white", bold=True)
    cancel = QRect(ok.x() - 100, ok.y(), 88, 34)
    round_rect(p, cancel, 8, QColor("white"), QColor("#d8e2ef"))
    text(p, cancel.x() + 18, cancel.y() + 22, "Отмена", 11, "#5c6b7a")

    draw_dock(p)
    p.end()
    return img


def desktop_scene() -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    draw_desktop(p)
    draw_dock(p)
    p.end()
    return img


def main() -> int:
    scenes = {
        "desktop.jpg": desktop_scene,
        "menu.jpg": menu_scene,
        "terminal.jpg": terminal_scene,
        "wallpaper-settings.jpg": wallpaper_scene,
    }
    for name, fn in scenes.items():
        img = fn()
        # экономим вес репо: 1280x720, JPEG
        small = img.scaled(1280, 720, Qt.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        out = os.path.join(OUT, os.path.splitext(name)[0] + ".jpg")
        small.save(out, quality=92)
        print("ok:", os.path.basename(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
