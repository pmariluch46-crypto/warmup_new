import os
import customtkinter as ctk
from tkinter import filedialog

class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, settings):
        super().__init__(master)
        self.settings = settings

        # Accent color (пока константа, потом можно привязать к Windows accent)
        self.accent_color = "#6750A4"
        self.error_color = "#B3261E"
        self.ok_color = "#1B873F"

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        # Главный контейнер
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Карточка настроек (Elevated Material 3)
        self.settings_card = ctk.CTkFrame(self, corner_radius=16)
        self.settings_card.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        self.settings_card.grid_columnconfigure(0, weight=1)
        self.settings_card.grid_columnconfigure(1, weight=0)

        # Заголовок
        self.title_label = ctk.CTkLabel(
            self.settings_card,
            text="Settings",
            font=("Segoe UI Variable", 20, "bold")
        )
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 12))

        row = 1

        # Firefox binary
        self._add_labeled_entry(
            parent=self.settings_card,
            row=row,
            label_text="Firefox binary",
            attr_name="firefox_entry",
            browse_command=self.browse_firefox
        )
        row += 1

        # Firefox profile
        self._add_labeled_entry(
            parent=self.settings_card,
            row=row,
            label_text="Firefox profile",
            attr_name="profile_entry",
            browse_command=self.browse_profile
        )
        row += 1

        # Geckodriver path
        self._add_labeled_entry(
            parent=self.settings_card,
            row=row,
            label_text="Geckodriver path",
            attr_name="gecko_entry",
            browse_command=self.browse_gecko
        )
        row += 1

        # Auto-close browser
        self.auto_close_var = ctk.BooleanVar(value=True)
        self.auto_close_checkbox = ctk.CTkCheckBox(
            self.settings_card,
            text="Auto-close browser",
            variable=self.auto_close_var,
            fg_color=self.accent_color
        )
        self.auto_close_checkbox.grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(12, 4))
        row += 1

        # Auto-detect button
        self.auto_detect_button = ctk.CTkButton(
            self.settings_card,
            text="Auto-detect",
            fg_color=self.accent_color,
            command=self.auto_detect,
            height=32
        )
        self.auto_detect_button.grid(row=row, column=0, sticky="w", padx=20, pady=(8, 16))
        row += 1

        # Карточка проверки путей
        self.check_card = ctk.CTkFrame(self, corner_radius=16)
        self.check_card.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.check_card.grid_columnconfigure(0, weight=0)
        self.check_card.grid_columnconfigure(1, weight=1)
        self.check_card.grid_columnconfigure(2, weight=0)

        self.check_button = ctk.CTkButton(
            self.check_card,
            text="Check paths",
            fg_color=self.accent_color,
            command=self.check_paths,
            height=32,
            width=120
        )
        self.check_button.grid(row=0, column=0, padx=20, pady=(14, 6), sticky="w")

        # Чип OK / Not OK
        self.status_chip = ctk.CTkLabel(
            self.check_card,
            text="",
            fg_color="transparent",
            corner_radius=999,
            font=("Segoe UI Variable", 13, "bold")
        )
        self.status_chip.grid(row=0, column=2, padx=20, pady=(14, 6), sticky="e")

        # Лог проверки
        self.result_label = ctk.CTkLabel(
            self.check_card,
            text="",
            font=("Segoe UI Variable", 13),
            justify="left"
        )
        self.result_label.grid(row=1, column=0, columnspan=3, padx=20, pady=(0, 14), sticky="w")

        # Флаг анимации
        self._checking = False

    def _add_labeled_entry(self, parent, row, label_text, attr_name, browse_command):
        label = ctk.CTkLabel(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", padx=20, pady=(8, 0))

        entry = ctk.CTkEntry(parent, width=420)
        entry.grid(row=row + 1, column=0, sticky="we", padx=20, pady=(4, 8))

        browse_button = ctk.CTkButton(
            parent,
            text="Browse",
            width=90,
            height=32,
            fg_color=self.accent_color,
            command=browse_command
        )
        browse_button.grid(row=row + 1, column=1, sticky="e", padx=(0, 20), pady=(4, 8))

        setattr(self, attr_name, entry)

    # ====== LOAD / SAVE ======

    def _load_settings(self):
        # если у тебя есть settings dict/объект — подставь реальные ключи
        self.firefox_entry.insert(0, self.settings.get("firefox_binary", ""))
        self.profile_entry.insert(0, self.settings.get("firefox_profile", ""))
        self.gecko_entry.insert(0, self.settings.get("geckodriver_path", ""))
        self.auto_close_var.set(self.settings.get("auto_close_browser", True))

    def save_settings(self):
        self.settings["firefox_binary"] = self.firefox_entry.get()
        self.settings["firefox_profile"] = self.profile_entry.get()
        self.settings["geckodriver_path"] = self.gecko_entry.get()
        self.settings["auto_close_browser"] = self.auto_close_var.get()

    # ====== BROWSE ======

    def browse_firefox(self):
        path = filedialog.askopenfilename(title="Select Firefox binary")
        if path:
            self.firefox_entry.delete(0, "end")
            self.firefox_entry.insert(0, path)

    def browse_profile(self):
        path = filedialog.askdirectory(title="Select Firefox profile folder")
        if path:
            self.profile_entry.delete(0, "end")
            self.profile_entry.insert(0, path)

    def browse_gecko(self):
        path = filedialog.askopenfilename(title="Select Geckodriver executable")
        if path:
            self.gecko_entry.delete(0, "end")
            self.gecko_entry.insert(0, path)

    # ====== AUTO-DETECT / AUTO-FIX ======

    def auto_detect(self):
        changed = False

        possible_firefox = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
        ]
        if not os.path.exists(self.firefox_entry.get()):
            for path in possible_firefox:
                if os.path.exists(path):
                    self.firefox_entry.delete(0, "end")
                    self.firefox_entry.insert(0, path)
                    changed = True
                    break

        possible_gecko = [
            r"Q:\warmup_new\drivers\geckodriver.exe",
            r"C:\tools\geckodriver.exe"
        ]
        if not os.path.exists(self.gecko_entry.get()):
            for path in possible_gecko:
                if os.path.exists(path):
                    self.gecko_entry.delete(0, "end")
                    self.gecko_entry.insert(0, path)
                    changed = True
                    break

        if changed:
            self.result_label.configure(text="Auto-detect: some paths were updated ✅", text_color=self.ok_color)
        else:
            self.result_label.configure(text="Auto-detect: nothing changed", text_color=self.error_color)

    def auto_fix_paths(self, missing):
        """
        missing: dict с флагами, что не найдено
        """
        fixed = False

        if missing.get("firefox"):
            self.auto_detect()  # пробуем через auto_detect
            fixed = True

        if missing.get("gecko"):
            self.auto_detect()
            fixed = True

        if missing.get("profile"):
            # если профиль не найден — предлагаем выбрать
            path = filedialog.askdirectory(title="Select Firefox profile folder")
            if path:
                self.profile_entry.delete(0, "end")
                self.profile_entry.insert(0, path)
                fixed = True

        if fixed:
            self.result_label.configure(text="Auto-fix applied. Run check again.", text_color=self.ok_color)
        else:
            self.result_label.configure(text="Auto-fix could not resolve all issues.", text_color=self.error_color)

    # ====== CHECK PATHS + АНИМАЦИЯ ======

    def check_paths(self):
        if self._checking:
            return

        self._checking = True
        self.check_button.configure(state="disabled", text="Checking…")
        self.status_chip.configure(text="", fg_color="transparent")
        self.result_label.configure(text="", text_color=None)

        # имитация анимации/задержки проверки
        self.after(600, self._finish_check_paths)

    def _finish_check_paths(self):
        self._checking = False
        self.check_button.configure(state="normal", text="Check paths")

        results = []
        ok = True
        missing = {"firefox": False, "profile": False, "gecko": False}

        firefox_path = self.firefox_entry.get().strip()
        profile_path = self.profile_entry.get().strip()
        gecko_path = self.gecko_entry.get().strip()

        if os.path.exists(firefox_path):
            results.append("Firefox binary: OK ✅")
        else:
            results.append("Firefox binary: Not found ❌")
            ok = False
            missing["firefox"] = True

        if os.path.exists(profile_path):
            results.append("Firefox profile: OK ✅")
        else:
            results.append("Firefox profile: Not found ❌")
            ok = False
            missing["profile"] = True

        if os.path.exists(gecko_path):
            results.append("Geckodriver: OK ✅")
        else:
            results.append("Geckodriver: Not found ❌")
            ok = False
            missing["gecko"] = True

        if ok:
            self.status_chip.configure(
                text="OK",
                fg_color=self.ok_color,
                text_color="white",
                padx=14,
                pady=4
            )
            self.result_label.configure(text="\n".join(results), text_color=self.ok_color)
        else:
            self.status_chip.configure(
                text="Not OK",
                fg_color=self.error_color,
                text_color="white",
                padx=14,
                pady=4
            )
            self.result_label.configure(text="\n".join(results), text_color=self.error_color)
            # авто‑фиксация
            self.auto_fix_paths(missing)
