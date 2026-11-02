"""Мастер установки PhotonOS: боковая навигация + шаги (M1).

Каркас в стиле Deepin Installer: слева шаги, справа контент, снизу навигация.
Реальная установка подключается на M2 (docs/INSTALLER.md).
"""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import disk, style
from .backend import BackendError, Installer
from .locale import tr
from .settings import DE_OPTIONS, InstallSettings, valid_hostname, valid_login

STEPS = ["welcome", "kb", "disk", "user", "de", "sum", "prog"]

LAYOUTS = [
    ("us", "English (US)"), ("ru", "Русская"), ("de", "Deutsch"),
    ("fr", "Français"), ("es", "Español"), ("it", "Italiano"),
    ("uk", "Українська"), ("pl", "Polski"), ("by", "Беларуская"),
    ("kz", "Қазақша"), ("pt", "Português"), ("cz", "Čeština"),
    ("tr", "Türkçe"), ("jp", "日本語"), ("cn", "中文"),
]


def available_timezones() -> list:
    """Список зон из /usr/share/zoneinfo (без posix*/right*)."""
    base = "/usr/share/zoneinfo"
    zones = []
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(("posix", "right", "."))]
            for f in files:
                if f.startswith((".", "zone", "leap")) or "+" in f:
                    continue
                rel = os.path.relpath(os.path.join(root, f), base)
                if "/" in rel:
                    zones.append(rel)
    return sorted(zones) or ["UTC"]


def current_timezone() -> str:
    """Определение зоны по симлинку /etc/localtime."""
    try:
        real = os.path.realpath("/etc/localtime")
        if "/zoneinfo/" in real:
            return real.split("/zoneinfo/", 1)[1]
    except OSError:
        pass
    return ""


# ── переиспользуемые виджеты ────────────────────────────────────────────

def head(title_key: str, sub_key: str, lang: str) -> tuple:
    """Заголовок шага: h1 + подзаголовок."""
    h1 = QLabel(tr(lang, title_key))
    h1.setObjectName("h1")
    sub = QLabel(tr(lang, sub_key))
    sub.setObjectName("sub")
    sub.setWordWrap(True)
    return h1, sub


class PickCard(QFrame):
    """Радио-карточка (выбор диска/DE): рамка подсвечивается при выборе."""

    def __init__(self, title: str, desc: str, badge: str, badge_class: str):
        super().__init__()
        self.setObjectName("pickcard")
        self.radio = QRadioButton(title)
        self.radio.setObjectName("picktitle")
        self.radio.setCursor(Qt.PointingHandCursor)
        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("pickdesc")
        desc_lbl.setWordWrap(True)
        badge_lbl = QLabel(badge)
        badge_lbl.setObjectName("badge")
        if badge_class:
            badge_lbl.setProperty("kind", badge_class)

        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(self.radio)
        top.addStretch(1)
        top.addWidget(badge_lbl)
        box.addLayout(top)
        box.addWidget(desc_lbl)
        self.radio.toggled.connect(self._restyle)

    def _restyle(self, *a) -> None:
        self.setProperty("checked", "true" if self.radio.isChecked() else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ── шаги ────────────────────────────────────────────────────────────────

class Step(QWidget):
    """Базовый шаг: заголовок + контент; валидация и применение настроек."""

    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 28, 36, 20)
        outer.setSpacing(14)
        h1, sub = head(self.TITLE, self.SUB, mw.lang)
        self.h1, self.sub = h1, sub
        outer.addWidget(h1)
        outer.addWidget(sub)

    lang: str = property(lambda self: self.mw.lang)

    TITLE = ""
    SUB = ""

    def validate(self) -> str:
        """Ключ ошибки или '' — если шаг валиден."""
        return ""

    def apply(self, s: InstallSettings) -> None:
        pass

    def refresh(self, s: InstallSettings) -> None:
        """Вызывается при входе на шаг (перечитать состояние)."""

    def retranslate(self) -> None:
        self.h1.setText(tr(self.lang, self.TITLE))
        self.sub.setText(tr(self.lang, self.SUB))


class WelcomeStep(Step):
    TITLE, SUB = "welcome_h1", "welcome_sub"

    def __init__(self, mw):
        super().__init__(mw)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        self.lang_lbl = QLabel()
        self.lang_box = QComboBox()
        for code, name in (("ru", "Русский"), ("en", "English")):
            self.lang_box.addItem(name, code)
        self.tz_lbl = QLabel()
        self.tz_box = QComboBox()
        self.tz_box.addItems(available_timezones())
        current = current_timezone()
        if current in available_timezones():
            self.tz_box.setCurrentText(current)
        grid.addWidget(self.lang_lbl, 0, 0)
        grid.addWidget(self.lang_box, 0, 1)
        grid.addWidget(self.tz_lbl, 1, 0)
        grid.addWidget(self.tz_box, 1, 1)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(Qt.AlignTop)
        outer = self.layout()
        card = QFrame()
        card.setObjectName("card")
        card.setLayout(grid)
        card.setMaximumWidth(640)
        outer.addWidget(card)
        outer.addStretch(1)
        self.lang_box.currentIndexChanged.connect(self._lang_changed)
        self.retranslate()

    def _lang_changed(self, idx: int) -> None:
        self.mw.set_language(self.lang_box.currentData())

    def apply(self, s):
        s.lang = self.lang_box.currentData()
        s.tz = self.tz_box.currentText()

    def retranslate(self):
        super().retranslate()
        self.lang_lbl.setText(tr(self.lang, "lang_label"))
        self.tz_lbl.setText(tr(self.lang, "tz_label"))


class KeyboardStep(Step):
    TITLE, SUB = "kb_h1", "kb_sub"

    def __init__(self, mw):
        super().__init__(mw)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        self.layout_lbl = QLabel()
        self.layout_box = QComboBox()
        for code, name in LAYOUTS:
            self.layout_box.addItem(name, code)
        self.variant_lbl = QLabel()
        self.variant_box = QComboBox()
        self.variant_box.addItem("—" if mw.lang != "ru" else "по умолчанию")
        self.test_lbl = QLabel()
        self.test_edit = QLineEdit()
        self.test_edit.setPlaceholderText("PhotonOS 0.1 …")
        grid.addWidget(self.layout_lbl, 0, 0)
        grid.addWidget(self.layout_box, 0, 1)
        grid.addWidget(self.variant_lbl, 1, 0)
        grid.addWidget(self.variant_box, 1, 1)
        grid.addWidget(self.test_lbl, 2, 0)
        grid.addWidget(self.test_edit, 2, 1)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(Qt.AlignTop)
        card = QFrame()
        card.setObjectName("card")
        card.setLayout(grid)
        card.setMaximumWidth(640)
        self.layout().addWidget(card)
        self.layout().addStretch(1)
        self.retranslate()

    def apply(self, s):
        s.layout = self.layout_box.currentData() or "us"

    def retranslate(self):
        super().retranslate()
        self.layout_lbl.setText(tr(self.lang, "layout_label"))
        self.variant_lbl.setText(tr(self.lang, "variant_label"))
        self.test_lbl.setText(tr(self.lang, "test_label"))


class DiskStep(Step):
    TITLE, SUB = "disk_h1", "disk_sub"

    def __init__(self, mw):
        super().__init__(mw)
        outer = self.layout()

        top = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumHeight(150)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        self.refresh_btn = QPushButton()
        self.refresh_btn.clicked.connect(lambda: self._reload(mw.settings))
        top.addWidget(self.list, 1)
        btns = QVBoxLayout()
        btns.addWidget(self.refresh_btn)
        btns.addStretch(1)
        top.addLayout(btns)
        outer.addLayout(top)

        self.state_lbl = QLabel("")
        self.state_lbl.setObjectName("warn")
        self.state_lbl.setWordWrap(True)
        outer.addWidget(self.state_lbl)

        self.swap_chk = QCheckBox()
        self.swap_chk.toggled.connect(lambda _: self._show_plan())
        outer.addWidget(self.swap_chk)

        plan_lbl = QLabel("")
        plan_lbl.setObjectName("sub")
        outer.addWidget(plan_lbl)
        self.plan_lbl = plan_lbl
        self.plan = QTreeWidget()
        self.plan.setColumnCount(3)
        self.plan.setHeaderLabels(["", "", ""])
        self.plan.setRootIsDecorated(False)
        self.plan.setMaximumHeight(150)
        outer.addWidget(self.plan)
        self.retranslate()

    # -- данные ---------------------------------------------------------
    def _reload(self, s: InstallSettings) -> None:
        s.disks = disk.list_disks(fake=self.mw.fake_disks)
        self.list.clear()
        for d in s.disks:
            mark = ""
            if d.has_data:
                mark = "  ⚠"
            QListWidgetItem(f"{d.describe()}{mark}", self.list)
        if s.disk:
            for i, d in enumerate(s.disks):
                if d.path == s.disk:
                    self.list.setCurrentRow(i)
                    break
        else:
            self.list.setCurrentRow(0)

    def _current_disk(self):
        idx = self.list.currentRow()
        disks = self.mw.settings.disks
        return disks[idx] if 0 <= idx < len(disks) else None

    def _selection_changed(self) -> None:
        self._show_plan()

    def _show_plan(self) -> None:
        d = self._current_disk()
        if not d:
            self.state_lbl.setText(tr(self.lang, "no_disks"))
            self.plan.clear()
            return
        if d.has_data:
            self.state_lbl.setProperty("class", "warn")
            self.state_lbl.setText("⚠ " + tr(self.lang, "disk_wipe_warn", disk=d.path))
        else:
            self.state_lbl.setText("✔ " + tr(self.lang, "disk_empty_ok"))
        plan = disk.auto_plan(d.size, self.swap_chk.isChecked())
        self.plan.clear()
        for row in plan:
            QTreeWidgetItem(self.plan, [
                tr(self.lang, f"role_{row['role']}"),
                disk.human_size(row["size"]),
                row["fs"],
            ])
        for col in range(3):
            self.plan.resizeColumnToContents(col)

    def refresh(self, s):
        if not s.disks:
            self._reload(s)
        self._show_plan()

    def validate(self) -> str:
        return "" if self._current_disk() else "no_disks"

    def apply(self, s):
        d = self._current_disk()
        if d:
            s.disk, s.disk_size = d.path, d.size_h
        s.swap = self.swap_chk.isChecked()

    def retranslate(self):
        super().retranslate()
        self.refresh_btn.setText(tr(self.lang, "refresh"))
        self.swap_chk.setText(tr(self.lang, "swap_label"))
        self.plan_lbl.setText(tr(self.lang, "plan_label"))
        self.plan.setHeaderLabels([
            tr(self.lang, "plan_role"), tr(self.lang, "plan_size"), tr(self.lang, "plan_fs")])


class UserStep(Step):
    TITLE, SUB = "user_h1", "user_sub"

    def __init__(self, mw):
        super().__init__(mw)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        self.full_lbl = QLabel()
        self.full_edit = QLineEdit()
        self.login_lbl = QLabel()
        self.login_edit = QLineEdit()
        self.pass_lbl = QLabel()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass2_lbl = QLabel()
        self.pass2_edit = QLineEdit()
        self.pass2_edit.setEchoMode(QLineEdit.Password)
        self.show_chk = QCheckBox()
        self.show_chk.toggled.connect(self._toggle_echo)
        self.host_lbl = QLabel()
        self.host_edit = QLineEdit()
        self.host_edit.setText("photon")
        rows = [
            (self.full_lbl, self.full_edit),
            (self.login_lbl, self.login_edit),
            (self.pass_lbl, self.pass_edit),
            (self.pass2_lbl, self.pass2_edit),
        ]
        for r, (lbl, edt) in enumerate(rows):
            grid.addWidget(lbl, r, 0)
            grid.addWidget(edt, r, 1)
        grid.addWidget(self.show_chk, len(rows), 1)
        grid.addWidget(self.host_lbl, len(rows) + 1, 0)
        grid.addWidget(self.host_edit, len(rows) + 1, 1)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(Qt.AlignTop)
        card = QFrame()
        card.setObjectName("card")
        card.setLayout(grid)
        card.setMaximumWidth(640)
        self.layout().addWidget(card)
        self.layout().addStretch(1)
        self.retranslate()

    def _toggle_echo(self, show: bool) -> None:
        mode = QLineEdit.Normal if show else QLineEdit.Password
        self.pass_edit.setEchoMode(mode)
        self.pass2_edit.setEchoMode(mode)

    def validate(self) -> str:
        if not (self.login_edit.text().strip() and self.pass_edit.text()
                and self.host_edit.text().strip()):
            return "err_required"
        if len(self.pass_edit.text()) < 6 or self.pass_edit.text() != self.pass2_edit.text():
            return "err_pass"
        if not valid_login(self.login_edit.text().strip()):
            return "err_login"
        return ""

    def apply(self, s):
        s.fullname = self.full_edit.text().strip()
        s.username = self.login_edit.text().strip()
        s.password = self.pass_edit.text()
        s.hostname = self.host_edit.text().strip()

    def refresh(self, s):
        if s.username and not self.login_edit.text():
            self.login_edit.setText(s.username)
            self.full_edit.setText(s.fullname)
            self.host_edit.setText(s.hostname or "photon")

    def retranslate(self):
        super().retranslate()
        self.full_lbl.setText(tr(self.lang, "fullname_label"))
        self.login_lbl.setText(tr(self.lang, "login_label"))
        self.pass_lbl.setText(tr(self.lang, "pass_label"))
        self.pass2_lbl.setText(tr(self.lang, "pass2_label"))
        self.show_chk.setText(tr(self.lang, "show_pass"))
        self.host_lbl.setText(tr(self.lang, "host_label"))


class DeStep(Step):
    """Выбор окружения: наш LXQt, MacShell, без DE и другие (бейджи)."""
    TITLE, SUB = "de_h1", "de_sub"

    def __init__(self, mw):
        super().__init__(mw)
        self.cards: list = []
        flow = QVBoxLayout()
        flow.setSpacing(10)
        for opt in DE_OPTIONS:
            card = PickCard(
                opt["title"],
                opt["desc"],
                tr(mw.lang, opt["badge"]),
                "exp" if opt["badge"] == "de_badge_exp" else
                ("ok" if opt["badge"] == "de_badge_default" else ""),
            )
            card.radio.setChecked(opt["id"] == mw.settings.de)
            card.radio.toggled.connect(self._picked)
            self.cards.append((card, opt))
            flow.addWidget(card)
        holder = QWidget()
        holder.setLayout(flow)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(holder)
        scroll.setMaximumWidth(720)
        self.layout().addWidget(scroll)

    def _picked(self) -> None:
        for card, opt in self.cards:
            if card.radio.isChecked():
                self.mw.settings.de = opt["id"]

    def apply(self, s):
        s.de = self.mw.settings.de

    def retranslate(self):
        super().retranslate()
        for card, opt in self.cards:
            card.radio.setText(opt["title"])
            for lbl in card.findChildren(QLabel):
                if lbl.objectName() == "badge":
                    lbl.setText(tr(self.lang, opt["badge"]))


class SummaryStep(Step):
    TITLE, SUB = "sum_h1", "sum_sub"

    def __init__(self, mw):
        super().__init__(mw)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setRootIsDecorated(False)
        self.tree.header().setStretchLastSection(True)
        self.layout().addWidget(self.tree)
        self.retranslate()

    def refresh(self, s):
        self.tree.clear()
        kb = s.layout + (f" ({s.variant})" if s.variant else "")
        rows = [
            ("sum_lang", {"ru": "Русский", "en": "English"}.get(s.lang, s.lang)),
            ("sum_tz", s.tz),
            ("sum_kb", kb),
            ("sum_disk", f"{s.disk} ({s.disk_size}) — {tr(self.lang, 'sum_wipe')}"),
            ("sum_swap", tr(self.lang, "sum_yes" if s.swap else "sum_no")),
            ("sum_user", f"{s.fullname} ({s.username})" if s.fullname else s.username),
            ("sum_host", s.hostname),
            ("sum_de", s.de_title()),
        ]
        for key, value in rows:
            QTreeWidgetItem(self.tree, [tr(self.lang, key), str(value)])
        self.tree.resizeColumnToContents(0)

    def retranslate(self):
        super().retranslate()
        self.tree.setHeaderLabels([tr(self.lang, "param_label"), ""])


# ── установка (M2) ──────────────────────────────────────────────────────

class InstallThread(QThread):
    """Бэкенд в отдельном потоке; сигналы уже потокобезопасны (queued)."""
    step_sig = Signal(str, int, int)
    log_sig = Signal(str)
    done_sig = Signal()
    fail_sig = Signal(str)

    def __init__(self, settings, dry_run: bool = False):
        super().__init__()
        self.settings = settings
        self.dry_run = dry_run
        self.steps = []  # (key, title) — заполнит start()

    def plan(self) -> list:
        inst = Installer(self.settings, dry_run=True)
        return inst.build_steps()

    def run(self) -> None:
        inst = Installer(self.settings, dry_run=self.dry_run)
        inst.on_step = lambda k, i, t: self.step_sig.emit(k, i, t)
        inst.on_log = self.log_sig.emit
        inst.on_done = self.done_sig.emit
        try:
            inst.run()
        except BackendError as e:
            self.fail_sig.emit(str(e))
        except FileNotFoundError as e:
            self.fail_sig.emit(
                f"утилита не найдена: {e.filename or e}. "
                "На live-ISO она входит в базовые пакеты.")
        except OSError as e:
            self.fail_sig.emit(f"ошибка системы: {e}")


class ProgressStep(Step):
    """Ход установки: список шагов слева, журнал справа."""
    TITLE, SUB = "prog_h1", "prog_sub"

    def __init__(self, mw):
        super().__init__(mw)
        body = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumWidth(330)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("DejaVu Sans Mono", 9))
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)
        body.addWidget(self.tree, 1)
        body.addWidget(self.log, 2)
        self.layout().addLayout(body, 1)
        self.status = QLabel("")
        self.status.setObjectName("sub")
        self.status.setWordWrap(True)
        self.layout().addWidget(self.status)
        self.thread = None
        self.done = False
        self.failed = False

    def start(self, dry_run: bool) -> None:
        if self.thread is not None:
            return
        self.thread = InstallThread(self.mw.settings, dry_run=dry_run)
        self.tree.clear()
        for key, title, _ in self.thread.plan():
            it = QTreeWidgetItem(self.tree, ["○  " + tr(self.lang, f"prog_step_{key}")])
            it.step_key = key
        self.tree.resizeColumnToContents(0)
        self.thread.step_sig.connect(self.on_step)
        self.thread.log_sig.connect(self.log.appendPlainText)
        self.thread.done_sig.connect(self.on_done)
        self.thread.fail_sig.connect(self.on_fail)
        if dry_run:
            self.status.setText(tr(self.lang, "prog_dry"))
        self.thread.start()
        self.mw._update_sidebar()

    def on_step(self, key: str, idx: int, total: int) -> None:
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            mark = "✔" if i < idx else ("▶" if i == idx else "○")
            it.setText(0, mark + "  " + tr(self.lang, f"prog_step_{it.step_key}"))
        if key == "done":
            self.status.setText(tr(self.lang, "prog_done"))

    def on_done(self) -> None:
        self.done = True
        self.failed = False
        self.status.setText("✔ " + tr(self.lang, "prog_done"))
        self.status.setObjectName("ok")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.mw._update_sidebar()

    def on_fail(self, msg: str) -> None:
        self.done = True
        self.failed = True
        self.status.setText("✘ " + tr(self.lang, "prog_fail") + "\n" + msg)
        self.status.setObjectName("warn")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.mw._update_sidebar()

    def retranslate(self):
        super().retranslate()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            it.setText(0, it.text(0)[0] + "  " + tr(self.lang, f"prog_step_{it.step_key}"))
        if self.done and not self.failed:
            self.status.setText("✔ " + tr(self.lang, "prog_done"))
        elif self.done and self.failed:
            self.status.setText("✘ " + tr(self.lang, "prog_fail"))


# ── главное окно ────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    STEP_KEYS = {
        "welcome": "step_welcome", "kb": "step_kb", "disk": "step_disk",
        "user": "step_user", "de": "step_de", "sum": "step_sum",
        "prog": "step_prog",
    }

    def __init__(self, lang: str = "ru", fake_disks: bool = False,
                 warn_root: bool = False, dry_run: bool = False):
        super().__init__()
        self.lang = lang
        self.fake_disks = fake_disks
        self.dry_run = dry_run
        self.settings = InstallSettings(lang=lang)
        self.settings.tz = current_timezone()
        self.step_idx = 0
        self.setWindowTitle(tr(lang, "app_title"))
        self.setMinimumSize(960, 640)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        body = QHBoxLayout(root)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # боковая панель шагов
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(230)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(16, 20, 16, 16)
        side_l.setSpacing(4)
        brand = QLabel("PhotonOS")
        brand.setObjectName("brand")
        side_l.addWidget(brand)
        side_l.addSpacing(10)
        self.step_rows: list = []
        for key in STEPS:
            row = QLabel("")
            row.setObjectName("steprow")
            row.setFixedHeight(34)
            row.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            row.setContentsMargins(10, 0, 10, 0)
            row.setCursor(Qt.PointingHandCursor)
            side_l.addWidget(row)
            self.step_rows.append(row)
        side_l.addStretch(1)
        body.addWidget(side)

        # контент: шаги
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        body.addLayout(content, 1)

        self.stack = QStackedWidget()
        self.steps: dict = {}
        for key, cls in (
            ("welcome", WelcomeStep), ("kb", KeyboardStep), ("disk", DiskStep),
            ("user", UserStep), ("de", DeStep), ("sum", SummaryStep),
            ("prog", ProgressStep),
        ):
            w = cls(self)
            self.steps[key] = w
            self.stack.addWidget(w)
        content.addWidget(self.stack, 1)

        if warn_root:
            warn = QLabel(tr(lang, "root_warn"))
            warn.setObjectName("warn")
            warn.setAlignment(Qt.AlignCenter)
            warn.setContentsMargins(0, 6, 0, 6)
            content.addWidget(warn)

        # нижняя навигация
        nav = QHBoxLayout()
        nav.setContentsMargins(36, 10, 36, 14)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.back_btn = QPushButton()
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("primary")
        self.next_btn.clicked.connect(self.go_next)
        nav.addWidget(self.hint, 1)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        content.addLayout(nav)

        self._update_sidebar()

    # -- навигация -------------------------------------------------------
    def current_key(self) -> str:
        return STEPS[self.step_idx]

    def go_back(self) -> None:
        if self.current_key() == "prog":
            return  # во время установки назад нельзя
        if self.step_idx > 0:
            self.step_idx -= 1
            self._enter()

    def go_next(self) -> None:
        if self.current_key() == "prog":
            if self.steps["prog"].done and not self.steps["prog"].failed:
                self._do_reboot()
            return
        step = self.steps[self.current_key()]
        err = step.validate()
        if err:
            self.hint.setText(tr(self.lang, err))
            return
        self.hint.setText("")
        step.apply(self.settings)
        if self.step_idx < len(STEPS) - 1:
            self.step_idx += 1
            self._enter()
            if self.current_key() == "prog":
                self.steps["prog"].start(dry_run=self.dry_run)

    def _do_reboot(self) -> None:
        if self.dry_run:
            QMessageBox.information(self, tr(self.lang, "app_title"),
                                    tr(self.lang, "prog_dry"))
            self.close()
            return
        subprocess.Popen(["reboot"])
        self.close()

    def _enter(self) -> None:
        self.stack.setCurrentIndex(self.step_idx)
        self.steps[self.current_key()].refresh(self.settings)
        self._update_sidebar()

    def _update_sidebar(self) -> None:
        for i, row in enumerate(self.step_rows):
            key = STEPS[i]
            row.setText(f"{i + 1}.  {tr(self.lang, self.STEP_KEYS[key])}")
            row.setProperty("class",
                            "current" if i == self.step_idx else
                            ("done" if i < self.step_idx else ""))
            row.style().unpolish(row)
            row.style().polish(row)
        self.back_btn.setText(tr(self.lang, "back"))
        prog = self.steps["prog"]
        if self.current_key() == "prog":
            self.back_btn.setEnabled(prog.failed)
            self.next_btn.setText(tr(self.lang, "prog_reboot"))
            self.next_btn.setEnabled(prog.done and not prog.failed)
        else:
            self.next_btn.setText(tr(self.lang, "install_btn")
                                  if self.step_idx == len(STEPS) - 2
                                  else tr(self.lang, "next"))
            self.next_btn.setEnabled(True)

    # -- язык ------------------------------------------------------------
    def set_language(self, lang: str) -> None:
        if lang == self.lang:
            return
        self.lang = lang
        self.settings.lang = lang
        self.setWindowTitle(tr(lang, "app_title"))
        for w in self.steps.values():
            w.retranslate()
        self._update_sidebar()
