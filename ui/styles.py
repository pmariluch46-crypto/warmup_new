"""
ui/styles.py  --  Shared PyQt6 style helpers for WarmUpPro tabs.
"""
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton,
    QSlider, QCheckBox, QScrollArea, QVBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# ── Colours ───────────────────────────────────────────────────────────────────
BG_PAGE   = "#f4f6fa"
BG_CARD   = "#ffffff"
BG_DARK   = "#1a2035"
ACCENT    = "#2979FF"
ACCENT2   = "#FF6D00"
TEXT_MAIN = "#1a2035"
TEXT_SUB  = "#6b7a99"
BORDER    = "#e0e5f0"
SUCCESS   = "#2e7d32"
DANGER    = "#c62828"


# ── Fonts ─────────────────────────────────────────────────────────────────────
def font(size=10, bold=False):
    f = QFont("Segoe UI", size)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── Page title ────────────────────────────────────────────────────────────────
def page_title(text):
    lbl = QLabel(text)
    lbl.setFont(font(18, bold=True))
    lbl.setStyleSheet(f"color: {TEXT_MAIN}; padding: 0;")
    return lbl


# ── Section card ─────────────────────────────────────────────────────────────
def card(parent=None):
    f = QFrame(parent)
    f.setStyleSheet(f"""
        QFrame {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 10px;
        }}
    """)
    return f


# ── Section header ────────────────────────────────────────────────────────────
def section_title(text):
    lbl = QLabel(text)
    lbl.setFont(font(11, bold=True))
    lbl.setStyleSheet(f"color: {TEXT_MAIN};")
    return lbl


# ── Sub label ─────────────────────────────────────────────────────────────────
def sub_label(text):
    lbl = QLabel(text)
    lbl.setFont(font(9))
    lbl.setStyleSheet(f"color: {TEXT_SUB};")
    return lbl


# ── Primary button ────────────────────────────────────────────────────────────
def primary_btn(text, color=ACCENT):
    btn = QPushButton(text)
    btn.setFont(font(10, bold=True))
    btn.setFixedHeight(38)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {color};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 0 20px;
        }}
        QPushButton:hover {{ background: {_darken(color)}; }}
        QPushButton:pressed {{ background: {_darken(color, 20)}; }}
        QPushButton:disabled {{ background: #c0c8d8; color: #9aa0b0; }}
    """)
    return btn


def danger_btn(text):
    return primary_btn(text, DANGER)


def success_btn(text):
    return primary_btn(text, SUCCESS)


def secondary_btn(text):
    btn = QPushButton(text)
    btn.setFont(font(10))
    btn.setFixedHeight(34)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: #e8ecf5;
            color: {TEXT_MAIN};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 0 16px;
        }}
        QPushButton:hover {{ background: #d8dff0; }}
        QPushButton:pressed {{ background: #c8d0e5; }}
    """)
    return btn


# ── Slider ────────────────────────────────────────────────────────────────────
def styled_slider(min_val, max_val, value, color=ACCENT):
    s = QSlider(Qt.Orientation.Horizontal)
    s.setMinimum(min_val)
    s.setMaximum(max_val)
    s.setValue(value)
    s.setFixedHeight(24)
    s.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            height: 4px;
            background: #dde3f0;
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {color};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
            background: {color};
            border: 2px solid white;
        }}
    """)
    return s


# ── Checkbox ─────────────────────────────────────────────────────────────────
def styled_checkbox(text, color=ACCENT):
    cb = QCheckBox(text)
    cb.setFont(font(9))
    cb.setStyleSheet(f"""
        QCheckBox {{
            color: {TEXT_MAIN};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 17px;
            height: 17px;
            border-radius: 4px;
            border: 2px solid #c0c8d8;
            background: white;
        }}
        QCheckBox::indicator:checked {{
            background: {color};
            border-color: {color};
            image: url(none);
        }}
        QCheckBox::indicator:hover {{
            border-color: {color};
        }}
    """)
    return cb


# ── Scroll area wrapper ───────────────────────────────────────────────────────
def scroll_wrap(widget):
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setStyleSheet(f"background: {BG_PAGE};")
    return area


# ── Divider line ─────────────────────────────────────────────────────────────
def h_divider():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {BORDER};")
    return line


# ── Helper ────────────────────────────────────────────────────────────────────
def _darken(hex_color, amount=15):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r, g, b = max(0, r-amount), max(0, g-amount), max(0, b-amount)
    return f"#{r:02x}{g:02x}{b:02x}"