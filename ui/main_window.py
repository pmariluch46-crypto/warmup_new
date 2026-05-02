from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QColor

from ui.tab_run import RunTab
from ui.tab_queries import QueriesTab
from ui.tab_amazon import AmazonTab
from ui.tab_scheduler import SchedulerTab
from ui.tab_history import HistoryTab
from ui.tab_settings import SettingsTab


# ── Sidebar nav button ────────────────────────────────────────────────────────
class NavButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI", 10))
        self._update_style(False)

    def _update_style(self, checked):
        if checked:
            self.setStyleSheet("""
                QPushButton {
                    background: #2979FF;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 0 16px;
                    text-align: left;
                    font-weight: 600;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #b0b8c8;
                    border: none;
                    border-radius: 6px;
                    padding: 0 16px;
                    text-align: left;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.07);
                    color: #ffffff;
                }
            """)

    def setChecked(self, checked):
        super().setChecked(checked)
        self._update_style(checked)


# ── Main Window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("WarmUpPro")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 780)

        try:
            self.setWindowIcon(QIcon("icon.ico"))
        except Exception:
            pass

        self._build_ui()
        self._nav_buttons[0].setChecked(True)
        self.stack.setCurrentIndex(0)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet("background: #1a2035;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 24, 12, 16)
        sb_layout.setSpacing(4)

        # Logo
        logo_label = QLabel("WarmU<span style='color:#2979FF;font-weight:900;'>P</span>ro")
        logo_label.setTextFormat(Qt.TextFormat.RichText)
        logo_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        logo_label.setStyleSheet("color: #ffffff; padding: 0 8px; margin-bottom: 4px;")
        sb_layout.addWidget(logo_label)

        subtitle = QLabel("Browser Warm-Up Automation")
        subtitle.setFont(QFont("Segoe UI", 8))
        subtitle.setStyleSheet("color: #5a6a8a; padding: 0 8px; margin-bottom: 16px;")
        sb_layout.addWidget(subtitle)

        # Nav buttons
        nav_items = ["Run", "Queries", "Amazon", "Scheduler", "History", "Settings"]
        self._nav_buttons = []
        for label in nav_items:
            btn = NavButton(label)
            btn.clicked.connect(lambda checked, l=label: self._on_nav(l))
            sb_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sb_layout.addStretch()

        # Language switcher
        lang_row = QHBoxLayout()
        lang_row.setSpacing(4)
        self.btn_en = self._lang_btn("EN", True)
        self.btn_ru = self._lang_btn("РУС", False)
        self.btn_en.clicked.connect(lambda: self._set_lang("en"))
        self.btn_ru.clicked.connect(lambda: self._set_lang("ru"))
        lang_row.addWidget(self.btn_en)
        lang_row.addWidget(self.btn_ru)
        lang_row.addStretch()
        sb_layout.addLayout(lang_row)

        # Status dot
        self.status_label = QLabel("● Idle")
        self.status_label.setFont(QFont("Segoe UI", 8))
        self.status_label.setStyleSheet("color: #5a6a8a; padding: 0 8px; margin-top: 6px;")
        sb_layout.addWidget(self.status_label)

        version = QLabel("v1.0")
        version.setFont(QFont("Segoe UI", 8))
        version.setStyleSheet("color: #3a4a5a; padding: 0 8px;")
        sb_layout.addWidget(version)

        root.addWidget(sidebar)

        # ── Divider ──────────────────────────────────────────────────────────
        div = QFrame()
        div.setFixedWidth(1)
        div.setStyleSheet("background: #2a3050;")
        root.addWidget(div)

        # ── Content stack ─────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #f4f6fa;")

        self.tab_run       = RunTab(self.settings, self)
        self.tab_queries   = QueriesTab(self.settings, self)
        self.tab_amazon    = AmazonTab(self.settings, self)
        self.tab_scheduler = SchedulerTab(self.settings, self)
        self.tab_history   = HistoryTab(self.settings, self)
        self.tab_settings  = SettingsTab(self.settings, self)

        for tab in [self.tab_run, self.tab_queries, self.tab_amazon,
                    self.tab_scheduler, self.tab_history, self.tab_settings]:
            self.stack.addWidget(tab)

        root.addWidget(self.stack, 1)

        # Page map
        self._page_map = {
            "Run": 0, "Queries": 1, "Amazon": 2,
            "Scheduler": 3, "History": 4, "Settings": 5
        }

    def _lang_btn(self, text, active):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setFixedSize(52, 26)
        btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._style_lang_btn(btn, active)
        return btn

    def _style_lang_btn(self, btn, active):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: #2979FF;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-weight: 700;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: #2a3050;
                    color: #7a8aaa;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background: #343d5c; color: #aaa; }
            """)

    def _set_lang(self, lang):
        self._style_lang_btn(self.btn_en, lang == "en")
        self._style_lang_btn(self.btn_ru, lang == "ru")
        self.btn_en.setChecked(lang == "en")
        self.btn_ru.setChecked(lang == "ru")

    def _on_nav(self, label):
        for btn in self._nav_buttons:
            btn.setChecked(btn.text() == label)
        self.stack.setCurrentIndex(self._page_map[label])

    def set_status(self, text, color="#5a6a8a"):
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(
            f"color: {color}; padding: 0 8px; margin-top: 6px;")

    def save_settings(self):
        self.settings.save_all()
