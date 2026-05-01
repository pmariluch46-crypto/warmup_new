import customtkinter as ctk
from tkinter import ttk
import traceback

from ui.tab_run import RunTab
from ui.tab_queries import QueriesTab
from ui.tab_amazon import AmazonTab
from ui.tab_scheduler import SchedulerTab
from ui.tab_history import HistoryTab
from ui.tab_settings import SettingsTab


class MainWindow(ctk.CTk):
    def __init__(self, settings, session):
        super().__init__()

        self.settings = settings
        self.session = session

        self.title("WarmUp New — CustomTkinter Edition")
        self.iconbitmap("icon.ico")
        self.geometry("1100x700")
        self.minsize(900, 600)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self._add_tabs()

    def _add_tabs(self):
        # RunTab
        try:
            tab_run = RunTab(self, self)
            self.notebook.add(tab_run, text="Run")
        except Exception:
            print("\n\n=== ERROR IN RUNTAB ===")
            traceback.print_exc()

        # QueriesTab — получает settings
        tab_queries = QueriesTab(self, self.settings)
        self.notebook.add(tab_queries, text="Queries")

        # AmazonTab — получает MainWindow
        try:
            tab_amazon = AmazonTab(self, self)
            self.notebook.add(tab_amazon, text="Amazon")
        except Exception:
            print("\n\n=== ERROR IN AMAZONTAB ===")
            traceback.print_exc()

        # SchedulerTab — получает settings
        tab_scheduler = SchedulerTab(self, self.settings)
        self.notebook.add(tab_scheduler, text="Scheduler")

        # HistoryTab — получает settings
        tab_history = HistoryTab(self, self.settings)
        self.notebook.add(tab_history, text="History")

        # SettingsTab — получает MainWindow (исправлено!)
        try:
            tab_settings = SettingsTab(self, self)
            self.notebook.add(tab_settings, text="Settings")
        except Exception:
            print("\n\n=== ERROR IN SETTINGSTAB ===")
            traceback.print_exc()

    def save_settings(self):
        self.settings.save_all()
