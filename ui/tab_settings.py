import os
import glob
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QFileDialog, QMessageBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.styles import (
    page_title, card, section_title, styled_checkbox,
    styled_slider, success_btn, secondary_btn,
    BG_PAGE, ACCENT, TEXT_SUB, TEXT_MAIN, BORDER
)


class SettingsTab(QWidget):
    def __init__(self, settings, main_window):
        super().__init__()
        self.settings    = settings
        self.main_window = main_window
        self.setStyleSheet(f"background: {BG_PAGE};")
        self._build_ui()
        self._load_into_ui()

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

        vbox.addWidget(page_title("Settings"))
        vbox.addWidget(self._build_paths_card())
        vbox.addWidget(self._build_browser_options_card())
        vbox.addWidget(self._build_session_gap_card())
        vbox.addWidget(self._build_reading_speed_card())
        vbox.addStretch()

        btn_save = success_btn("Save All Settings")
        btn_save.setFixedWidth(180)
        btn_save.clicked.connect(self._save)
        vbox.addWidget(btn_save)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_paths_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section_title("Firefox & Geckodriver Paths"))

        self.edit_binary  = self._path_row(lay, "Firefox binary (.exe)")
        self.edit_profile = self._path_row(lay, "Firefox profile folder", folder=True)
        self.edit_gecko   = self._path_row(lay, "Geckodriver (.exe)")

        btn_row = QHBoxLayout()
        btn_autodetect = secondary_btn("Auto-detect geckodriver")
        btn_autodetect.clicked.connect(self._autodetect_gecko)
        btn_autoprofile = secondary_btn("Auto-detect profile")
        btn_autoprofile.clicked.connect(self._autodetect_profile)
        btn_test = success_btn("Test paths")
        btn_test.setFixedWidth(110)
        btn_test.clicked.connect(self._test_paths)
        btn_row.addWidget(btn_autodetect)
        btn_row.addWidget(btn_autoprofile)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.test_result_lbl = QLabel("")
        self.test_result_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.test_result_lbl.setWordWrap(True)
        lay.addWidget(self.test_result_lbl)
        return c

    def _path_row(self, parent_layout, label, folder=False):
        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        parent_layout.addWidget(lbl)

        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setFixedHeight(32)
        edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {BORDER}; border-radius: 5px;
                background: white; font-family: 'Segoe UI'; font-size: 9pt;
                padding: 0 10px; color: {TEXT_MAIN};
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """)
        btn = secondary_btn("Browse...")
        btn.setFixedWidth(90)
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda _, e=edit, f=folder: self._browse(e, f))
        row.addWidget(edit, 1)
        row.addWidget(btn)
        parent_layout.addLayout(row)
        return edit

    def _build_browser_options_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(section_title("Browser Options"))

        self.cb_close = styled_checkbox("Close browser after session")
        self.cb_retry = styled_checkbox("Retry crashed phases")
        self.cb_close.setChecked(True)
        self.cb_retry.setChecked(True)
        lay.addWidget(self.cb_close)
        lay.addWidget(self.cb_retry)
        self.sl_retries = self._slider_row(lay, "Max retries per phase", 1, 10, 1)
        return c

    def _build_session_gap_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(section_title("Session Gap"))
        self.sl_gap = self._slider_row(lay, "Min gap between sessions (min)", 0, 60, 1)
        return c

    def _build_reading_speed_card(self):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(section_title("Reading Speed"))

        row = QHBoxLayout()
        lbl = QLabel("Read speed (0=fast, 1=slow):")
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        lbl.setFixedWidth(220)
        self.sl_read = styled_slider(0, 100, 70)
        self.val_read = QLabel("0.7")
        self.val_read.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.val_read.setStyleSheet(f"color: {ACCENT}; min-width: 32px;")
        self.sl_read.valueChanged.connect(
            lambda v: self.val_read.setText(f"{v/100:.1f}"))
        row.addWidget(lbl)
        row.addWidget(self.sl_read, 1)
        row.addWidget(self.val_read)
        lay.addLayout(row)
        return c

    def _slider_row(self, parent_layout, label, min_v, max_v, default):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {TEXT_MAIN};")
        lbl.setFixedWidth(220)
        sl = styled_slider(min_v, max_v, default)
        val_lbl = QLabel(str(default))
        val_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {ACCENT}; min-width: 28px;")
        sl.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))
        row.addWidget(lbl)
        row.addWidget(sl, 1)
        row.addWidget(val_lbl)
        parent_layout.addLayout(row)
        return sl

    def _browse(self, edit_widget, folder=False):
        if folder:
            path = QFileDialog.getExistingDirectory(self, "Select folder")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select file", "", "Executables (*.exe);;All files (*.*)")
        if path:
            edit_widget.setText(path)

    def _autodetect_gecko(self):
        base = Path(__file__).resolve().parent.parent
        candidates = [
            base / "drivers" / "geckodriver.exe",
            base / "geckodriver.exe",
        ]
        for c in candidates:
            if c.exists():
                self.edit_gecko.setText(str(c))
                return
        QMessageBox.information(self, "Not found",
            "geckodriver.exe not found. Place it in the drivers/ folder.")

    def _autodetect_profile(self):
        patterns = [
            os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles\*.default-release"),
            os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles\*.default"),
            os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles\*"),
        ]
        for pattern in patterns:
            matches = glob.glob(pattern)
            if matches:
                self.edit_profile.setText(matches[0])
                return
        QMessageBox.information(self, "Not found",
            "Firefox profile not found. Set path manually.")

    def _test_paths(self):
        binary  = self.edit_binary.text().strip()
        profile = self.edit_profile.text().strip()
        gecko   = self.edit_gecko.text().strip()
        errors = []
        if not os.path.exists(binary):  errors.append("Firefox binary not found")
        if not os.path.exists(profile): errors.append("Firefox profile not found")
        if not os.path.exists(gecko):   errors.append("Geckodriver not found")

        if errors:
            self.test_result_lbl.setText("❌  " + "  |  ".join(errors))
            self.test_result_lbl.setStyleSheet("color: #c62828; font-weight: bold;")
        else:
            self.test_result_lbl.setText("✅  All paths configured correctly.")
            self.test_result_lbl.setStyleSheet("color: #2e7d32; font-weight: bold;")

    def _load_into_ui(self):
        try:
            self.edit_binary.setText(self.settings.get("firefox_binary", ""))
            self.edit_profile.setText(self.settings.get("firefox_profile", ""))
            self.edit_gecko.setText(self.settings.get("geckodriver", ""))
            self.cb_close.setChecked(self.settings.get("close_after_session", True))
            self.cb_retry.setChecked(self.settings.get("retry_crashes", True))
            self.sl_retries.setValue(self.settings.get("max_retries", 1))
            self.sl_gap.setValue(self.settings.get("session_gap_min", 1))
            speed = self.settings.get("read_speed", 0.7)
            self.sl_read.setValue(int(float(speed) * 100))
        except Exception:
            pass

    def _save(self):
        try:
            self.settings.set("firefox_binary",      self.edit_binary.text().strip())
            self.settings.set("firefox_profile",     self.edit_profile.text().strip())
            self.settings.set("geckodriver",          self.edit_gecko.text().strip())
            self.settings.set("close_after_session",  self.cb_close.isChecked())
            self.settings.set("retry_crashes",        self.cb_retry.isChecked())
            self.settings.set("max_retries",          self.sl_retries.value())
            self.settings.set("session_gap_min",      self.sl_gap.value())
            self.settings.set("read_speed",           self.sl_read.value() / 100.0)
            self.settings.save_all()
            QMessageBox.information(self, "Saved", "Settings saved successfully.")
            try:
                self.main_window.tab_run._check_firefox()
                self.main_window.tab_amazon._check_firefox()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
