"""
ui/tab_scheduler.py  --  Scheduler tab.
"""

import datetime
import threading
import time
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from core.i18n import t

CT_BG    = "#f1f5f9"
CARD_BG  = "#ffffff"
BORDER   = "#e2e8f0"
TEXT_MAIN= "#0f172a"
TEXT_SUB = "#64748b"
ACCENT   = "#3b82f6"
SUCCESS  = "#22c55e"
ERROR    = "#ef4444"
WARNING  = "#f59e0b"

DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday",
           "Friday", "Saturday", "Sunday"]


class SchedulerTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=CT_BG, corner_radius=0)
        self.app = app
        self._sched_thread = None
        self._stop_event   = threading.Event()
        self._jobs = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text=t('scheduler_title'),
                     font=("Helvetica", 20, "bold"),
                     text_color=TEXT_MAIN).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 0))

        body = ctk.CTkScrollableFrame(self, fg_color=CT_BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # Status card
        status_card = self._card(body, row=0, title=t('sched_status_card'))
        self._sched_status = ctk.CTkLabel(
            status_card, text=t('sched_off'),
            font=("Helvetica", 13), text_color=TEXT_SUB)
        self._sched_status.pack(anchor="w", padx=16, pady=(4, 4))
        self._next_lbl = ctk.CTkLabel(
            status_card, text=t('next_run_dash'),
            font=("Helvetica", 12), text_color=TEXT_SUB)
        self._next_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        btn_row = ctk.CTkFrame(status_card, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(0, 12))
        self._toggle_btn = ctk.CTkButton(
            btn_row, text=t('enable_sched'), height=36, width=180,
            font=("Helvetica", 13, "bold"),
            fg_color=SUCCESS, hover_color="#16a34a",
            command=self._toggle_scheduler)
        self._toggle_btn.pack(side="left")

        # Builder card
        builder = self._card(body, row=1, title=t('add_sched_run'))

        ctk.CTkLabel(builder, text=t('days_of_week'),
                     font=("Helvetica", 12), text_color=TEXT_MAIN).pack(
            anchor="w", padx=16, pady=(4, 4))
        day_row = ctk.CTkFrame(builder, fg_color="transparent")
        day_row.pack(fill="x", padx=16, pady=(0, 8))
        self._day_vars = {}
        days_short = t('days_short')
        for i, d in enumerate(DAYS_EN):
            var = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(day_row, text=days_short[i], variable=var, width=60,
                            font=("Helvetica", 11), text_color=TEXT_MAIN,
                            fg_color=ACCENT, checkmark_color="#ffffff").pack(
                side="left", padx=2)
            self._day_vars[d] = var

        time_row = ctk.CTkFrame(builder, fg_color="transparent")
        time_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(time_row, text=t('time_label'),
                     font=("Helvetica", 12), text_color=TEXT_MAIN,
                     width=140, anchor="w").pack(side="left")
        self._hour_var = tk.StringVar(value="09")
        self._min_var  = tk.StringVar(value="00")
        ctk.CTkEntry(time_row, textvariable=self._hour_var,
                     width=50, height=30, font=("Helvetica", 12),
                     fg_color=CT_BG, border_color=BORDER,
                     text_color=TEXT_MAIN, justify="center").pack(side="left")
        ctk.CTkLabel(time_row, text=":", font=("Helvetica", 14, "bold"),
                     text_color=TEXT_MAIN).pack(side="left", padx=4)
        ctk.CTkEntry(time_row, textvariable=self._min_var,
                     width=50, height=30, font=("Helvetica", 12),
                     fg_color=CT_BG, border_color=BORDER,
                     text_color=TEXT_MAIN, justify="center").pack(side="left")

        lbl_row = ctk.CTkFrame(builder, fg_color="transparent")
        lbl_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(lbl_row, text=t('label_optional'),
                     font=("Helvetica", 12), text_color=TEXT_MAIN,
                     width=140, anchor="w").pack(side="left")
        self._label_var = tk.StringVar()
        ctk.CTkEntry(lbl_row, textvariable=self._label_var,
                     height=30, font=("Helvetica", 12),
                     fg_color=CT_BG, border_color=BORDER,
                     text_color=TEXT_MAIN).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(builder, text=t('add_job'), height=34, width=120,
                      font=("Helvetica", 12, "bold"),
                      fg_color=ACCENT, hover_color="#2563eb",
                      command=self._add_job).pack(anchor="w", padx=16, pady=(0, 12))

        # Jobs list
        jobs_card = self._card(body, row=2, title=t('sched_jobs'))
        self._jobs_frame = ctk.CTkFrame(jobs_card, fg_color="transparent")
        self._jobs_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._refresh_jobs_ui()

        # Note
        note = self._card(body, row=3, title=t('note'))
        ctk.CTkLabel(note, text=t('sched_note'),
                     font=("Helvetica", 11), text_color=TEXT_SUB,
                     justify="left").pack(anchor="w", padx=16, pady=(0, 12))

    def _card(self, parent, row, title):
        f = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10,
                         border_width=1, border_color=BORDER)
        f.grid(row=row, column=0, sticky="ew", padx=24, pady=(0, 14))
        ctk.CTkLabel(f, text=title,
                     font=("Helvetica", 13, "bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkFrame(f, height=1, fg_color=BORDER).pack(fill="x", padx=16, pady=(0, 8))
        return f

    # ── Jobs ─────────────────────────────────────────────────
    def _add_job(self):
        days = [d for d, v in self._day_vars.items() if v.get()]
        if not days:
            messagebox.showwarning("WarmUpPro", t('warn_select_day'))
            return
        try:
            hour   = int(self._hour_var.get())
            minute = int(self._min_var.get())
            assert 0 <= hour < 24 and 0 <= minute < 60
        except Exception:
            messagebox.showwarning("WarmUpPro", t('warn_invalid_time'))
            return
        days_short = t('days_short')
        days_abbr  = [days_short[DAYS_EN.index(d)] for d in days]
        label = (self._label_var.get().strip() or
                 f"{', '.join(days_abbr)} {hour:02d}:{minute:02d}")
        self._jobs.append({"days": days, "hour": hour, "minute": minute, "label": label})
        self._refresh_jobs_ui()

    def _refresh_jobs_ui(self):
        for widget in self._jobs_frame.winfo_children():
            widget.destroy()
        if not self._jobs:
            ctk.CTkLabel(self._jobs_frame, text=t('no_jobs'),
                         font=("Helvetica", 12), text_color=TEXT_SUB).pack(
                anchor="w", padx=4, pady=8)
            return
        days_short = t('days_short')
        for i, job in enumerate(self._jobs):
            row = ctk.CTkFrame(self._jobs_frame, fg_color=CT_BG, corner_radius=6)
            row.pack(fill="x", pady=2, padx=4)
            abbrs = [days_short[DAYS_EN.index(d)] for d in job["days"]
                     if d in DAYS_EN]
            days_str = ", ".join(abbrs)
            ctk.CTkLabel(row,
                         text=f"{job['label']}  |  {days_str}  {job['hour']:02d}:{job['minute']:02d}",
                         font=("Helvetica", 12), text_color=TEXT_MAIN).pack(
                side="left", padx=10, pady=6)
            ctk.CTkButton(row, text=t('remove'), width=80, height=26,
                          font=("Helvetica", 11), fg_color=ERROR,
                          command=lambda idx=i: self._remove_job(idx)).pack(
                side="right", padx=8, pady=4)

    def _remove_job(self, idx):
        if 0 <= idx < len(self._jobs):
            self._jobs.pop(idx)
            self._refresh_jobs_ui()

    # ── Scheduler toggle ─────────────────────────────────────
    def _toggle_scheduler(self):
        if self._sched_thread and self._sched_thread.is_alive():
            self._stop_event.set()
            self._sched_status.configure(text=t('sched_off'), text_color=TEXT_SUB)
            self._next_lbl.configure(text=t('next_run_dash'))
            self._toggle_btn.configure(text=t('enable_sched'),
                                        fg_color=SUCCESS, hover_color="#16a34a")
        else:
            if not self._jobs:
                messagebox.showwarning("WarmUpPro", t('warn_add_job_first'))
                return
            self._stop_event.clear()
            self._sched_thread = threading.Thread(
                target=self._scheduler_loop, daemon=True)
            self._sched_thread.start()
            self._sched_status.configure(text=t('sched_on'), text_color=SUCCESS)
            self._toggle_btn.configure(text=t('disable_sched'),
                                        fg_color=ERROR, hover_color="#dc2626")
            self._update_next_run()

    def _scheduler_loop(self):
        while not self._stop_event.is_set():
            now = datetime.datetime.now()
            for job in self._jobs:
                if (now.strftime("%A") in job["days"]
                        and now.hour == job["hour"]
                        and now.minute == job["minute"]
                        and now.second == 0):
                    self.after(0, self._trigger_session)
            self._stop_event.wait(timeout=30)
            self.after(0, self._update_next_run)

    def _trigger_session(self):
        run_tab = self.app._tabs.get("run")
        if run_tab and not self.app.session_mgr.is_running():
            run_tab._start_session()

    def _update_next_run(self):
        if not self._jobs or (self._sched_thread and not self._sched_thread.is_alive()):
            return
        now = datetime.datetime.now()
        earliest = None
        for job in self._jobs:
            for delta in range(7):
                candidate = now + datetime.timedelta(days=delta)
                if candidate.strftime("%A") in job["days"]:
                    cand_t = candidate.replace(hour=job["hour"], minute=job["minute"],
                                               second=0, microsecond=0)
                    if cand_t > now:
                        if earliest is None or cand_t < earliest:
                            earliest = cand_t
                        break
        if earliest:
            self._next_lbl.configure(
                text=t('next_run_prefix') + earliest.strftime('%A %d %b %H:%M'))

    def on_show(self):
        pass

    # ── Language update ──────────────────────────────────────
    def update_lang(self):
        was_running = self._sched_thread and self._sched_thread.is_alive()
        for w in self.winfo_children():
            w.destroy()
        self._build()
        if was_running:
            self._sched_status.configure(text=t('sched_on'), text_color=SUCCESS)
            self._toggle_btn.configure(text=t('disable_sched'),
                                        fg_color=ERROR, hover_color="#dc2626")
            self._update_next_run()
