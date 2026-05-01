import customtkinter as ctk

class MaterialSidebar(ctk.CTkFrame):
    def __init__(self, master, tabs, command, accent="#6750A4"):
        """
        tabs: [("Run", icon), ("Queries", icon), ...]
        command: callback(tab_name)
        """
        super().__init__(master, fg_color="#F5F5F7")
        self.command = command
        self.accent = accent
        self.buttons = {}

        self.grid_columnconfigure(0, weight=1)

        # Header
        title = ctk.CTkLabel(
            self, text="WarmUp New",
            font=("Segoe UI Variable", 18, "bold"),
            text_color="#1C1B1F"
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(20, 10))

        row = 1
        for name, icon in tabs:
            btn = ctk.CTkButton(
                self,
                text=name,
                image=icon,
                anchor="w",
                fg_color="transparent",
                hover_color="#E7E0EC",
                text_color="#1C1B1F",
                corner_radius=8,
                height=40,
                command=lambda n=name: self._on_click(n)
            )
            btn.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
            self.buttons[name] = btn
            row += 1

        # Language switcher
        self.lang_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.lang_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(20, 10))

        self.lang_en = ctk.CTkButton(
            self.lang_frame, text="EN", width=40,
            fg_color=self.accent, text_color="white",
            command=lambda: self._switch_lang("en")
        )
        self.lang_en.grid(row=0, column=0, padx=4)

        self.lang_ru = ctk.CTkButton(
            self.lang_frame, text="RU", width=40,
            fg_color="transparent", text_color="#1C1B1F",
            command=lambda: self._switch_lang("ru")
        )
        self.lang_ru.grid(row=0, column=1, padx=4)

    # ────────────────────────────────────────────────────────────────
    def _on_click(self, name):
        self.set_active(name)
        self.command(name)

    # ────────────────────────────────────────────────────────────────
    def set_active(self, name):
        for n, btn in self.buttons.items():
            if n == name:
                btn.configure(
                    fg_color=self.accent,
                    text_color="white",
                    hover_color=self.accent
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color="#1C1B1F",
                    hover_color="#E7E0EC"
                )

    # ────────────────────────────────────────────────────────────────
    def _switch_lang(self, lang):
        # здесь позже подключим i18n
        pass
