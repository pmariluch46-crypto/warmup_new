import customtkinter as ctk
import tkinter as tk

from ui.material_sidebar import MaterialSidebar
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

        # Window
        self.title("WarmUp New — CustomTkinter Edition")
        try:
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.geometry("1200x750")
        self.minsize(1000, 650)

        # Material 3 style base
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar (Material 3 Elevated, left column)
        self.sidebar = MaterialSidebar(
            self,
            tabs=[
                ("Run", None),
                ("Queries", None),
                ("Amazon", None),
                ("Scheduler", None),
                ("History", None),
                ("Settings", None),
            ],
            command=self._switch_tab,
            accent="#6750A4"
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        # Content area (right side)
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Tabs (frames)
        self.tabs = {
            "Run": RunTab(self.content, self),
            "Queries": QueriesTab(self.content, self.settings),
            "Amazon": AmazonTab(self.content, self),
            "Scheduler": SchedulerTab(self.content, self.settings),
            "History": HistoryTab(self.content, self.settings),
            "Settings": SettingsTab(self.content, self.settings),
        }

        # Place all tabs but hide them initially
        for tab in self.tabs.values():
            tab.grid(row=0, column=0, sticky="nsew")
            tab.grid_remove()

        # Default tab
        self._switch_tab("Run")

    # ────────────────────────────────────────────────────────────────
    def _switch_tab(self, name: str):
        # Hide all
        for tab in self.tabs.values():
            tab.grid_remove()

        # Show selected
        if name in self.tabs:
            self.tabs[name].grid()
            self.sidebar.set_active(name)

    # ────────────────────────────────────────────────────────────────
    def save_settings(self):
        """
        Прокси-метод, если SettingsTab или другие части UI
        захотят инициировать сохранение настроек через MainWindow.
        """
        if hasattr(self.settings, "save_all"):
            self.settings.save_all()
