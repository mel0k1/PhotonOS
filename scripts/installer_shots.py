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

    last = len(STEPS) - 2   # из «Сводки» в «Установку» идём отдельно, с dry-run
    for i, key in enumerate(STEPS[:-1]):
        win.step_idx = i
        win.stack.setCurrentIndex(i)
        win.steps[key].refresh(win.settings)
        win._update_sidebar()
        app.processEvents()
        app.processEvents()
        win.grab().save(f"{out}/{i + 1:02d}-{key}.png")
        print("shot:", key)
        if i < len(STEPS) - 2:   # с «Сводки» переходим отдельно, с dry-run
            win.go_next()        # apply() текущего шага + переход

    # шаг prog — dry-run бэкенда в QThread: интеграционный тест
    from PySide6.QtCore import QEventLoop, QTimer
    win.dry_run = True
    prog = win.steps["prog"]
    win.step_idx = len(STEPS) - 1
    win._enter()
    prog.start(dry_run=True)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.start(60000)             # предохранитель на 60 с
    app.processEvents()
    # ждём финал (done/fail) — сигналы с worker-потока queued
    while not (prog.done or prog.failed):
        if not timer.isActive():
            break
        app.processEvents(QEventLoop.AllEvents, 50)
    win._update_sidebar()
    app.processEvents()
    win.grab().save(f"{out}/07-prog.png")
    print("shot: prog | done =", prog.done, "| failed =", prog.failed)
    if prog.failed:
        print(prog.status.text())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
