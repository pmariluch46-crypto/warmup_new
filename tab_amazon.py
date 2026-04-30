"""
ui/tab_amazon.py  --  Amazon Warmer tab (Google Ads Editor style, 3 columns).

Left   : Active categories (checkboxes) + Firefox status
Middle : Session settings + progress + Start/Stop
Right  : Full query editor (20 categories × 100 queries)
"""

import time
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from core import geckodriver_util
from core.amazon_query_manager import (
    load_amazon_queries, get_amazon_categories,
    add_amazon_query, remove_amazon_query, update_amazon_query,
)
from core.i18n import t
from core import history

# Цвета — близко к Material 3, но с сохранением логики старого UI
CT_BG       = "#0b0f19"   # общий фон вкладки (тёмный)
CARD_BG     = "#111827"   # карточки
BORDER      = "#1f2933"
TEXT_MAIN   = "#e5e7eb"
TEXT_SUB    = "#9ca3af"
ACCENT      = "#3b82f6"
SUCCESS     = "#22c55e"
ERROR       = "#ef4444"
WARNING     = "#f59e0b"
AMZN        = "#FF9900"
AMZN_DARK   = "#e68900"
ROW_ALT     = "#020617"

_ALL_CATEGORIES = [
    "Electronics", "Computers & Laptops", "Cell Phones & Accessories",
    "Home & Kitchen", "Clothing & Fashion", "Sports & Outdoors",
    "Books", "Toys & Games", "Beauty & Personal Care",
    "Health & Household", "Automotive", "Garden & Outdoor",
    "Pet Supplies", "Office Products", "Tools & Home Improvement",
    "Baby Products", "Food & Grocery", "Video Games & Consoles",
    "Movies & TV Shows", "Musical Instruments", "Own Requests",
]


class AmazonTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self.app = app
        self._stop_event   = threading.Event()
        self._thread       = None
        self._session_start = None
        self._timer_job    = None
        self._editor_cat   = None
        self._editor_idx   = None
        self._build()

    # ==========================================================================
    #  BUILD (3‑колоночный layout)
    # ==========================================================================

    def _build(self):
        # Общий layout: заголовок + 3 колонки
        self.grid_columnconfigure(0, weight=0)   # left
        self.grid_columnconfigure(1, weight=0)   # middle
        self.grid_columnconfigure(2, weight=1)   # right
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=(16, 0))
        ctk.CTkLabel(
            hdr,
            text=t('amazon_title'),
            font=("Segoe UI Variable", 20, "bold"),
            text_color=TEXT_MAIN
        ).pack(side="left")
        ctk.CTkLabel(
            hdr,
            text=t('amazon_sub'),
            font=("Segoe UI Variable", 12),
            text_color=TEXT_SUB
        ).pack(side="left", padx=12)

        # ЛЕВАЯ КОЛОНКА: Firefox status + Active Categories
        left = ctk.CTkScrollableFrame(
            self, fg_color=CT_BG, corner_radius=0, width=260
        )
        left.grid(row=1, column=0, sticky="nsw", padx=(16, 8), pady=(8, 16))
        left.grid_columnconfigure(0, weight=1)

        # СРЕДНЯЯ КОЛОНКА: Session settings + Progress + Start/Stop
        middle = ctk.CTkScrollableFrame(
            self, fg_color=CT_BG, corner_radius=0, width=260
        )
        middle.grid(row=1, column=1, sticky="nsw", padx=(0, 8), pady=(8, 16))
        middle.grid_columnconfigure(0, weight=1)

        # ПРАВАЯ КОЛОНКА: Query Editor (категории + список + редактирование)
        right = ctk.CTkFrame(self, fg_color=CT_BG, corner_radius=0)
        right.grid(row=1, column=2, sticky="nsew", padx=(0, 16), pady=(8, 16))
        right.grid_columnconfigure(0, weight=0)
        right.grid_columnconfigure(1, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)

        self._build_left(left)
        self._build_middle(middle)
        self._build_right(right)

    # --------------------------------------------------------------------------
    #  LEFT COLUMN: Firefox status + Active Categories
    # --------------------------------------------------------------------------

    def _build_left(self, parent):
        # Firefox status
        path_card = self._card(parent, row=0, title=t('ff_config'))
        self._ff_lbl = ctk.CTkLabel(
            path_card,
            text=t('checking_paths'),
            font=("Segoe UI Variable", 12),
            text_color=TEXT_SUB
        )
        self._ff_lbl.pack(anchor="w", padx=16, pady=(4, 12))

        # Categories
        cat_card = self._card(parent, row=1, title=t('active_categories'))
        ctrl = ctk.CTkFrame(cat_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(2, 6))
        ctk.CTkButton(
            ctrl,
            text=t('all'),
            width=54,
            height=24,
            font=("Segoe UI Variable", 11),
            fg_color=AMZN,
            hover_color=AMZN_DARK,
            text_color="#000000",
            command=self._select_all
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            ctrl,
            text=t('none'),
            width=54,
            height=24,
            font=("Segoe UI Variable", 11),
            fg_color=TEXT_SUB,
            hover_color="#475569",
            command=self._deselect_all
        ).pack(side="left")

        grid = ctk.CTkFrame(cat_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 10))
        grid.grid_columnconfigure((0, 1), weight=1)

        self._cat_vars: dict[str, tk.BooleanVar] = {}
        saved = self.app.settings.get("amazon_categories", _ALL_CATEGORIES[:5])
        regular_cats = [c for c in _ALL_CATEGORIES if c != "Own Requests"]
        for i, cat in enumerate(regular_cats):
            var = tk.BooleanVar(value=(cat in saved))
            cb = ctk.CTkCheckBox(
                grid,
                text=cat,
                variable=var,
                font=("Segoe UI Variable", 11),
                text_color=TEXT_MAIN,
                checkmark_color="#000000",
                fg_color=AMZN,
                hover_color=AMZN_DARK,
                command=self._save_categories
            )
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)
            self._cat_vars[cat] = var

        # Own Requests — отдельной строкой
        sep_row = len(regular_cats) // 2 + (1 if len(regular_cats) % 2 else 0)
        ctk.CTkFrame(grid, height=1, fg_color=BORDER).grid(
            row=sep_row, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 4)
        )
        own_var = tk.BooleanVar(value=("Own Requests" in saved))
        own_cb = ctk.CTkCheckBox(
            grid,
            text="⭐  Own Requests",
            variable=own_var,
            font=("Segoe UI Variable", 12, "bold"),
            text_color=AMZN,
            checkmark_color="#000000",
            fg_color=AMZN,
            hover_color=AMZN_DARK,
            command=self._save_categories
        )
        own_cb.grid(
            row=sep_row + 1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=6,
            pady=(0, 6)
        )
        self._cat_vars["Own Requests"] = own_var

    # --------------------------------------------------------------------------
    #  MIDDLE COLUMN: Session settings + Progress + Start/Stop
    # --------------------------------------------------------------------------

    def _build_middle(self, parent):
        # Session settings
        cfg_card = self._card(parent, row=0, title=t('session_settings'))
        self._minutes_var = tk.IntVar(
            value=self.app.settings.get("amazon_minutes", 10)
        )
        self._add_slider(
            cfg_card,
            t('session_duration'),
            self._minutes_var,
            3,
            60,
            lambda v: self._save_setting("amazon_minutes", v),
        )

        rev_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        rev_row.pack(fill="x", padx=16, pady=(0, 12))
        self._reviews_var = tk.BooleanVar(
            value=self.app.settings.get("amazon_read_reviews", True)
        )
        ctk.CTkCheckBox(
            rev_row,
            text=t('read_reviews'),
            variable=self._reviews_var,
            font=("Segoe UI Variable", 12),
            text_color=TEXT_MAIN,
            checkmark_color="#000000",
            fg_color=AMZN,
            hover_color=AMZN_DARK,
            command=lambda: self._save_setting(
                "amazon_read_reviews", self._reviews_var.get()
            ),
        ).pack(side="left")

        # Progress
        prog_card = self._card(parent, row=1, title=t('progress'))
        self._phase_lbl = ctk.CTkLabel(
            prog_card,
            text="—",
            font=("Segoe UI Variable", 12),
            text_color=TEXT_SUB
        )
        self._phase_lbl.pack(anchor="w", padx=16, pady=(4, 6))
        self._progress_bar = ctk.CTkProgressBar(
            prog_card,
            height=10,
            fg_color=BORDER,
            progress_color=AMZN
        )
        self._progress_bar.pack(fill="x", padx=16, pady=(0, 4))
        self._progress_bar.set(0)
        self._elapsed_lbl = ctk.CTkLabel(
            prog_card,
            text=t('elapsed_prefix') + '0:00',
            font=("Segoe UI Variable", 11),
            text_color=TEXT_SUB
        )
        self._elapsed_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        # Buttons
        btn_card = ctk.CTkFrame(
            parent,
            fg_color=CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER
        )
        btn_card.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        btn_inner = ctk.CTkFrame(btn_card, fg_color="transparent")
        btn_inner.pack(fill="x", padx=16, pady=12)

        self._start_btn = ctk.CTkButton(
            btn_inner,
            text=t('start_amazon'),
            height=40,
            font=("Segoe UI Variable", 13, "bold"),
            fg_color=SUCCESS,
            hover_color="#16a34a",
            command=self._start_session
        )
        self._start_btn.pack(fill="x", pady=(0, 6))

        self._stop_btn = ctk.CTkButton(
            btn_inner,
            text=t('stop_amazon'),
            height=36,
            font=("Segoe UI Variable", 13, "bold"),
            fg_color=ERROR,
            hover_color="#dc2626",
            state="disabled",
            command=self._stop_session
        )
        self._stop_btn.pack(fill="x")

        self._result_lbl = ctk.CTkLabel(
            btn_inner,
            text="",
            font=("Segoe UI Variable", 11),
            text_color=TEXT_SUB
        )
        self._result_lbl.pack(anchor="w", pady=(6, 0))

    # --------------------------------------------------------------------------
    #  RIGHT COLUMN: Query Editor (категории + список + редактирование)
    # --------------------------------------------------------------------------

    def _build_right(self, right):
        sub_hdr = ctk.CTkFrame(right, fg_color="transparent")
        sub_hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 6))
        ctk.CTkLabel(
            sub_hdr,
            text=t('query_editor'),
            font=("Segoe UI Variable", 14, "bold"),
            text_color=TEXT_MAIN
        ).pack(side="left")
        ctk.CTkLabel(
            sub_hdr,
            text=t('query_editor_hint'),
            font=("Segoe UI Variable", 11),
            text_color=TEXT_SUB
        ).pack(side="left", padx=10)

        # Category list (left pane of editor)
        cat_frame = ctk.CTkFrame(
            right,
            fg_color=CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            width=190
        )
        cat_frame.grid(row=1, column=0, sticky="nsew", padx=(16, 6), pady=(0, 16))
        cat_frame.grid_propagate(False)
        cat_frame.grid_rowconfigure(1, weight=1)
        cat_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cat_frame,
            text=t('categories'),
            font=("Segoe UI Variable", 12, "bold"),
            text_color=TEXT_MAIN
        ).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkFrame(cat_frame, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="sew", padx=8
        )

        cat_scroll = ctk.CTkScrollableFrame(
            cat_frame, fg_color="transparent", corner_radius=0
        )
        cat_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        self._cat_btn_map: dict[str, ctk.CTkButton] = {}
        for cat in _ALL_CATEGORIES:
            if cat == "Own Requests":
                ctk.CTkFrame(cat_scroll, height=1, fg_color=BORDER).pack(
                    fill="x", padx=4, pady=(6, 4)
                )
                btn = ctk.CTkButton(
                    cat_scroll,
                    text="⭐  Own Requests",
                    anchor="w",
                    font=("Segoe UI Variable", 11, "bold"),
                    height=32,
                    fg_color="#1f2937",
                    text_color=AMZN,
                    hover_color="#111827",
                    corner_radius=6,
                    border_width=1,
                    border_color=AMZN,
                    command=lambda c=cat: self._select_editor_cat(c),
                )
            else:
                btn = ctk.CTkButton(
                    cat_scroll,
                    text=cat,
                    anchor="w",
                    font=("Segoe UI Variable", 11),
                    height=30,
                    fg_color="transparent",
                    text_color=TEXT_MAIN,
                    hover_color=BORDER,
                    corner_radius=6,
                    command=lambda c=cat: self._select_editor_cat(c),
                )
            btn.pack(fill="x", padx=4, pady=1)
            self._cat_btn_map[cat] = btn

        # Query list (right pane of editor)
        q_frame = ctk.CTkFrame(
            right,
            fg_color=CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER
        )
        q_frame.grid(row=1, column=1, sticky="nsew", padx=(0, 16), pady=(0, 16))
        q_frame.grid_rowconfigure(1, weight=1)
        q_frame.grid_columnconfigure(0, weight=1)

        tb = ctk.CTkFrame(q_frame, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        self._q_title = ctk.CTkLabel(
            tb,
            text=t('select_cat_arrow'),
            font=("Segoe UI Variable", 13, "bold"),
            text_color=TEXT_MAIN
        )
        self._q_title.pack(side="left")
        self._q_count = ctk.CTkLabel(
            tb,
            text="",
            font=("Segoe UI Variable", 11),
            text_color=TEXT_SUB
        )
        self._q_count.pack(side="left", padx=8)

        ctk.CTkButton(
            tb,
            text=t('add'),
            width=68,
            height=27,
            font=("Segoe UI Variable", 11),
            fg_color=SUCCESS,
            hover_color="#16a34a",
            command=self._add_query
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            tb,
            text=t('delete'),
            width=68,
            height=27,
            font=("Segoe UI Variable", 11),
            fg_color=ERROR,
            hover_color="#dc2626",
            command=self._delete_query
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            tb,
            text=t('save'),
            width=68,
            height=27,
            font=("Segoe UI Variable", 11),
            fg_color=AMZN,
            hover_color=AMZN_DARK,
            text_color="#000000",
            command=self._save_edit
        ).pack(side="right")

        ctk.CTkFrame(q_frame, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="sew", padx=8
        )

        lb_frame = ctk.CTkFrame(q_frame, fg_color="transparent")
        lb_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))
        lb_frame.grid_rowconfigure(0, weight=1)
        lb_frame.grid_columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            lb_frame,
            font=("Segoe UI Variable", 11),
            bg=CARD_BG,
            fg=TEXT_MAIN,
            selectbackground=AMZN,
            selectforeground="#000000",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            relief="flat",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(lb_frame, orient="vertical", command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)

        edit_frame = ctk.CTkFrame(q_frame, fg_color="transparent")
        edit_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        edit_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            edit_frame,
            text=t('edit_selected_q'),
            font=("Segoe UI Variable", 11),
            text_color=TEXT_SUB
        ).grid(row=0, column=0, sticky="w")
        self._edit_var = tk.StringVar()
        self._edit_entry = ctk.CTkEntry(
            edit_frame,
            textvariable=self._edit_var,
            height=32,
            font=("Segoe UI Variable", 12),
            fg_color=CT_BG,
            border_color=BORDER,
            text_color=TEXT_MAIN,
            placeholder_text=t('query_placeholder'),
        )
        self._edit_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._edit_entry.bind("<Return>", lambda e: self._save_edit())

    # ==========================================================================
    #  HELPERS
    # ==========================================================================

    def _card(self, parent, row, title):
        frame = ctk.CTkFrame(
            parent,
            fg_color=CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER
        )
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 12))
        ctk.CTkLabel(
            frame,
            text=title,
            font=("Segoe UI Variable", 12, "bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(10, 3))
        ctk.CTkFrame(frame, height=1, fg_color=BORDER).pack(
            fill="x", padx=16, pady=(0, 6)
        )
        return frame

    def _add_slider(self, parent, label, var, lo, hi, cmd):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(
            row,
            text=label,
            font=("Segoe UI Variable", 11),
            text_color=TEXT_MAIN,
            width=200,
            anchor="w",
        ).pack(side="left")
        val_lbl = ctk.CTkLabel(
            row,
            text=str(var.get()),
            font=("Segoe UI Variable", 11, "bold"),
            text_color=AMZN,
            width=28,
        )
        val_lbl.pack(side="right")
        slider = ctk.CTkSlider(
            row,
            from_=lo,
            to=hi,
            variable=var,
            number_of_steps=hi - lo,
            fg_color=BORDER,
            progress_color=AMZN,
            button_color=AMZN,
            button_hover_color=AMZN_DARK,
            command=lambda v, lbl=val_lbl, fn=cmd: (
                lbl.configure(text=str(int(v))), fn(int(v))
            ),
        )
        slider.pack(side="right", padx=(0, 8), fill="x", expand=True)

    # ==========================================================================
    #  QUERY CRUD
    # ==========================================================================

    def _select_editor_cat(self, cat: str):
        self._editor_cat = cat
        self._editor_idx = None
        self._edit_var.set("")
        for c, btn in self._cat_btn_map.items():
            if c == "Own Requests":
                if c == cat:
                    btn.configure(fg_color=AMZN, text_color="#000000", border_color=AMZN)
                else:
                    btn.configure(fg_color="#1f2937", text_color=AMZN, border_color=AMZN)
            else:
                if c == cat:
                    btn.configure(fg_color=AMZN, text_color="#000000")
                else:
                    btn.configure(fg_color="transparent", text_color=TEXT_MAIN)
        self._refresh_query_list()

    def _refresh_query_list(self):
        if not self._editor_cat:
            return
        try:
            data = load_amazon_queries()
            queries = data.get(self._editor_cat, [])
        except Exception:
            queries = []
        self._listbox.delete(0, "end")
        for i, q in enumerate(queries):
            self._listbox.insert("end", f"  {q}")
            if i % 2 == 1:
                self._listbox.itemconfigure(i, bg=ROW_ALT)
        self._q_title.configure(text=self._editor_cat)
        n = len(queries)
        self._q_count.configure(text=t('queries_count').format(n=n))

    def _on_list_select(self, event):
        sel = self._listbox.curselection()
        if sel:
            self._editor_idx = sel[0]
            self._edit_var.set(self._listbox.get(sel[0]).strip())

    def _add_query(self):
        if not self._editor_cat:
            messagebox.showwarning("Amazon Warmer", t('select_a_cat'))
            return
        new_q = self._edit_var.get().strip()
        if not new_q:
            return
        add_amazon_query(self._editor_cat, new_q)
        self._edit_var.set("")
        self._refresh_query_list()

    def _delete_query(self):
        if self._editor_idx is None or not self._editor_cat:
            return
        q = self._listbox.get(self._editor_idx).strip()
        if messagebox.askyesno(t('delete'), f'"{q}"?'):
            remove_amazon_query(self._editor_cat, q)
            self._editor_idx = None
            self._edit_var.set("")
            self._refresh_query_list()

    def _save_edit(self):
        if self._editor_idx is None or not self._editor_cat:
            return
        old = self._listbox.get(self._editor_idx).strip()
        new = self._edit_var.get().strip()
        if not new:
            return
        update_amazon_query(self._editor_cat, old, new)
        self._refresh_query_list()
        if self._editor_idx < self._listbox.size():
            self._listbox.selection_set(self._editor_idx)
            self._listbox.see(self._editor_idx)

    # ==========================================================================
    #  CATEGORY CHECKBOXES
    # ==========================================================================

    def _select_all(self):
        for v in self._cat_vars.values():
            v.set(True)
        self._save_categories()

    def _deselect_all(self):
        for v in self._cat_vars.values():
            v.set(False)
        self._save_categories()

    def _save_categories(self):
        selected = [k for k, v in self._cat_vars.items() if v.get()]
        self.app.settings["amazon_categories"] = selected
        self.app.save_settings()

    def _save_setting(self, key, value):
        self.app.settings[key] = value
        self.app.save_settings()

    # ==========================================================================
    #  ON_SHOW / PATH STATUS
    # ==========================================================================

    def on_show(self):
        self._refresh_path_status()
        if self._editor_cat:
            self._refresh_query_list()

    def _refresh_path_status(self):
        s = self.app.settings
        ok, msg = geckodriver_util.validate(
            s.get("firefox_binary", ""),
            s.get("firefox_profile", ""),
            s.get("geckodriver_path", ""),
        )
        if ok:
            self._ff_lbl.configure(text=t('ff_ok'), text_color=SUCCESS)
        else:
            self._ff_lbl.configure(
                text=f"{msg}  ({t('nav_settings').strip()})",
                text_color=ERROR
            )

    # ==========================================================================
    #  TIMER
    # ==========================================================================

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

    # ==========================================================================
    #  SESSION
    # ==========================================================================

    def _on_progress(self, text: str, pct: int):
        self.after(0, lambda: self._apply_progress(text, pct))

    def _apply_progress(self, text: str, pct: int):
        self._phase_lbl.configure(text=text)
        self._progress_bar.set(pct / 100)

    def _start_session(self):
        selected = [k for k, v in self._cat_vars.items() if v.get()]
        if not selected:
            self._result_lbl.configure(text=t('select_one_cat'), text_color=WARNING)
            return
        s = self.app.settings
        ok, msg = geckodriver_util.validate(
            s.get("firefox_binary", ""),
            s.get("firefox_profile", ""),
            s.get("geckodriver_path", ""),
        )
        if not ok:
            self._result_lbl.configure(text=msg, text_color=ERROR)
            return

        self._stop_event.clear()
        self._session_start = time.time()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._result_lbl.configure(text=t('session_running'), text_color=TEXT_SUB)
        self._progress_bar.set(0)
        self._phase_lbl.configure(text="…")
        self.app.set_status(t('amzn_running'), AMZN)
        self.app.start_cursor_highlight(color=AMZN)
        self.app.start_mouse_blocker(stop_cb=lambda: self.after(0, self._stop_session))
        self._tick_timer()

        self._thread = threading.Thread(
            target=self._worker, args=(s, selected), daemon=True
        )
        self._thread.start()

    def _worker(self, s: dict, selected: list):
        from core.browser_bot import create_driver
        from core.amazon_engine import run_amazon_session, AmazonSessionConfig
        import time as _time

        driver     = None
        session_id = None
        t_start    = _time.time()
        error_msg  = ""

        session_id = history.start_session(selected, total_phases=1)

        try:
            driver = create_driver(
                firefox_binary   = s["firefox_binary"],
                firefox_profile  = s["firefox_profile"],
                geckodriver_path = s["geckodriver_path"],
            )
            cfg = AmazonSessionConfig(
                categories      = selected,
                session_minutes = self._minutes_var.get(),
                read_reviews    = self._reviews_var.get(),
                stop_event      = self._stop_event,
                on_progress     = self._on_progress,
            )
            run_amazon_session(driver, cfg)
        except Exception as exc:
            error_msg = str(exc)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

            stopped    = self._stop_event.is_set()
            duration_s = _time.time() - t_start
            if session_id:
                if error_msg:
                    db_status, done = "partial", 0
                elif stopped:
                    db_status, done = "stopped", 0
                else:
                    db_status, done = "completed", 1
                history.log_phase(
                    session_id,
                    phase_name = "Amazon Warm-up",
                    category   = ", ".join(selected),
                    status     = db_status,
                    duration_s = round(duration_s, 1),
                )
                history.end_session(session_id, done, db_status)

            self.after(0, lambda st=stopped: self._session_finished(not st))

    def _stop_session(self):
        self._stop_event.set()
        self.app.stop_mouse_blocker()
        self._stop_btn.configure(state="disabled")
        self._result_lbl.configure(text=t('stopping'), text_color=WARNING)
        self.app.set_status(t('amzn_stopping'), WARNING)
        self.app.stop_cursor_highlight()

    def _session_finished(self, success: bool, error: str = ""):
        self._stop_timer()
        self.app.stop_cursor_highlight()
        self.app.stop_mouse_blocker()
        self._session_start = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        if success and not self._stop_event.is_set():
            self._result_lbl.configure(text=t('session_complete'), text_color=SUCCESS)
            self.app.set_status(t('amzn_done'), SUCCESS)
            self._progress_bar.set(1.0)
            self._phase_lbl.configure(text=t('status_done') + '.')
        elif self._stop_event.is_set():
            self._result_lbl.configure(text=t('stopped_msg'), text_color=WARNING)
            self.app.set_status(t('amzn_stopped'), WARNING)
        else:
            self._result_lbl.configure(
                text=f"{t('status_error')}: {error[:80]}",
                text_color=ERROR
            )
            self.app.set_status(t('amzn_error'), ERROR)

    # ==========================================================================
    #  LANGUAGE UPDATE
    # ==========================================================================

    def update_lang(self):
        saved_cat   = self._editor_cat
        was_running = self._session_start is not None
        self._stop_timer()
        for w in self.winfo_children():
            w.destroy()
        self._editor_cat = None
        self._editor_idx = None
        self._build()
        if saved_cat:
            self._select_editor_cat(saved_cat)
        if was_running:
            self._session_start = time.time()
            self._tick_timer()
        self._refresh_path_status()
