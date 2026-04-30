"""
ui/tab_history.py  --  Session history viewer.
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from core import history
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

STATUS_COLORS = {
    "completed": SUCCESS,
    "stopped":   WARNING,
    "error":     ERROR,
}


class HistoryTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=CT_BG, corner_radius=0)
        self.app = app
        self._selected_session_id = None
        self._sessions_data = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 0))
        ctk.CTkLabel(hdr, text=t('history_title'),
                     font=("Helvetica", 20, "bold"),
                     text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkButton(hdr, text=t('refresh'), width=80, height=32,
                      font=("Helvetica", 12), fg_color=ACCENT,
                      command=self._load_sessions).pack(side="right", padx=(8, 0))
        ctk.CTkButton(hdr, text=t('clear_all'), width=90, height=32,
                      font=("Helvetica", 12), fg_color=ERROR,
                      command=self._clear_all).pack(side="right")

        # Stats bar
        stats_frame = ctk.CTkFrame(self, fg_color=CARD_BG,
                                    corner_radius=10,
                                    border_width=1, border_color=BORDER)
        stats_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 0))

        self._stat_labels = {}
        stat_keys = [
            ('total',         'stat_total'),
            ('completed',     'stat_completed'),
            ('stopped',       'stat_stopped'),
            ('total_minutes', 'stat_minutes'),
        ]
        for i, (data_key, label_key) in enumerate(stat_keys):
            if i > 0:
                ctk.CTkFrame(stats_frame, width=1, fg_color=BORDER).grid(
                    row=0, column=i * 2 - 1, sticky="ns", pady=8)
            sf = ctk.CTkFrame(stats_frame, fg_color="transparent")
            sf.grid(row=0, column=i * 2, padx=20, pady=8)
            lbl = ctk.CTkLabel(sf, text="—",
                                font=("Helvetica", 18, "bold"), text_color=ACCENT)
            lbl.pack()
            ctk.CTkLabel(sf, text=t(label_key),
                         font=("Helvetica", 10), text_color=TEXT_SUB).pack()
            self._stat_labels[data_key] = lbl

        # Body: sessions list + phase detail
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=24, pady=12)
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)

        # Sessions list
        sess_card = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10,
                                  border_width=1, border_color=BORDER)
        sess_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        sess_card.grid_rowconfigure(1, weight=1)
        sess_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sess_card, text=t('sessions_lbl'),
                     font=("Helvetica", 13, "bold"),
                     text_color=TEXT_MAIN).grid(
            row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        ctk.CTkFrame(sess_card, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="sew", padx=8)

        lf = ctk.CTkFrame(sess_card, fg_color="transparent")
        lf.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        lf.grid_rowconfigure(0, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        self._sess_list = tk.Listbox(lf, font=("Helvetica", 11),
                                      bg=CARD_BG, fg=TEXT_MAIN,
                                      selectbackground=ACCENT,
                                      selectforeground="#ffffff",
                                      bd=0, highlightthickness=0,
                                      activestyle="none", relief="flat")
        self._sess_list.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(lf, orient="vertical", command=self._sess_list.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._sess_list.configure(yscrollcommand=sb.set)
        self._sess_list.bind("<<ListboxSelect>>", self._on_session_select)

        # Phase detail
        phase_card = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10,
                                   border_width=1, border_color=BORDER)
        phase_card.grid(row=0, column=1, sticky="nsew")
        phase_card.grid_rowconfigure(1, weight=1)
        phase_card.grid_columnconfigure(0, weight=1)

        self._phase_title = ctk.CTkLabel(phase_card, text=t('select_session'),
                                          font=("Helvetica", 13, "bold"),
                                          text_color=TEXT_MAIN)
        self._phase_title.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        ctk.CTkFrame(phase_card, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="sew", padx=8)

        pf = ctk.CTkFrame(phase_card, fg_color="transparent")
        pf.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        pf.grid_rowconfigure(0, weight=1)
        pf.grid_columnconfigure(0, weight=1)

        self._phase_list = tk.Listbox(pf, font=("Helvetica", 11),
                                       bg=CARD_BG, fg=TEXT_MAIN,
                                       selectbackground=BORDER,
                                       selectforeground=TEXT_MAIN,
                                       bd=0, highlightthickness=0,
                                       activestyle="none", relief="flat")
        self._phase_list.grid(row=0, column=0, sticky="nsew")
        psb = tk.Scrollbar(pf, orient="vertical", command=self._phase_list.yview)
        psb.grid(row=0, column=1, sticky="ns")
        self._phase_list.configure(yscrollcommand=psb.set)

    # ── Data ─────────────────────────────────────────────────
    def on_show(self):
        history.init_db()
        self._load_sessions()

    def _load_sessions(self):
        self._update_stats()
        sessions = history.get_sessions(limit=200)
        self._sessions_data = sessions
        self._sess_list.delete(0, "end")
        for s in sessions:
            dur     = s.get("duration_m", 0) or 0
            started = (s.get("started_at") or "")[:16].replace("T", " ")
            status  = s.get("status", "?")
            self._sess_list.insert("end", f"{started}  |  {status:10s}  |  {dur:.0f} min")

    def _update_stats(self):
        stats = history.get_stats()
        self._stat_labels["total"].configure(text=str(stats.get("total_sessions", 0)))
        self._stat_labels["completed"].configure(text=str(stats.get("completed", 0)))
        self._stat_labels["stopped"].configure(text=str(stats.get("stopped", 0)))
        mins = stats.get("total_minutes", 0) or 0
        self._stat_labels["total_minutes"].configure(text=f"{mins:.0f}")

    def _on_session_select(self, event):
        sel = self._sess_list.curselection()
        if not sel or sel[0] >= len(self._sessions_data):
            return
        s = self._sessions_data[sel[0]]
        self._selected_session_id = s["id"]
        self._phase_title.configure(
            text=f"{t('phases_prefix')}{s['id']}  ({s.get('status','')})")
        phases = history.get_phase_log(s["id"])
        self._phase_list.delete(0, "end")
        for p in phases:
            line = (f"[{p.get('status','?'):8s}]  "
                    f"{p.get('category',''):<18s}  "
                    f"{p.get('phase','')[:40]}")
            self._phase_list.insert("end", line)

    def _clear_all(self):
        if messagebox.askyesno(t('clear_all'), t('clear_confirm')):
            history.clear_history()
            self._load_sessions()
            self._phase_list.delete(0, "end")
            self._phase_title.configure(text=t('select_session'))

    # ── Language update ──────────────────────────────────────
    def update_lang(self):
        for w in self.winfo_children():
            w.destroy()
        self._sessions_data = []
        self._selected_session_id = None
        self._build()
        try:
            history.init_db()
            self._load_sessions()
        except Exception:
            pass
