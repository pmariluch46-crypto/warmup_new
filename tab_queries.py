"""
ui/tab_queries.py  --  Browse and edit the queries library.
"""

import csv
import io
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from core.query_selector import (
    load_queries, get_categories, add_query, remove_query, update_query
)
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
ROW_ALT  = "#f8fafc"


class QueriesTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=CT_BG, corner_radius=0)
        self.app = app
        self._selected_cat = None
        self._selected_idx = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 0))
        ctk.CTkLabel(hdr, text=t('queries_title'),
                     font=("Helvetica", 20, "bold"),
                     text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkButton(hdr, text=t('export_csv'), width=100, height=32,
                      font=("Helvetica", 12), fg_color=TEXT_SUB,
                      command=self._export_csv).pack(side="right", padx=(8, 0))
        ctk.CTkButton(hdr, text=t('import_csv'), width=100, height=32,
                      font=("Helvetica", 12), fg_color=ACCENT,
                      command=self._import_csv).pack(side="right")

        # Two-pane body
        pane = ctk.CTkFrame(self, fg_color="transparent")
        pane.grid(row=1, column=0, sticky="nsew", padx=24, pady=12)
        pane.grid_columnconfigure(1, weight=1)
        pane.grid_rowconfigure(0, weight=1)

        # Left: category list
        left = ctk.CTkFrame(pane, fg_color=CARD_BG, corner_radius=10,
                            border_width=1, border_color=BORDER, width=180)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left, text=t('categories'),
                     font=("Helvetica", 13, "bold"),
                     text_color=TEXT_MAIN).grid(
            row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        ctk.CTkFrame(left, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="sew", padx=8)

        cat_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent",
                                             corner_radius=0)
        cat_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        left.grid_columnconfigure(0, weight=1)

        self._cat_buttons = {}
        for cat in get_categories():
            btn = ctk.CTkButton(
                cat_scroll, text=cat, anchor="w",
                font=("Helvetica", 12), height=32,
                fg_color="transparent", text_color=TEXT_MAIN,
                hover_color=BORDER, corner_radius=6,
                command=lambda c=cat: self._select_category(c))
            btn.pack(fill="x", padx=4, pady=1)
            self._cat_buttons[cat] = btn

        # Right: query list + editor
        right = ctk.CTkFrame(pane, fg_color=CARD_BG, corner_radius=10,
                             border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Toolbar
        tb = ctk.CTkFrame(right, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self._cat_title = ctk.CTkLabel(tb, text=t('select_a_cat'),
                                        font=("Helvetica", 13, "bold"),
                                        text_color=TEXT_MAIN)
        self._cat_title.pack(side="left")
        self._count_lbl = ctk.CTkLabel(tb, text="",
                                        font=("Helvetica", 11), text_color=TEXT_SUB)
        self._count_lbl.pack(side="left", padx=8)
        ctk.CTkButton(tb, text=t('add'), width=72, height=28,
                      font=("Helvetica", 12), fg_color=SUCCESS,
                      command=self._add_query).pack(side="right", padx=(4, 0))
        ctk.CTkButton(tb, text=t('delete'), width=72, height=28,
                      font=("Helvetica", 12), fg_color=ERROR,
                      command=self._delete_query).pack(side="right", padx=4)
        ctk.CTkButton(tb, text=t('save'), width=72, height=28,
                      font=("Helvetica", 12), fg_color=ACCENT,
                      command=self._save_edit).pack(side="right")
        ctk.CTkFrame(right, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="sew", padx=8)

        # Listbox
        list_frame = ctk.CTkFrame(right, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self._listbox = tk.Listbox(list_frame, font=("Helvetica", 11),
                                    bg=CARD_BG, fg=TEXT_MAIN,
                                    selectbackground=ACCENT, selectforeground="#ffffff",
                                    bd=0, highlightthickness=0, activestyle="none",
                                    relief="flat")
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(list_frame, orient="vertical",
                           command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)

        # Edit area
        edit_frame = ctk.CTkFrame(right, fg_color="transparent")
        edit_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        edit_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(edit_frame, text=t('edit_query_lbl'),
                     font=("Helvetica", 11), text_color=TEXT_SUB).grid(
            row=0, column=0, sticky="w")
        self._edit_var = tk.StringVar()
        self._edit_entry = ctk.CTkEntry(edit_frame, textvariable=self._edit_var,
                                         height=32, font=("Helvetica", 12),
                                         fg_color=CT_BG, border_color=BORDER,
                                         text_color=TEXT_MAIN)
        self._edit_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._edit_entry.bind("<Return>", lambda e: self._save_edit())

    # ── Category selection ───────────────────────────────────
    def _select_category(self, cat):
        self._selected_cat = cat
        self._selected_idx = None
        self._edit_var.set("")
        for c, btn in self._cat_buttons.items():
            btn.configure(fg_color=ACCENT if c == cat else "transparent",
                          text_color="#ffffff" if c == cat else TEXT_MAIN)
        self._refresh_list()

    def _refresh_list(self):
        if not self._selected_cat:
            return
        data = load_queries()
        queries = data.get(self._selected_cat, [])
        self._listbox.delete(0, "end")
        for q in queries:
            self._listbox.insert("end", q)
        self._cat_title.configure(text=self._selected_cat)
        n = len(queries)
        self._count_lbl.configure(
            text=t('queries_count').format(n=n))

    def _on_list_select(self, event):
        sel = self._listbox.curselection()
        if sel:
            self._selected_idx = sel[0]
            self._edit_var.set(self._listbox.get(sel[0]))

    # ── CRUD ─────────────────────────────────────────────────
    def _add_query(self):
        if not self._selected_cat:
            messagebox.showwarning("WarmUpPro", t('select_a_cat'))
            return
        new_q = self._edit_var.get().strip()
        if not new_q:
            return
        add_query(self._selected_cat, new_q)
        self._edit_var.set("")
        self._refresh_list()

    def _delete_query(self):
        if self._selected_idx is None or not self._selected_cat:
            return
        q = self._listbox.get(self._selected_idx)
        if messagebox.askyesno(t('delete'), f'"{q}"?'):
            remove_query(self._selected_cat, q)
            self._selected_idx = None
            self._edit_var.set("")
            self._refresh_list()

    def _save_edit(self):
        if self._selected_idx is None or not self._selected_cat:
            return
        old_text = self._listbox.get(self._selected_idx)
        new_text = self._edit_var.get().strip()
        if not new_text:
            return
        update_query(self._selected_cat, old_text, new_text)
        self._refresh_list()
        if self._selected_idx < self._listbox.size():
            self._listbox.selection_set(self._selected_idx)
            self._listbox.see(self._selected_idx)

    # ── CSV ──────────────────────────────────────────────────
    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            title=t('export_csv'),
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        data = load_queries()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["category", "query"])
            for cat, queries in data.items():
                for q in queries:
                    writer.writerow([cat, q])
        messagebox.showinfo("WarmUpPro",
            f"{sum(len(v) for v in data.values())} queries exported.")

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title=t('import_csv'),
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        count = 0
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cat = row.get("category", "").strip()
                    q   = row.get("query", "").strip()
                    if cat and q:
                        add_query(cat, q)
                        count += 1
        except Exception as e:
            messagebox.showerror("Import failed", str(e))
            return
        messagebox.showinfo("WarmUpPro", f"{count} queries imported.")
        self._refresh_list()

    def on_show(self):
        if self._selected_cat:
            self._refresh_list()

    # ── Language update ──────────────────────────────────────
    def update_lang(self):
        saved_cat = self._selected_cat
        saved_idx = self._selected_idx
        for w in self.winfo_children():
            w.destroy()
        self._selected_cat = None
        self._selected_idx = None
        self._build()
        if saved_cat:
            self._select_category(saved_cat)
            if saved_idx is not None and saved_idx < self._listbox.size():
                self._listbox.selection_set(saved_idx)
                self._listbox.see(saved_idx)
                self._selected_idx = saved_idx
