import threading
import time
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QScrollArea, QFrame, QProgressBar,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.styles import (
    page_title, card, section_title, sub_label,
    styled_slider, styled_checkbox, primary_btn, danger_btn,
    success_btn, secondary_btn, scroll_wrap,
    BG_PAGE, ACCENT, ACCENT2, TEXT_SUB, TEXT_MAIN, BORDER
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "history.db"


AMAZON_CATEGORIES = [
    "Electronics", "Computers & Laptops", "Cell Phones & Accessories",
    "Home & Kitchen", "Clothing & Fashion", "Sports & Outdoors",
    "Books", "Toys & Games", "Beauty & Personal Care",
    "Health & Household", "Automotive", "Garden & Outdoor",
    "Pet Supplies", "Office Products", "Tools & Home Improvement",
    "Baby Products", "Food & Grocery", "Video Games & Consoles",
    "Movies & TV Shows", "Musical Instruments",
]

# ==============================================================================
# HISTORY HELPERS  (write directly to the same DB that HistoryTab reads)
# ==============================================================================

def _ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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


def _save_amazon_session(start_time: float, end_time: float,
                          categories: list, status: str,
                          tabs_visited: int, queries_done: int):
    """
    Insert one row into the sessions table for a completed Amazon session.
    """
    try:
        _ensure_db()
        duration_m = max(1, round((end_time - start_time) / 60))
        date_str   = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M")
        cats_str   = ", ".join(categories) if categories else "—"
        details    = (
            f"Categories: {cats_str}\n"
            f"Tabs visited: {tabs_visited}\n"
            f"Queries run: {queries_done}\n"
            f"Started:  {datetime.fromtimestamp(start_time).strftime('%H:%M:%S')}\n"
            f"Finished: {datetime.fromtimestamp(end_time).strftime('%H:%M:%S')}"
        )
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO sessions (date, type, duration, status, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (date_str, "Amazon", duration_m, status, details)
            )
    except Exception:
        pass  # never crash the UI over a history write


# ==============================================================================
# AMAZON TAB
# ==============================================================================

class AmazonTab(QWidget):
    _sig_progress        = pyqtSignal(str, int)
    _sig_status          = pyqtSignal(str, str)
    _sig_refresh_history = pyqtSignal()

    def __init__(self, settings, main_window):
        super().__init__()
        self.settings    = settings
        self.main_window = main_window
        self._stop_event = None
        self._queries    = {}
        self._current_cat = None

        # Session tracking counters (updated from worker thread)
        self._session_tabs_visited  = 0
        self._session_queries_done  = 0

        self._sig_progress.connect(self._on_progress)
        self._sig_status.connect(self._on_status)
        self._sig_refresh_history.connect(self._on_refresh_history)

        self.setStyleSheet(f"background: {BG_PAGE};")
        self._load_queries()
        self._build_ui()

    def _load_queries(self):
        path = DATA_DIR / "amazon_queries.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._queries = json.load(f)
            except Exception:
                self._queries = {}

    def _save_queries(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / "amazon_queries.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._queries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save Error", str(e))

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        # ── Title row ─────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_lbl = page_title("Amazon Warmer")
        title_row.addWidget(title_lbl)
        info = QLabel("amazon.com  •  no login required")
        info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet(f"color: {TEXT_SUB};")
        title_row.addWidget(info)
        title_row.addStretch()
        self.firefox_label = QLabel("")
        self.firefox_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_row.addWidget(self.firefox_label)
        outer.addLayout(title_row)

        # ── Main splitter: left config | right query editor ────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #e0e5f0; width: 1px; }")

        # Left panel
        left_widget = QWidget()
        left_widget.setStyleSheet(f"background: {BG_PAGE};")
        left_vbox = QVBoxLayout(left_widget)
        left_vbox.setContentsMargins(0, 0, 8, 0)
        left_vbox.setSpacing(12)

        left_vbox.addWidget(self._build_categories_card())
        left_vbox.addWidget(self._build_session_card())
        left_vbox.addWidget(self._build_progress_card())
        left_vbox.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_start = success_btn("Start Amazon Session")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = danger_btn("Stop")
        self.btn_stop.setFixedWidth(90)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        left_vbox.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # Right panel — Query Editor
        right_widget = QWidget()
        right_widget.setStyleSheet(f"background: {BG_PAGE};")
        right_vbox = QVBoxLayout(right_widget)
        right_vbox.setContentsMargins(8, 0, 0, 0)
        right_vbox.setSpacing(12)
        right_vbox.addWidget(self._build_query_editor())
        splitter.addWidget(right_widget)

        splitter.setSizes([420, 580])
        outer.addWidget(splitter, 1)

        self._check_firefox()

    def _build_categories_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lay.addWidget(section_title("Active Categories"))

        btn_row = QHBoxLayout()
        btn_all = secondary_btn("All")
        btn_all.setFixedWidth(60)
        btn_all.clicked.connect(lambda: self._set_all_cats(True))
        btn_none = secondary_btn("None")
        btn_none.setFixedWidth(60)
        btn_none.clicked.connect(lambda: self._set_all_cats(False))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._cat_checks = {}
        for i, cat in enumerate(AMAZON_CATEGORIES):
            cb = styled_checkbox(cat, ACCENT2)
            self._cat_checks[cat] = cb
            grid.addWidget(cb, i // 2, i % 2)

        self._own_requests_cb = styled_checkbox("⭐ Own Requests", ACCENT2)
        self._own_requests_cb.setStyleSheet(
            self._own_requests_cb.styleSheet() +
            f" QCheckBox {{ color: {ACCENT2}; font-weight: bold; }}"
        )
        grid.addWidget(self._own_requests_cb,
                       len(AMAZON_CATEGORIES) // 2 + 1, 0, 1, 2)

        lay.addLayout(grid)
        return c

    def _build_session_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lay.addWidget(section_title("Session Settings"))

        row = QHBoxLayout()
        lbl = QLabel("Session duration (minutes)")
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        row.addWidget(lbl)
        self.sl_duration = styled_slider(5, 120, 30, ACCENT2)
        self.val_duration = QLabel("30")
        self.val_duration.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.val_duration.setStyleSheet(f"color: {ACCENT2}; min-width: 28px;")
        self.sl_duration.valueChanged.connect(
            lambda v: self.val_duration.setText(str(v)))
        row.addWidget(self.sl_duration, 1)
        row.addWidget(self.val_duration)
        lay.addLayout(row)

        self.cb_reviews = styled_checkbox("Read product reviews", ACCENT2)
        self.cb_reviews.setChecked(True)
        lay.addWidget(self.cb_reviews)
        return c

    def _build_progress_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(section_title("Progress"))

        self.progress_label = QLabel("—")
        self.progress_label.setFont(QFont("Segoe UI", 9))
        self.progress_label.setStyleSheet(f"color: {TEXT_SUB};")
        lay.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: #e0e5f0; border-radius: 4px; border: none; }}
            QProgressBar::chunk {{ background: {ACCENT2}; border-radius: 4px; }}
        """)
        lay.addWidget(self.progress_bar)

        self.elapsed_label = QLabel("Elapsed: 0:00")
        self.elapsed_label.setFont(QFont("Segoe UI", 9))
        self.elapsed_label.setStyleSheet(f"color: {TEXT_SUB};")
        lay.addWidget(self.elapsed_label)
        return c

    def _build_query_editor(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(section_title("Query Editor"))
        hint = QLabel("Click a category to view/edit its queries")
        hint.setFont(QFont("Segoe UI", 8))
        hint.setStyleSheet(f"color: {TEXT_SUB};")
        hdr.addWidget(hint)
        hdr.addStretch()

        self.btn_save_q = secondary_btn("Save")
        self.btn_save_q.setFixedWidth(70)
        self.btn_save_q.clicked.connect(self._save_current_queries)

        self.btn_delete_q = danger_btn("Delete")
        self.btn_delete_q.setFixedWidth(80)
        self.btn_delete_q.clicked.connect(self._delete_selected_query)

        self.btn_add_q = primary_btn("+ Add")
        self.btn_add_q.setFixedWidth(80)
        self.btn_add_q.clicked.connect(self._add_query)

        hdr.addWidget(self.btn_save_q)
        hdr.addWidget(self.btn_delete_q)
        hdr.addWidget(self.btn_add_q)
        lay.addLayout(hdr)

        split = QHBoxLayout()
        split.setSpacing(12)

        cat_frame = QFrame()
        cat_frame.setStyleSheet(f"""
            QFrame {{
                background: #f8f9fc;
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        cat_vbox = QVBoxLayout(cat_frame)
        cat_vbox.setContentsMargins(0, 0, 0, 0)
        cat_hdr = QLabel("Categories")
        cat_hdr.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        cat_hdr.setStyleSheet(f"color: {TEXT_SUB}; padding: 8px 12px 4px 12px;")
        cat_vbox.addWidget(cat_hdr)

        self.cat_list = QListWidget()
        self.cat_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 6px 12px;
                color: {TEXT_MAIN};
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background: {ACCENT2};
                color: white;
            }}
            QListWidget::item:hover:!selected {{
                background: #f0f2f8;
            }}
        """)
        for cat in AMAZON_CATEGORIES:
            self.cat_list.addItem(cat)
        own = QListWidgetItem("⭐ Own Requests")
        own.setForeground(__import__('PyQt6.QtGui', fromlist=['QColor']).QColor(ACCENT2))
        self.cat_list.addItem(own)
        self.cat_list.currentRowChanged.connect(self._on_cat_selected)
        cat_vbox.addWidget(self.cat_list)
        split.addWidget(cat_frame, 2)

        q_frame = QFrame()
        q_frame.setStyleSheet(f"""
            QFrame {{
                background: #f8f9fc;
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        q_vbox = QVBoxLayout(q_frame)
        q_vbox.setContentsMargins(0, 0, 0, 0)

        self.query_header = QLabel("← Select a category")
        self.query_header.setFont(QFont("Segoe UI", 9))
        self.query_header.setStyleSheet(
            f"color: {TEXT_SUB}; padding: 8px 12px 4px 12px;")
        q_vbox.addWidget(self.query_header)

        self.query_list = QListWidget()
        self.query_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 5px 12px;
                color: {TEXT_MAIN};
            }}
            QListWidget::item:selected {{
                background: #e8f0fe;
                color: {TEXT_MAIN};
            }}
        """)
        self.query_list.currentRowChanged.connect(self._on_query_selected)
        q_vbox.addWidget(self.query_list, 1)

        edit_lbl = QLabel("Edit selected query:")
        edit_lbl.setFont(QFont("Segoe UI", 8))
        edit_lbl.setStyleSheet(f"color: {TEXT_SUB}; padding: 4px 12px 0 12px;")
        q_vbox.addWidget(edit_lbl)

        self.query_edit = QTextEdit()
        self.query_edit.setFixedHeight(60)
        self.query_edit.setStyleSheet(f"""
            QTextEdit {{
                border: none;
                border-top: 1px solid {BORDER};
                background: white;
                font-family: 'Segoe UI';
                font-size: 9pt;
                padding: 6px 12px;
            }}
        """)
        q_vbox.addWidget(self.query_edit)
        split.addWidget(q_frame, 3)

        lay.addLayout(split, 1)
        return c

    # ── Query editor handlers ──────────────────────────────────────────────

    def _on_cat_selected(self, row):
        if row < 0:
            return
        items = AMAZON_CATEGORIES + ["Own Requests"]
        if row < len(items):
            self._current_cat = items[row]
        else:
            return
        n = len(self._queries.get(self._current_cat, []))
        self.query_header.setText(f"{self._current_cat} — {n} queries")
        self.query_list.clear()
        for q in self._queries.get(self._current_cat, []):
            self.query_list.addItem(q)

    def _on_query_selected(self, row):
        if row < 0 or not self._current_cat:
            return
        qs = self._queries.get(self._current_cat, [])
        if row < len(qs):
            self.query_edit.setPlainText(qs[row])

    def _add_query(self):
        if not self._current_cat:
            return
        text = self.query_edit.toPlainText().strip()
        if not text:
            return
        if self._current_cat not in self._queries:
            self._queries[self._current_cat] = []
        self._queries[self._current_cat].append(text)
        self.query_list.addItem(text)
        self.query_edit.clear()
        self._update_cat_header()

    def _delete_selected_query(self):
        if not self._current_cat:
            return
        row = self.query_list.currentRow()
        if row < 0:
            return
        self.query_list.takeItem(row)
        qs = self._queries.get(self._current_cat, [])
        if row < len(qs):
            qs.pop(row)
        self._update_cat_header()

    def _save_current_queries(self):
        if self._current_cat:
            qs = [self.query_list.item(i).text()
                  for i in range(self.query_list.count())]
            self._queries[self._current_cat] = qs
        self._save_queries()
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Saved", "Queries saved successfully.")

    def _update_cat_header(self):
        if self._current_cat:
            n = len(self._queries.get(self._current_cat, []))
            self.query_header.setText(f"{self._current_cat} — {n} queries")

    def _set_all_cats(self, checked):
        for cb in self._cat_checks.values():
            cb.setChecked(checked)
        self._own_requests_cb.setChecked(checked)

    def _get_selected_categories(self):
        cats = [cat for cat, cb in self._cat_checks.items() if cb.isChecked()]
        if self._own_requests_cb.isChecked():
            cats.append("Own Requests")
        return cats

    def _check_firefox(self):
        try:
            import os
            s = self.settings
            if os.path.exists(s.firefox_binary) and os.path.exists(s.geckodriver):
                self.firefox_label.setText("Firefox paths configured correctly.")
                self.firefox_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            else:
                self.firefox_label.setText("Firefox paths not configured.")
                self.firefox_label.setStyleSheet("color: #c62828; font-weight: bold;")
        except Exception:
            self.firefox_label.setText("")

    # ── Session start / stop ───────────────────────────────────────────────

    def _start(self):
        cats = self._get_selected_categories()
        if not cats:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No categories",
                                "Select at least one Amazon category.")
            return

        self._stop_event = threading.Event()

        # Reset per-session counters
        self._session_tabs_visited = 0
        self._session_queries_done = 0

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.main_window.set_status("Amazon Running", ACCENT2)

        from core.amazon_engine import AmazonSessionConfig, run_amazon_session
        from core import browser_bot as bot

        # Wrap on_progress to count queries
        def _counting_progress(text, pct):
            # Heuristic: each "Searching Amazon:" line = one query done
            if text.startswith("Searching Amazon:"):
                self._session_queries_done += 1
            # Each "tabs:" line tells us how many tabs were opened
            if "tabs:" in text and text[0].isdigit():
                try:
                    n = int(text.split(" tabs:")[0].strip())
                    self._session_tabs_visited += n
                except Exception:
                    pass
            self._emit_progress(text, pct)

        cfg = AmazonSessionConfig(
            categories=cats,
            session_minutes=self.sl_duration.value(),
            read_reviews=self.cb_reviews.isChecked(),
            stop_event=self._stop_event,
            on_progress=_counting_progress,
        )

        def worker():
            driver     = None
            start_time = time.time()
            status     = "stopped"
            try:
                driver = bot.create_driver(
                    self.settings.firefox_binary,
                    self.settings.firefox_profile,
                    self.settings.geckodriver,
                )
                bot.set_captcha_handler(None, self._stop_event)
                run_amazon_session(driver, cfg)
                status = "stopped" if self._stop_event.is_set() else "completed"
            except Exception as e:
                status = "partial"
                self._emit_progress(f"Error: {e}", 0)
            finally:
                end_time = time.time()
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                try:
                    bot.clear_captcha_handler()
                except Exception:
                    pass

                # ── Save to history DB ────────────────────────────────
                try:
                    _save_amazon_session(
                        start_time=start_time,
                        end_time=end_time,
                        categories=cats,
                        status=status,
                        tabs_visited=self._session_tabs_visited,
                        queries_done=self._session_queries_done,
                    )
                except Exception:
                    pass

                # ── Tell the History tab to refresh ───────────────────
                try:
                    history_tab = self.main_window.get_tab("history")
                    if history_tab and hasattr(history_tab, "refresh"):
                        self._sig_refresh_history.emit()
                except Exception:
                    pass

                self._emit_status("Idle", "#5a6a8a")

        threading.Thread(target=worker, daemon=True).start()

        # Start elapsed-time ticker
        self._start_time = time.time()
        self._tick_elapsed()

    def _tick_elapsed(self):
        """Update the elapsed label every second while running."""
        if self._stop_event and not self._stop_event.is_set():
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            self.elapsed_label.setText(f"Elapsed: {m}:{s:02d}")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1000, self._tick_elapsed)

    def _stop(self):
        if self._stop_event:
            self._stop_event.set()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.main_window.set_status("Idle", "#5a6a8a")

    # ── Signal emitters (thread-safe) ──────────────────────────────────────

    def _emit_progress(self, text, pct):
        self._sig_progress.emit(text, int(pct))

    def _emit_status(self, text, color):
        self._sig_status.emit(text, color)

    def _on_progress(self, text, pct):
        self.progress_label.setText(text)
        self.progress_bar.setValue(pct)
        if pct >= 100:
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def _on_status(self, text, color):
        self.main_window.set_status(text, color)
    def _on_refresh_history(self):
        """Called from worker thread via signal — safely refresh History tab."""
        try:
            history_tab = self.main_window.get_tab("history")
            if history_tab and hasattr(history_tab, "refresh"):
                history_tab.refresh()
        except Exception:
            pass
