import sqlite3
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QFrame,
    QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from ui.styles import (
    page_title, card, section_title,
    danger_btn, secondary_btn,
    BG_PAGE, ACCENT, TEXT_SUB, TEXT_MAIN, BORDER
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "history.db"

# Colour for Amazon sessions in the list
AMAZON_COLOR = "#e65c00"
BROWSE_COLOR = "#1a73e8"


class HistoryTab(QWidget):
    def __init__(self, settings, main_window):
        super().__init__()
        self.settings    = settings
        self.main_window = main_window
        self._sessions_data = []
        self.setStyleSheet(f"background: {BG_PAGE};")
        self._ensure_db()
        self._build_ui()
        self.refresh()

    def _ensure_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id       INTEGER PRIMARY KEY AUTOINCREMENT,
                        date     TEXT,
                        type     TEXT,
                        duration INTEGER,
                        status   TEXT,
                        details  TEXT
                    )
                """)
        except Exception:
            pass

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        # Title + buttons
        title_row = QHBoxLayout()
        title_row.addWidget(page_title("Session History"))
        title_row.addStretch()
        btn_clear = danger_btn("Clear All")
        btn_clear.setFixedWidth(100)
        btn_clear.clicked.connect(self._clear_all)
        btn_refresh = secondary_btn("Refresh")
        btn_refresh.setFixedWidth(90)
        btn_refresh.clicked.connect(self.refresh)
        title_row.addWidget(btn_clear)
        title_row.addWidget(btn_refresh)
        outer.addLayout(title_row)

        # ── Stats bar (now with Amazon-specific counter) ──────────────────
        stats_card = card()
        stats_lay  = QHBoxLayout(stats_card)
        stats_lay.setContentsMargins(24, 16, 24, 16)
        stats_lay.setSpacing(0)
        self._stat_widgets = {}
        for key, label in [
            ("total",     "Total"),
            ("completed", "Completed"),
            ("stopped",   "Stopped"),
            ("amazon",    "Amazon"),
            ("minutes",   "Total Minutes"),
        ]:
            frame = QFrame()
            frame.setStyleSheet("border: none; background: none;")
            flay  = QVBoxLayout(frame)
            flay.setContentsMargins(0, 0, 0, 0)
            flay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("0")
            val.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
            # Amazon count uses the orange accent
            color = AMAZON_COLOR if key == "amazon" else ACCENT
            val.setStyleSheet(f"color: {color};")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {TEXT_SUB};")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            flay.addWidget(val)
            flay.addWidget(lbl)
            self._stat_widgets[key] = val
            stats_lay.addWidget(frame, 1)
        outer.addWidget(stats_card)

        # Sessions list + detail
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        # ── Sessions list ─────────────────────────────────────────────────
        list_card = card()
        list_lay  = QVBoxLayout(list_card)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_hdr = QLabel("Sessions")
        list_hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        list_hdr.setStyleSheet(
            f"color: {TEXT_MAIN}; padding: 14px 16px 8px 16px;"
            f" border-bottom: 1px solid {BORDER};")
        list_lay.addWidget(list_hdr)
        self.session_list = QListWidget()
        self.session_list.setStyleSheet(f"""
            QListWidget {{
                border: none; background: white;
                font-family: 'Segoe UI'; font-size: 9pt; outline: none;
            }}
            QListWidget::item {{
                padding: 10px 16px; border-bottom: 1px solid #f4f6fa;
            }}
            QListWidget::item:selected {{ background: #e8f0fe; color: {TEXT_MAIN}; }}
            QListWidget::item:hover:!selected {{ background: #f8f9fc; }}
        """)
        self.session_list.currentRowChanged.connect(self._on_session_selected)
        list_lay.addWidget(self.session_list)
        content_row.addWidget(list_card, 1)

        # ── Detail panel ──────────────────────────────────────────────────
        detail_card = card()
        detail_lay  = QVBoxLayout(detail_card)
        detail_lay.setContentsMargins(0, 0, 0, 0)
        self._detail_hdr = QLabel("Select a session")
        self._detail_hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._detail_hdr.setStyleSheet(
            f"color: {TEXT_MAIN}; padding: 14px 16px 8px 16px;"
            f" border-bottom: 1px solid {BORDER};")
        detail_lay.addWidget(self._detail_hdr)
        self.detail_area = QLabel("")
        self.detail_area.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail_area.setWordWrap(True)
        self.detail_area.setFont(QFont("Segoe UI", 9))
        self.detail_area.setStyleSheet(
            f"color: {TEXT_MAIN}; padding: 16px; background: white;")
        detail_lay.addWidget(self.detail_area, 1)
        content_row.addWidget(detail_card, 1)

        outer.addLayout(content_row, 1)

    def refresh(self):
        self._sessions_data = []
        self.session_list.clear()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT id,date,type,duration,status,details "
                    "FROM sessions ORDER BY id DESC LIMIT 200"
                ).fetchall()
        except Exception:
            rows = []

        total     = len(rows)
        completed = sum(1 for r in rows if r[4] == "completed")
        stopped   = sum(1 for r in rows if r[4] == "stopped")
        amazon    = sum(1 for r in rows if (r[2] or "").lower() == "amazon")
        minutes   = sum(r[3] or 0 for r in rows)

        self._stat_widgets["total"].setText(str(total))
        self._stat_widgets["completed"].setText(str(completed))
        self._stat_widgets["stopped"].setText(str(stopped))
        self._stat_widgets["amazon"].setText(str(amazon))
        self._stat_widgets["minutes"].setText(str(minutes))

        for row in rows:
            self._sessions_data.append(row)
            sid, date, stype, duration, status, _ = row
            stype = stype or "Browse"

            # Icon by status
            if status == "completed":
                icon = "✅"
            elif status == "stopped":
                icon = "⏹"
            else:
                icon = "⚠️"

            # Type badge
            type_badge = f"[{stype}]"

            item = QListWidgetItem(
                f"{icon}  {date or '—'}  {type_badge}  •  {duration or 0} min"
            )

            # Colour Amazon rows differently
            if stype.lower() == "amazon":
                item.setForeground(QColor(AMAZON_COLOR))
            else:
                item.setForeground(QColor(TEXT_MAIN))

            self.session_list.addItem(item)

    def _on_session_selected(self, row):
        if row < 0 or row >= len(self._sessions_data):
            return
        sid, date, stype, duration, status, details = self._sessions_data[row]
        stype = stype or "Browse"

        # Header colour
        color = AMAZON_COLOR if stype.lower() == "amazon" else BROWSE_COLOR
        self._detail_hdr.setText(f"Session #{sid}  [{stype}]")
        self._detail_hdr.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 10pt;"
            f" padding: 14px 16px 8px 16px; border-bottom: 1px solid {BORDER};"
        )

        # Status emoji
        status_icon = {"completed": "✅ Completed",
                       "stopped":   "⏹ Stopped",
                       "partial":   "⚠️ Partial"}.get(status, status or "—")

        self.detail_area.setText(
            f"Date:      {date or '—'}\n"
            f"Type:      {stype}\n"
            f"Duration:  {duration or 0} minutes\n"
            f"Status:    {status_icon}\n\n"
            f"Details:\n{details or '—'}"
        )

    def _clear_all(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Delete all session history? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("DELETE FROM sessions")
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self.refresh()