import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QLineEdit, QMessageBox, QScrollArea, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ui.styles import (
    page_title, card, section_title,
    primary_btn, danger_btn, success_btn, secondary_btn,
    BG_PAGE, ACCENT, TEXT_SUB, TEXT_MAIN, BORDER
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR  = BASE_DIR / "data"
DAYS      = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAYS_FULL = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]


class SchedulerTab(QWidget):
    def __init__(self, settings, main_window):
        super().__init__()
        self.settings     = settings
        self.main_window  = main_window
        self._jobs        = []
        self._enabled     = False
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check_schedule)
        self.setStyleSheet(f"background: {BG_PAGE};")
        self._load_jobs()
        self._build_ui()

    # ── Persistence ───────────────────────────────────────────────────────
    def _load_jobs(self):
        self._jobs    = self.settings.get("scheduled_jobs", [])
        self._enabled = self.settings.get("scheduler_enabled", False)

    def _save_jobs(self):
        self.settings.set("scheduled_jobs",    self._jobs)
        self.settings.set("scheduler_enabled", self._enabled)
        self.settings.save_all()

    # ── UI ────────────────────────────────────────────────────────────────
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

        vbox.addWidget(page_title("Scheduler"))
        vbox.addWidget(self._build_status_card())
        vbox.addWidget(self._build_add_job_card())

        # Jobs list card
        jobs_card = card()
        jobs_lay  = QVBoxLayout(jobs_card)
        jobs_lay.setContentsMargins(20, 16, 20, 16)
        jobs_lay.setSpacing(8)
        jobs_lay.addWidget(section_title("Scheduled Jobs"))
        self.jobs_container = QVBoxLayout()
        self.jobs_container.setSpacing(6)
        jobs_lay.addLayout(self.jobs_container)
        vbox.addWidget(jobs_card)

        vbox.addWidget(self._build_note_card())
        vbox.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._refresh_jobs_ui()
        if self._enabled:
            self._check_timer.start(60000)

    def _build_status_card(self):
        c   = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(section_title("Scheduler Status"))

        self.status_lbl = QLabel("Scheduler is ON" if self._enabled else "Scheduler is OFF")
        self.status_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_lbl.setStyleSheet(f"color: {'#2e7d32' if self._enabled else TEXT_SUB};")
        lay.addWidget(self.status_lbl)

        self.next_run_lbl = QLabel("Next run: —")
        self.next_run_lbl.setFont(QFont("Segoe UI", 9))
        self.next_run_lbl.setStyleSheet(f"color: {TEXT_SUB};")
        lay.addWidget(self.next_run_lbl)

        self.btn_toggle = success_btn(
            "Disable Scheduler" if self._enabled else "Enable Scheduler")
        self.btn_toggle.setFixedWidth(180)
        self.btn_toggle.clicked.connect(self._toggle_scheduler)
        lay.addWidget(self.btn_toggle)
        return c

    def _build_add_job_card(self):
        c   = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section_title("Add Scheduled Run"))

        # Days row
        days_row = QHBoxLayout()
        days_lbl = QLabel("Days of week:")
        days_lbl.setFont(QFont("Segoe UI", 9))
        days_lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        days_row.addWidget(days_lbl)
        self._day_checks = {}
        for day in DAYS:
            cb = QCheckBox(day)
            cb.setFont(QFont("Segoe UI", 9))
            cb.setStyleSheet(f"""
                QCheckBox {{ color: {TEXT_MAIN}; spacing: 4px; }}
                QCheckBox::indicator {{
                    width: 16px; height: 16px; border-radius: 3px;
                    border: 2px solid #c0c8d8; background: white;
                }}
                QCheckBox::indicator:checked {{
                    background: {ACCENT}; border-color: {ACCENT};
                }}
            """)
            self._day_checks[day] = cb
            days_row.addWidget(cb)
        days_row.addStretch()
        lay.addLayout(days_row)

        # Time row
        time_row = QHBoxLayout()
        time_lbl = QLabel("Time (HH:MM):")
        time_lbl.setFont(QFont("Segoe UI", 9))
        time_lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        time_row.addWidget(time_lbl)
        self.hour_edit = QLineEdit("09")
        self.hour_edit.setFixedSize(52, 32)
        self.hour_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hour_edit.setStyleSheet(self._input_style())
        colon = QLabel(":")
        colon.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.min_edit = QLineEdit("00")
        self.min_edit.setFixedSize(52, 32)
        self.min_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.min_edit.setStyleSheet(self._input_style())
        time_row.addWidget(self.hour_edit)
        time_row.addWidget(colon)
        time_row.addWidget(self.min_edit)
        time_row.addStretch()
        lay.addLayout(time_row)

        # Label row
        label_row = QHBoxLayout()
        label_lbl = QLabel("Label (optional):")
        label_lbl.setFont(QFont("Segoe UI", 9))
        label_lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        label_row.addWidget(label_lbl)
        self.label_edit = QLineEdit()
        self.label_edit.setFixedHeight(32)
        self.label_edit.setPlaceholderText("e.g. Morning warmup")
        self.label_edit.setStyleSheet(self._input_style())
        label_row.addWidget(self.label_edit, 1)
        lay.addLayout(label_row)

        btn_add = primary_btn("Add Job")
        btn_add.setFixedWidth(100)
        btn_add.clicked.connect(self._add_job)
        lay.addWidget(btn_add)
        return c

    def _build_note_card(self):
        c   = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(4)
        lay.addWidget(section_title("Note"))
        for line in [
            "The scheduler runs while WarmUpPro is open.",
            "Use Windows Task Scheduler to auto-launch WarmUpPro at startup",
            "if you need fully unattended scheduling.",
        ]:
            lbl = QLabel(line)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {TEXT_SUB};")
            lay.addWidget(lbl)
        return c

    def _input_style(self):
        return f"""
            QLineEdit {{
                border: 1px solid {BORDER}; border-radius: 5px;
                background: white; font-family: 'Segoe UI'; font-size: 10pt;
                padding: 0 8px; color: {TEXT_MAIN};
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """

    # ── Logic ─────────────────────────────────────────────────────────────
    def _toggle_scheduler(self):
        self._enabled = not self._enabled
        self.status_lbl.setText(
            "Scheduler is ON" if self._enabled else "Scheduler is OFF")
        self.status_lbl.setStyleSheet(
            f"color: {'#2e7d32' if self._enabled else TEXT_SUB};")
        self.btn_toggle.setText(
            "Disable Scheduler" if self._enabled else "Enable Scheduler")
        if self._enabled:
            self._check_timer.start(60000)
            self._update_next_run()
        else:
            self._check_timer.stop()
            self.next_run_lbl.setText("Next run: —")
        self._save_jobs()

    def _add_job(self):
        days = [d for d, cb in self._day_checks.items() if cb.isChecked()]
        if not days:
            QMessageBox.warning(self, "No days", "Select at least one day.")
            return
        try:
            h = int(self.hour_edit.text())
            m = int(self.min_edit.text())
            assert 0 <= h <= 23 and 0 <= m <= 59
        except Exception:
            QMessageBox.warning(self, "Invalid time", "Enter valid HH:MM (e.g. 09:30).")
            return
        job = {
            "days":  days,
            "time":  f"{h:02d}:{m:02d}",
            "label": self.label_edit.text().strip(),
        }
        self._jobs.append(job)
        self._save_jobs()
        self._refresh_jobs_ui()
        self.label_edit.clear()
        if self._enabled:
            self._update_next_run()

    def _delete_job(self, idx):
        if 0 <= idx < len(self._jobs):
            self._jobs.pop(idx)
            self._save_jobs()
            self._refresh_jobs_ui()
            if self._enabled:
                self._update_next_run()

    def _refresh_jobs_ui(self):
        while self.jobs_container.count():
            item = self.jobs_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._jobs:
            lbl = QLabel("No jobs scheduled.")
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {TEXT_SUB};")
            self.jobs_container.addWidget(lbl)
            return

        for i, job in enumerate(self._jobs):
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background: #f4f6fa; border: 1px solid {BORDER}; border-radius: 6px;
                }}
            """)
            rlay = QHBoxLayout(row)
            rlay.setContentsMargins(12, 8, 12, 8)
            days_str = ", ".join(job.get("days", []))
            label    = job.get("label", "")
            text     = f"{job['time']}  —  {days_str}"
            if label:
                text += f"  |  {label}"
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: none;")
            rlay.addWidget(lbl, 1)
            btn_del = danger_btn("Remove")
            btn_del.setFixedWidth(80)
            btn_del.setFixedHeight(28)
            btn_del.clicked.connect(lambda _, idx=i: self._delete_job(idx))
            rlay.addWidget(btn_del)
            self.jobs_container.addWidget(row)

    def _check_schedule(self):
        from datetime import datetime
        now      = datetime.now()
        day_name = DAYS[now.weekday()]
        cur_time = f"{now.hour:02d}:{now.minute:02d}"
        for job in self._jobs:
            if day_name in job.get("days", []) and job.get("time") == cur_time:
                try:
                    self.main_window.tab_run.btn_start.click()
                except Exception:
                    pass
                break

    def _update_next_run(self):
        from datetime import datetime, timedelta
        if not self._jobs or not self._enabled:
            self.next_run_lbl.setText("Next run: —")
            return
        now      = datetime.now()
        earliest = None
        for job in self._jobs:
            h, m = map(int, job["time"].split(":"))
            for offset in range(7):
                candidate = (now + timedelta(days=offset)).replace(
                    hour=h, minute=m, second=0, microsecond=0)
                if candidate > now and DAYS[candidate.weekday()] in job.get("days", []):
                    if earliest is None or candidate < earliest:
                        earliest = candidate
                    break
        if earliest:
            self.next_run_lbl.setText(
                f"Next run: {earliest.strftime('%A, %d %b at %H:%M')}")
        else:
            self.next_run_lbl.setText("Next run: —")
