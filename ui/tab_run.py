"""
ui/tab_run.py  --  Run tab: categories, timings, start/stop, progress.
"""

import time
import threading
import tkinter as tk
import customtkinter as ctk

from core.session_manager import SessionManager, SessionConfig, SessionStatus
from core import geckodriver_util
from core.i18n import t

SB_BG       = "#1e293b"
CT_BG       = "#f1f5f9"
CARD_BG     = "#ffffff"
BORDER      = "#e2e8f0"
TEXT_MAIN   = "#0f172a"
TEXT_SUB    = "#64748b"
ACCENT      = "#3b82f6"
SUCCESS     = "#22c55e"
ERROR       = "#ef4444"
WARNING     = "#f59e0b"

ALL_CATEGORIES = [
    "News & Events", "Weather", "YouTube", "Reddit", "Wikipedia",
    "Shopping", "Food & Recipes", "Health & Wellness",
    "Travel & Tourism", "Technology",
]


class RunTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=CT_BG, corner_radius=0)
        self.app = app                      # MainWindow (имеет .settings и .session)
        self._timer_job     = None
        self._session_start = None
        self._captcha_win   = None
        self._build()

    # ── Build ─────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 0))
        ctk.CTkLabel(hdr, text=t('run_title'),
                     font=("Helvetica", 20, "bold"),
                     text_color=TEXT_MAIN).pack(side="left")

        body = ctk.CTkScrollableFrame(self, fg_color=CT_BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # Firefox status
        self._path_card = self._card(body, row=0, title=t('ff_config'))
        self._ff_status_lbl = ctk.CTkLabel(
            self._path_card, text=t('checking_paths'),
            font=("Helvetica", 12), text_color=TEXT_SUB)
        self._ff_status_lbl.pack(anchor="w", padx=16, pady=(4, 12))

        # Categories
        cat_card = self._card(body, row=1, title=t('browse_categories'))
        ctrl_row = ctk.CTkFrame(cat_card, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=16, pady=(2, 8))
        ctk.CTkButton(ctrl_row, text=t('select_all'), width=90, height=26,
                      font=("Helvetica", 12), fg_color=ACCENT,
                      command=self._select_all).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ctrl_row, text=t('deselect_all'), width=90, height=26,
                      font=("Helvetica", 12), fg_color=TEXT_SUB,
                      command=self._deselect_all).pack(side="left")

        grid = ctk.CTkFrame(cat_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 12))
        self._cat_vars = {}

        selected_cats = self.app.settings.get("selected_categories") or []
        for i, cat in enumerate(ALL_CATEGORIES):
            var = tk.BooleanVar(value=(cat in selected_cats))
            cb = ctk.CTkCheckBox(
                grid, text=cat, variable=var,
                font=("Helvetica", 12), text_color=TEXT_MAIN,
                checkmark_color="#ffffff",
                fg_color=ACCENT, hover_color="#2563eb",
                command=self._save_categories
            )
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=3)
            self._cat_vars[cat] = var
        grid.grid_columnconfigure((0, 1), weight=1)

        # Timings
        s = self.app.settings
        tim_card = self._card(body, row=2, title=t('session_timings'))
        self._browse1_var = tk.IntVar(value=s.get("browse1_minutes") or 15)
        self._idle_var    = tk.IntVar(value=s.get("idle_minutes") or 8)
        self._browse2_var = tk.IntVar(value=s.get("browse2_minutes") or 20)
        self._add_slider(tim_card, t('browse1'), self._browse1_var, 5, 60,
                         lambda v: self._save_timing("browse1_minutes", v))
        self._add_slider(tim_card, t('idle_pause'), self._idle_var, 1, 30,
                         lambda v: self._save_timing("idle_minutes", v))
        self._add_slider(tim_card, t('browse2'), self._browse2_var, 5, 60,
                         lambda v: self._save_timing("browse2_minutes", v))

        # Queries per category
        qpc_card = self._card(body, row=3, title=t('queries_per_cat'))
        self._min_q_var = tk.IntVar(value=s.get("min_per_category") or 5)
        self._max_q_var = tk.IntVar(value=s.get("max_per_category") or 15)
        self._add_slider(qpc_card, t('min_queries'), self._min_q_var, 1, 30,
                         lambda v: self._save_timing("min_per_category", v))
        self._add_slider(qpc_card, t('max_queries'), self._max_q_var, 1, 50,
                         lambda v: self._save_timing("max_per_category", v))

        # Progress
        prog_card = self._card(body, row=4, title=t('progress'))
        self._phase_lbl = ctk.CTkLabel(
            prog_card, text="—",
            font=("Helvetica", 12), text_color=TEXT_SUB
        )
        self._phase_lbl.pack(anchor="w", padx=16, pady=(4, 6))
        self._progress = ctk.CTkProgressBar(
            prog_card, height=12,
            fg_color=BORDER, progress_color=ACCENT
        )
        self._progress.pack(fill="x", padx=16, pady=(0, 4))
        self._progress.set(0)
        self._elapsed_lbl = ctk.CTkLabel(
            prog_card,
            text=t('elapsed_prefix') + '0:00',
            font=("Helvetica", 11), text_color=TEXT_SUB
        )
        self._elapsed_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        # Buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=24, pady=(8, 24))
        self._start_btn = ctk.CTkButton(
            btn_row, text=t('start_session'), height=44,
            font=("Helvetica", 14, "bold"),
            fg_color=SUCCESS, hover_color="#16a34a",
            command=self._start_session
        )
        self._start_btn.pack(side="left", padx=(0, 12))
        self._stop_btn = ctk.CTkButton(
            btn_row, text=t('stop'), height=44, width=100,
            font=("Helvetica", 14, "bold"),
            fg_color=ERROR, hover_color="#dc2626",
            state="disabled",
            command=self._stop_session
        )
        self._stop_btn.pack(side="left")
        self._result_lbl = ctk.CTkLabel(
            btn_row, text="",
            font=("Helvetica", 12), text_color=TEXT_SUB
        )
        self._result_lbl.pack(side="left", padx=16)

    # ── Card / slider helpers ────────────────────────────────
    def _card(self, parent, row, title):
        frame = ctk.CTkFrame(
            parent, fg_color=CARD_BG,
            corner_radius=10, border_width=1, border_color=BORDER
        )
        frame.grid(row=row, column=0, sticky="ew", padx=24, pady=(0, 14))
        ctk.CTkLabel(
            frame, text=title,
            font=("Helvetica", 13, "bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkFrame(frame, height=1, fg_color=BORDER).pack(
            fill="x", padx=16, pady=(0, 8)
        )
        return frame

    def _add_slider(self, parent, label, var, lo, hi, cmd):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(
            row, text=label, font=("Helvetica", 12),
            text_color=TEXT_MAIN, width=180, anchor="w"
        ).pack(side="left")
        val_lbl = ctk.CTkLabel(
            row, text=str(var.get()),
            font=("Helvetica", 12, "bold"),
            text_color=ACCENT, width=30
        )
        val_lbl.pack(side="right")
        slider = ctk.CTkSlider(
            row, from_=lo, to=hi, variable=var,
            number_of_steps=hi - lo,
            fg_color=BORDER, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color="#2563eb",
            command=lambda v, lbl=val_lbl, fn=cmd: (
                lbl.configure(text=str(int(v))), fn(int(v))
            )
        )
        slider.pack(side="right", padx=(0, 8), fill="x", expand=True)

    # ── Category helpers ─────────────────────────────────────
    def _select_all(self):
        for v in self._cat_vars.values():
            v.set(True)
        self._save_categories()

    def _deselect_all(self):
        for v in self._cat_vars.values():
            v.set(False)
        self._save_categories()

    def _save_categories(self):
        selected = [c for c, v in self._cat_vars.items() if v.get()]
        self.app.settings.set("selected_categories", selected)
        self.app.settings.save_all()

    def _save_timing(self, key, value):
        self.app.settings.set(key, value)
        self.app.settings.save_all()

    # ── on_show ──────────────────────────────────────────────
    def on_show(self):
        self._refresh_path_status()

    def _refresh_path_status(self):
        s = self.app.settings
        ok, msg = geckodriver_util.validate(
            s.get("firefox_binary") or "",
            s.get("firefox_profile") or "",
            s.get("geckodriver_path") or "",
        )
        if ok:
            self._ff_status_lbl.configure(text=t('ff_ok'), text_color=SUCCESS)
        else:
            self._ff_status_lbl.configure(
                text=f"{msg}  ({t('nav_settings').strip()})",
                text_color=ERROR
            )

    # ── Timer ────────────────────────────────────────────────
    def _tick_timer(self):
        if self._session_start is None:
            return
        elapsed = int(time.time() - self._session_start)
        m, s = divmod(elapsed, 60)
        self._elapsed_lbl.configure(text=f"{t('elapsed_prefix')}{m}:{s:02d}")
        self._timer_job = self.after(1000, self._tick_timer)

    def _stop_timer(self):
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None

    # ── Session start / stop ─────────────────────────────────
    def _start_session(self):
        selected = [c for c, v in self._cat_vars.items() if v.get()]
        if not selected:
            self._result_lbl.configure(text=t('select_one_cat'), text_color=WARNING)
            return

        s = self.app.settings
        ok, msg = geckodriver_util.validate(
            s.get("firefox_binary") or "",
            s.get("firefox_profile") or "",
            s.get("geckodriver_path") or "",
        )
        if not ok:
            self._result_lbl.configure(text=msg, text_color=ERROR)
            return

        cfg_obj = SessionConfig(
            firefox_binary      = s.get("firefox_binary") or "",
            firefox_profile     = s.get("firefox_profile") or "",
            geckodriver_path    = s.get("geckodriver_path") or "",
            selected_categories = selected,
            browse1_minutes     = s.get("browse1_minutes") or 15,
            idle_minutes        = s.get("idle_minutes") or 8,
            browse2_minutes     = s.get("browse2_minutes") or 20,
            min_per_category    = s.get("min_per_category") or 5,
            max_per_category    = s.get("max_per_category") or 15,
            read_speed          = s.get("read_speed") or 0.7,
            auto_close          = s.get("auto_close_browser") or True,
            max_retries         = s.get("max_retries") or 1,
        )

        mgr: SessionManager = self.app.session
        if mgr is None:
            self._result_lbl.configure(text="SessionManager is not initialized", text_color=ERROR)
            return

        mgr.on_progress = self._on_progress
        mgr.on_complete = self._on_complete
        mgr.on_error    = self._on_error
        mgr.on_captcha  = self._on_captcha

        started = mgr.start(cfg_obj)
        if not started:
            self._result_lbl.configure(text="Session already running", text_color=WARNING)
            return

        self._session_start = time.time()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._result_lbl.configure(text=t('session_running'), text_color=TEXT_SUB)
        self._progress.set(0)
        self._phase_lbl.configure(text="…")
        self._tick_timer()

    def _stop_session(self):
        mgr: SessionManager = self.app.session
        if mgr:
            mgr.stop()
        self._stop_btn.configure(state="disabled")
        self._result_lbl.configure(text=t('stopping'), text_color=WARNING)

    def _on_progress(self, index, total, block, category, query):
        self.after(0, lambda: self._apply_progress(index, total, block, category, query))

    def _apply_progress(self, index, total, block, category, query):
        self._phase_lbl.configure(text=f"{block}: {category} — {query[:50]}")
        self._progress.set(index / max(total, 1))

    def _on_complete(self, status_str, duration_m):
        self.after(0, lambda: self._session_done(status_str, duration_m))

    def _session_done(self, status_str, duration_m):
        self._stop_timer()
        self._session_start = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

        if status_str == SessionStatus.COMPLETED:
            self._result_lbl.configure(text=t('session_complete'), text_color=SUCCESS)
            self._progress.set(1.0)
        elif status_str == SessionStatus.STOPPED:
            self._result_lbl.configure(text="Session stopped", text_color=WARNING)
        else:
            self._result_lbl.configure(text=t('status_error'), text_color=ERROR)

        self._close_captcha_win()

    def _on_error(self, msg):
        self.after(0, lambda: self._session_error(msg))

    def _session_error(self, msg):
        self._stop_timer()
        self._session_start = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._result_lbl.configure(
            text=f"{t('status_error')}: {msg[:60]}",
            text_color=ERROR
        )
        self._close_captcha_win()

    # ── CAPTCHA handling ─────────────────────────────────────
    def _on_captcha(self, solved: bool):
        self.after(0, lambda: self._handle_captcha(solved))

    def _handle_captcha(self, solved: bool):
        if solved:
            self._close_captcha_win()
            self._result_lbl.configure(text=t('session_running'), text_color=TEXT_SUB)
            return

        if self._captcha_win and self._captcha_win.winfo_exists():
            return

        win = ctk.CTkToplevel(self)
        win.title("⚠ CAPTCHA")
        win.attributes('-topmost', True)
        win.resizable(False, False)
        win.configure(fg_color="#1e293b")

        self.update_idletasks()
        ax = self.winfo_rootx() + self.winfo_width()  // 2
        ay = self.winfo_rooty() + self.winfo_height() // 2
        win.geometry(f"420x180+{ax - 210}+{ay - 90}")

        ctk.CTkLabel(
            win, text="⚠  Google CAPTCHA Detected",
            font=("Helvetica", 15, "bold"),
            text_color=WARNING
        ).pack(pady=(22, 6))

        ctk.CTkLabel(
            win,
            text="Please solve the CAPTCHA in the Firefox window.\n"
                 "The session will continue automatically once solved.",
            font=("Helvetica", 12), text_color="#f1f5f9",
            justify="center"
        ).pack(padx=20)

        ctk.CTkLabel(
            win, text="Waiting for solution…",
            font=("Helvetica", 11), text_color="#64748b"
        ).pack(pady=(10, 0))

        self._captcha_win = win
        self._result_lbl.configure(text="⚠ CAPTCHA — solve in Firefox", text_color=WARNING)

    def _close_captcha_win(self):
        if self._captcha_win:
            try:
                self._captcha_win.destroy()
            except Exception:
                pass
            self._captcha_win = None

    # ── Language update ──────────────────────────────────────
    def update_lang(self):
        running = self._session_start is not None
        self._stop_timer()
        for w in self.winfo_children():
            w.destroy()
        self._build()
        if running:
            self._session_start = time.time()
            self._tick_timer()
        self._refresh_path_status()
