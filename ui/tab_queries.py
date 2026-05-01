import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QTextEdit,
    QFrame, QFileDialog, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.styles import (
    page_title, card, section_title, primary_btn, danger_btn,
    secondary_btn, BG_PAGE, ACCENT, TEXT_SUB, TEXT_MAIN, BORDER
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR  = BASE_DIR / "data"

CATEGORIES = [
    "News & Events", "Weather", "YouTube", "Reddit",
    "Wikipedia", "Shopping", "Food & Recipes", "Health & Wellness",
    "Travel & Tourism", "Technology",
]


class QueriesTab(QWidget):
    def __init__(self, settings, main_window):
        super().__init__()
        self.settings     = settings
        self.main_window  = main_window
        self._queries     = {}
        self._current_cat = None

        self.setStyleSheet(f"background: {BG_PAGE};")
        self._load_queries()
        self._build_ui()

    # ── Data ─────────────────────────────────────────────────────────────────
    def _load_queries(self):
        path = DATA_DIR / "queries.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._queries = json.load(f)
            except Exception:
                self._queries = {}

    def _save_queries(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(DATA_DIR / "queries.json", "w", encoding="utf-8") as f:
                json.dump(self._queries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        # Title + CSV buttons
        title_row = QHBoxLayout()
        title_row.addWidget(page_title("Query Library"))
        title_row.addStretch()
        btn_import = primary_btn("Import CSV")
        btn_import.setFixedWidth(110)
        btn_import.clicked.connect(self._import_csv)
        btn_export = secondary_btn("Export CSV")
        btn_export.setFixedWidth(110)
        btn_export.clicked.connect(self._export_csv)
        title_row.addWidget(btn_import)
        title_row.addWidget(btn_export)
        outer.addLayout(title_row)

        # ── Main card ─────────────────────────────────────────────────────
        c = card()
        c_lay = QVBoxLayout(c)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)

        # Action buttons row
        btn_bar = QWidget()
        btn_bar.setStyleSheet(f"background: #f8f9fc; border-bottom: 1px solid {BORDER};")
        bar_lay = QHBoxLayout(btn_bar)
        bar_lay.setContentsMargins(16, 10, 16, 10)
        bar_lay.setSpacing(8)
        bar_lay.addStretch()

        self.btn_save = secondary_btn("Save")
        self.btn_save.setFixedWidth(70)
        self.btn_save.clicked.connect(self._save_current)

        self.btn_delete = danger_btn("Delete")
        self.btn_delete.setFixedWidth(80)
        self.btn_delete.clicked.connect(self._delete_selected)

        self.btn_add = primary_btn("+ Add")
        self.btn_add.setFixedWidth(80)
        self.btn_add.clicked.connect(self._add_query)

        bar_lay.addWidget(self.btn_save)
        bar_lay.addWidget(self.btn_delete)
        bar_lay.addWidget(self.btn_add)
        c_lay.addWidget(btn_bar)

        # Splitter: categories | queries
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #e0e5f0; width: 1px; }")

        # Left: categories
        cat_widget = QWidget()
        cat_widget.setStyleSheet("background: white;")
        cat_vbox = QVBoxLayout(cat_widget)
        cat_vbox.setContentsMargins(0, 0, 0, 0)
        cat_vbox.setSpacing(0)

        cat_hdr = QLabel("Categories")
        cat_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        cat_hdr.setStyleSheet(
            f"color: {TEXT_SUB}; padding: 12px 16px 8px 16px;"
            f" border-bottom: 1px solid {BORDER};")
        cat_vbox.addWidget(cat_hdr)

        self.cat_list = QListWidget()
        self.cat_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }}
            QListWidget::item {{
                padding: 9px 16px;
                color: {TEXT_MAIN};
                border-bottom: 1px solid #f0f2f8;
            }}
            QListWidget::item:selected {{
                background: #e8f0fe;
                color: {ACCENT};
                font-weight: bold;
            }}
            QListWidget::item:hover:!selected {{
                background: #f4f6fc;
            }}
        """)
        for cat in CATEGORIES:
            self.cat_list.addItem(cat)
        self.cat_list.currentRowChanged.connect(self._on_cat_selected)
        cat_vbox.addWidget(self.cat_list)
        splitter.addWidget(cat_widget)

        # Right: queries + edit
        q_widget = QWidget()
        q_widget.setStyleSheet("background: white;")
        q_vbox = QVBoxLayout(q_widget)
        q_vbox.setContentsMargins(0, 0, 0, 0)
        q_vbox.setSpacing(0)

        self.q_header = QLabel("Select a category")
        self.q_header.setFont(QFont("Segoe UI", 10))
        self.q_header.setStyleSheet(
            f"color: {TEXT_SUB}; padding: 12px 16px 8px 16px;"
            f" border-bottom: 1px solid {BORDER};")
        q_vbox.addWidget(self.q_header)

        self.query_list = QListWidget()
        self.query_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 7px 16px;
                color: {TEXT_MAIN};
                border-bottom: 1px solid #f8f9fc;
            }}
            QListWidget::item:selected {{
                background: #e8f0fe;
                color: {TEXT_MAIN};
            }}
        """)
        self.query_list.currentRowChanged.connect(self._on_query_selected)
        q_vbox.addWidget(self.query_list, 1)

        # Edit bar at bottom
        edit_bar = QWidget()
        edit_bar.setStyleSheet(
            f"background: #f8f9fc; border-top: 1px solid {BORDER};")
        edit_lay = QVBoxLayout(edit_bar)
        edit_lay.setContentsMargins(16, 8, 16, 8)
        edit_lbl = QLabel("Edit query:")
        edit_lbl.setFont(QFont("Segoe UI", 8))
        edit_lbl.setStyleSheet(f"color: {TEXT_SUB};")
        edit_lay.addWidget(edit_lbl)
        self.query_edit = QTextEdit()
        self.query_edit.setFixedHeight(52)
        self.query_edit.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {BORDER};
                border-radius: 4px;
                background: white;
                font-family: 'Segoe UI';
                font-size: 9pt;
                padding: 4px 8px;
            }}
        """)
        edit_lay.addWidget(self.query_edit)
        q_vbox.addWidget(edit_bar)
        splitter.addWidget(q_widget)

        splitter.setSizes([260, 740])
        c_lay.addWidget(splitter, 1)
        outer.addWidget(c, 1)

    # ── Actions ──────────────────────────────────────────────────────────────
    def _on_cat_selected(self, row):
        if row < 0 or row >= len(CATEGORIES):
            return
        self._current_cat = CATEGORIES[row]
        qs = self._queries.get(self._current_cat, [])
        self.q_header.setText(
            f"{self._current_cat}  —  {len(qs)} queries")
        self.query_list.clear()
        for q in qs:
            self.query_list.addItem(q)

    def _on_query_selected(self, row):
        if row < 0 or not self._current_cat:
            return
        qs = self._queries.get(self._current_cat, [])
        if row < len(qs):
            self.query_edit.setPlainText(qs[row])

    def _add_query(self):
        if not self._current_cat:
            QMessageBox.information(self, "Info", "Select a category first.")
            return
        text = self.query_edit.toPlainText().strip()
        if not text:
            return
        self._queries.setdefault(self._current_cat, []).append(text)
        self.query_list.addItem(text)
        self.query_edit.clear()
        self._refresh_header()

    def _delete_selected(self):
        if not self._current_cat:
            return
        row = self.query_list.currentRow()
        if row < 0:
            return
        self.query_list.takeItem(row)
        qs = self._queries.get(self._current_cat, [])
        if row < len(qs):
            qs.pop(row)
        self._refresh_header()

    def _save_current(self):
        if self._current_cat:
            qs = [self.query_list.item(i).text()
                  for i in range(self.query_list.count())]
            self._queries[self._current_cat] = qs
        self._save_queries()
        QMessageBox.information(self, "Saved", "Queries saved successfully.")

    def _refresh_header(self):
        if self._current_cat:
            n = len(self._queries.get(self._current_cat, []))
            self.q_header.setText(f"{self._current_cat}  —  {n} queries")

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        cat, query = row[0].strip(), row[1].strip()
                        if cat and query:
                            self._queries.setdefault(cat, []).append(query)
            self._save_queries()
            if self._current_cat:
                self._on_cat_selected(
                    CATEGORIES.index(self._current_cat)
                    if self._current_cat in CATEGORIES else -1)
            QMessageBox.information(self, "Imported", "CSV imported successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Import Error", str(e))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "queries.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for cat, qs in self._queries.items():
                    for q in qs:
                        writer.writerow([cat, q])
            QMessageBox.information(self, "Exported", "Queries exported successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))
