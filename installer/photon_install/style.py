"""Стиль установщика: палитра в духе Deepin + общий QSS."""

ACCENT = "#2f86ff"          # фирменный синий (кнопки, выделение)
ACCENT_HOVER = "#4a96ff"
ACCENT_PRESSED = "#2b74d9"

BG = "#f3f6fb"              # фон контента
SIDEBAR_BG = "#eaf0f9"      # фон панели шагов
TEXT = "#20262e"
TEXT_DIM = "#6b7787"
CARD = "#ffffff"
BORDER = "#d8e2ef"
WARN = "#c2410c"
OK = "#157347"

QSS = f"""
* {{
    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, #root {{ background: {BG}; }}

/* ── панель шагов ─────────────────────────────────────────── */
#sidebar {{
    background: {SIDEBAR_BG};
    border: none;
    border-right: 1px solid {BORDER};
}}
#brand {{ color: {ACCENT}; font-size: 19px; font-weight: 700; padding: 2px; }}
#steprow {{
    color: {TEXT_DIM};
    padding: 7px 10px;
    border-radius: 9px;
}}
#steprow.current, #steprow[class="current"] {{ background: {ACCENT}; color: white; font-weight: 600; }}
#steprow.done, #steprow[class="done"] {{ color: {OK}; }}

/* ── заголовки ────────────────────────────────────────────── */
#h1 {{ font-size: 22px; font-weight: 700; }}
#sub {{ color: {TEXT_DIM}; }}

/* ── карточки и формы ─────────────────────────────────────── */
#card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLineEdit, QComboBox {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 20px;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: white;
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}

/* ── кнопки ───────────────────────────────────────────────── */
QPushButton {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 18px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton#primary {{
    background: {ACCENT};
    border: none;
    color: white;
    font-weight: 600;
    padding: 9px 26px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#primary:disabled {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; }}

/* ── радио-карточки выбора DE/диска ───────────────────────── */
#pickcard {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 11px;
}}
#pickcard[checked="true"] {{ border: 2px solid {ACCENT}; }}
#picktitle {{ font-weight: 600; }}
#pickdesc {{ color: {TEXT_DIM}; }}
#badge {{
    background: {SIDEBAR_BG};
    border-radius: 8px;
    color: {TEXT_DIM};
    font-size: 11px;
    padding: 2px 8px;
}}
#badge[kind="exp"] {{ background: #fff3e6; color: {WARN}; }}
#badge[kind="ok"] {{ background: #e2f5ea; color: {OK}; }}

/* ── таблица плана/сводки ─────────────────────────────────── */
QTreeWidget {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 4px;
}}
QTreeWidget::item {{ height: 26px; }}
QHeaderView::section {{
    background: {BG};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
}}

#warn {{ color: {WARN}; }}
#ok {{ color: {OK}; }}
#hint {{ color: {TEXT_DIM}; }}
"""
