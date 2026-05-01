import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QScrollArea, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from ui.styles import (
    page_title, card, section_title, sub_label,
    styled_slider, styled_checkbox, primary_btn, danger_btn,
    success_btn, secondary_btn, scroll_wrap, BG_PAGE, ACCENT, TEXT_SUB, TEXT_MAIN
)


CATEGORIES = [
    "News & Events", "Weather", "YouTube", "Reddit",
    "Wikipedia", "Shopping", "Food & Recipes", "Health & Wellness",
    "Travel & Tourism", "Technology",
]


class RunTab(QWidget):
    _sig_progress = pyqtSignal(str, int)
    _sig_status   = pyqtSignal(str, str)

    def __init__(self, settings, main_window):
        super().__init__()
        self.settings    = settings
        self.main_window = main_window
        self._worker     = None
        self._stop_event = None
        self._elapsed    = 0
        self._timer      = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._sig_progress.connect(self._on_progress)
        self._sig_status.connect(self._on_status)

        self.setStyleSheet(f"background: {BG_PAGE};")
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {BG_PAGE};")

        content = QWidget()
        content.setStyleSheet(f"background: {BG_PAGE};")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(28, 24, 28, 24)
        vbox.setSpacing(16)

        # Title + Firefox status
        title_row = QHBoxLayout()
        title_row.addWidget(page_title("Run Session"))
        title_row.addStretch()
        self.firefox_label = QLabel("Checking Firefox paths...")
        self.firefox_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.firefox_label.setStyleSheet("color: #f59e0b;")
        title_row.addWidget(self.firefox_label)
        vbox.addLayout(title_row)

        # ── Browse Categories ──────────────────────────────────────────────
        vbox.addWidget(self._build_categories_card())

        # ── Session Timings ────────────────────────────────────────────────
        vbox.addWidget(self._build_timings_card())

        # ── Queries Per Category ───────────────────────────────────────────
        vbox.addWidget(self._build_queries_card())

        # ── Progress ───────────────────────────────────────────────────────
        vbox.addWidget(self._build_progress_card())

        vbox.addStretch()

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_start = success_btn("Start Session")
        self.btn_start.setFixedWidth(160)
        self.btn_start.clicked.connect(self._start)

        self.btn_stop = danger_btn("Stop")
        self.btn_stop.setFixedWidth(100)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        vbox.addLayout(btn_row)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._check_firefox()

    def _build_categories_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section_title("Browse Categories"))

        # Select All / Deselect All
        btn_row = QHBoxLayout()
        btn_sel = secondary_btn("Select All")
        btn_sel.setFixedWidth(100)
        btn_sel.clicked.connect(lambda: self._set_all(True))
        btn_des = secondary_btn("Deselect All")
        btn_des.setFixedWidth(110)
        btn_des.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(btn_sel)
        btn_row.addWidget(btn_des)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Checkboxes in 2 columns
        grid = QGridLayout()
        grid.setSpacing(8)
        self._cat_checks = {}
        for i, cat in enumerate(CATEGORIES):
            cb = styled_checkbox(cat)
            self._cat_checks[cat] = cb
            grid.addWidget(cb, i // 2, i % 2)
        lay.addLayout(grid)
        return c

    def _build_timings_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section_title("Session Timings"))

        self.sl_browse1 = self._slider_row(lay, "Browse 1 (minutes)", 1, 60, 15)
        self.sl_idle    = self._slider_row(lay, "Idle pause (minutes)", 1, 30, 8)
        self.sl_browse2 = self._slider_row(lay, "Browse 2 (minutes)", 1, 60, 20)
        return c

    def _build_queries_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section_title("Queries Per Category"))

        self.sl_qmin = self._slider_row(lay, "Minimum queries", 1, 30, 5)
        self.sl_qmax = self._slider_row(lay, "Maximum queries", 1, 50, 15)
        return c

    def _build_progress_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
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
            QProgressBar {{
                background: #e0e5f0;
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {ACCENT};
                border-radius: 4px;
            }}
        """)
        lay.addWidget(self.progress_bar)

        self.elapsed_label = QLabel("Elapsed: 0:00")
        self.elapsed_label.setFont(QFont("Segoe UI", 9))
        self.elapsed_label.setStyleSheet(f"color: {TEXT_SUB};")
        lay.addWidget(self.elapsed_label)
        return c

    def _slider_row(self, parent_layout, label, min_v, max_v, default):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        lbl.setFixedWidth(180)

        sl = styled_slider(min_v, max_v, default)

        val_lbl = QLabel(str(default))
        val_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {ACCENT}; min-width: 28px;")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        sl.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))

        row.addWidget(lbl)
        row.addWidget(sl, 1)
        row.addWidget(val_lbl)
        parent_layout.addLayout(row)
        return sl

    def _set_all(self, checked):
        for cb in self._cat_checks.values():
            cb.setChecked(checked)

    def _check_firefox(self):
        try:
            from core.settings import Settings
            s = self.settings
            import os
            if os.path.exists(s.firefox_binary) and os.path.exists(s.geckodriver):
                self.firefox_label.setText("Firefox paths configured correctly.")
                self.firefox_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            else:
                self.firefox_label.setText("Firefox paths not configured.")
                self.firefox_label.setStyleSheet("color: #c62828; font-weight: bold;")
        except Exception:
            self.firefox_label.setText("")

    def _get_selected_categories(self):
        return [cat for cat, cb in self._cat_checks.items() if cb.isChecked()]

    def _start(self):
        cats = self._get_selected_categories()
        if not cats:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No categories", "Select at least one category.")
            return

        import threading
        from core.session_manager import SessionManager

        self._stop_event = threading.Event()
        self._elapsed = 0
        self.progress_bar.setValue(0)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.main_window.set_status("Running", "#2979FF")

        config = {
            "categories":    cats,
            "browse1_min":   self.sl_browse1.value(),
            "idle_min":      self.sl_idle.value(),
            "browse2_min":   self.sl_browse2.value(),
            "queries_min":   self.sl_qmin.value(),
            "queries_max":   self.sl_qmax.value(),
        }

        def worker():
            try:
                mgr = SessionManager(self.settings, self._stop_event,
                                     on_progress=self._emit_progress,
                                     on_status=self._emit_status)
                mgr.run(config)
            except Exception as e:
                self._emit_status(f"Error: {e}", "#c62828")
            finally:
                self._emit_status("Idle", "#5a6a8a")
                self._emit_progress("Done", 100)

        self._timer.start(1000)
        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _stop(self):
        if self._stop_event:
            self._stop_event.set()
        self._timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.main_window.set_status("Idle", "#5a6a8a")

    def _tick(self):
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        self.elapsed_label.setText(f"Elapsed: {m}:{s:02d}")

    def _emit_progress(self, text, pct):
        self._sig_progress.emit(text, pct)

    def _emit_status(self, text, color):
        self._sig_status.emit(text, color)

    def _on_progress(self, text, pct):
        self.progress_label.setText(text)
        self.progress_bar.setValue(pct)
        if pct >= 100:
            self._timer.stop()
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def _on_status(self, text, color):
        self.main_window.set_status(text, color)
