"""PhotonOS welcome: окно первого входа - обновления, принтеры, копия.

Запускается из autostart только пока пользователь не снял галочку
«Показывать при входе» (флаг ~/.config/photon/no-welcome).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QHBoxLayout,
                             QLabel, QMainWindow, QMessageBox, QPushButton,
                             QPlainTextEdit, QVBoxLayout, QWidget)

ICON = "/usr/share/icons/photon/64x64/apps/start-here-photon.png"
FLAG = os.path.expanduser("~/.config/photon/no-welcome")

QSS = """
QMainWindow, QWidget { background: #14171c; color: #e8eaed; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#sub { color: #9aa0a6; font-size: 13px; }
QPlainTextEdit#fetch {
    font-family: 'Noto Sans Mono', monospace; font-size: 12px;
    color: #c7cbd1; background: #1b1f26; border: 1px solid #2a2f38;
    border-radius: 10px; padding: 10px;
}
QPushButton {
    background: #242a33; border: 1px solid #333b47; border-radius: 10px;
    padding: 14px 16px; text-align: left; font-size: 13px;
}
QPushButton:hover { background: #2c3440; }
QPushButton QLabel#btn_sub { color: #9aa0a6; font-size: 11px; }
QCheckBox { color: #9aa0a6; }
QMessageBox { background: #1b1f26; }
"""


def fetch_text() -> str:
    if not shutil.which("photon-fetch"):
        return ""
    r = subprocess.run(["photon-fetch"], capture_output=True, text=True)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout).strip()


def _button(title: str, sub: str) -> QPushButton:
    btn = QPushButton()
    lay = QVBoxLayout(btn)
    lay.setContentsMargins(6, 2, 6, 2)
    lay.setSpacing(2)
    t = QLabel(title)
    s = QLabel(sub)
    s.setObjectName("btn_sub")
    lay.addWidget(t)
    lay.addWidget(s)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(64)
    return btn


class MainWindow(QMainWindow):
    def __init__(self, autostart: bool):
        super().__init__()
        self.autostart = autostart
        self.setWindowTitle("PhotonOS")
        self.setMinimumSize(560, 460)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        logo = QLabel()
        if os.path.exists(ICON):
            logo.setPixmap(QPixmap(ICON).scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        head.addWidget(logo)
        col = QVBoxLayout()
        t = QLabel("PhotonOS")
        t.setObjectName("title")
        sub = QLabel("Офис, печать и почта уже в системе. С чего начнём?")
        sub.setObjectName("sub")
        col.addWidget(t)
        col.addWidget(sub)
        head.addLayout(col, 1)
        root.addLayout(head)

        info = QPlainTextEdit(fetch_text())
        info.setObjectName("fetch")
        info.setReadOnly(True)
        info.setMaximumHeight(150)
        root.addWidget(info)

        grid = QGridLayout()
        grid.setSpacing(10)
        up = _button("Обновить систему",
                     "свежие пакеты из Debian (apt full-upgrade)")
        up.clicked.connect(lambda: self._run([
            "qterminal", "-e", "sh", "-c",
            "sudo apt update && sudo apt full-upgrade"]))
        prn = _button("Принтеры", "подключить сетевой или USB-принтер")
        prn.clicked.connect(lambda: self._run(["system-config-printer"]))
        bkp = _button("Резервная копия", "домашний каталог на флешку или сервер")
        bkp.clicked.connect(lambda: self._run(["qterminal", "-e", "photon-backup"]))
        mail = _button("Почта", "Claws Mail уже настроен для первого запуска")
        mail.clicked.connect(lambda: self._run(["claws-mail"]))
        grid.addWidget(up, 0, 0)
        grid.addWidget(prn, 0, 1)
        grid.addWidget(bkp, 1, 0)
        grid.addWidget(mail, 1, 1)
        root.addLayout(grid)

        root.addStretch(1)
        self.show_chk = QCheckBox("Показывать при входе в систему")
        self.show_chk.setChecked(True)
        root.addWidget(self.show_chk)

    def _run(self, argv: list) -> None:
        if not shutil.which(argv[0]):
            QMessageBox.warning(self, "PhotonOS",
                                f"Программа не найдена: {argv[0]}")
            return
        try:
            subprocess.Popen(argv, start_new_session=True)
        except OSError as e:
            QMessageBox.warning(self, "PhotonOS", f"Не удалось запустить: {e}")

    def closeEvent(self, event) -> None:
        os.makedirs(os.path.dirname(FLAG), exist_ok=True)
        if self.show_chk.isChecked():
            if os.path.exists(FLAG):
                os.unlink(FLAG)
        else:
            with open(FLAG, "w", encoding="utf-8") as f:
                f.write("1\n")
        super().closeEvent(event)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="PhotonOS welcome")
    ap.add_argument("--autostart", action="store_true",
                    help="из autostart: выйти молча, если показ отключён")
    args = ap.parse_args()
    if args.autostart and os.path.exists(FLAG):
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("photon-welcome")
    app.setStyleSheet(QSS)
    win = MainWindow(args.autostart)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
