#!/usr/bin/env python3
"""Оффскрин-скриншоты шагов мастера (проверка дизайна без X-сервера).

Запуск: python3 scripts/installer_shots.py  ->  /tmp/installer-shots/*.png
Требует PySide6; платформа offscreen, реальные диски не трогаются.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "installer"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from photon_install import style  # noqa: E402
from photon_install.wizard import STEPS, MainWindow  # noqa: E402


def main() -> int:
    out = "/tmp/installer-shots"
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(style.QSS)
    win = MainWindow(lang="ru", fake_disks=True, warn_root=False)
    win.resize(980, 660)
    win.show()

    # заполняем пользователя и идём настоящим путём навигации (apply + next)
    u = win.steps["user"]
    u.login_edit.setText("anya")
    u.full_edit.setText("Аня Волкова")
    u.pass_edit.setText("hunter2")
    u.pass2_edit.setText("hunter2")
    win.settings.de = "macshell"

    last = len(STEPS) - 1
    for i, key in enumerate(STEPS):
        win.step_idx = i
        win.stack.setCurrentIndex(i)
        win.steps[key].refresh(win.settings)
        win._update_sidebar()
        app.processEvents()
        app.processEvents()
        win.grab().save(f"{out}/{i + 1:02d}-{key}.png")
        print("shot:", key)
        if i < last:
            win.go_next()          # apply() текущего шага + переход
    return 0


if __name__ == "__main__":
    sys.exit(main())
