import sys
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QPushButton,
    QLabel, QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CATEGORIES_FILE = CONFIG_DIR / "categories.json"
QUERIES_FILE = CONFIG_DIR / "queries.json"


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WarmUPro – Amazon Config")

        self.categories = load_json(CATEGORIES_FILE, {})
        self.queries = load_json(QUERIES_FILE, {})

        self.current_category = None

        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # -------- LEFT: Active Categories --------
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Active Categories"))

        self.category_list = QListWidget()
        self.category_list.itemChanged.connect(self.on_category_checked)
        self.category_list.currentItemChanged.connect(self.on_category_selected)
        left_layout.addWidget(self.category_list)

        main_layout.addLayout(left_layout, 1)

        # -------- RIGHT: Query Editor --------
        right_layout = QVBoxLayout()
        self.category_label = QLabel("Category: -")
        right_layout.addWidget(self.category_label)

        self.query_list = QListWidget()
        right_layout.addWidget(self.query_list)

        # input + buttons
        input_layout = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("New or edited query...")
        input_layout.addWidget(self.query_input)

        btn_add = QPushButton("+ Add")
        btn_add.clicked.connect(self.add_query)
        input_layout.addWidget(btn_add)

        btn_delete = QPushButton("Delete")
        btn_delete.clicked.connect(self.delete_query)
        input_layout.addWidget(btn_delete)

        right_layout.addLayout(input_layout)

        btn_save = QPushButton("Save All")
        btn_save.clicked.connect(self.save_all)
        right_layout.addWidget(btn_save)

        main_layout.addLayout(right_layout, 2)

        self.populate_categories()

    # ---------- Data binding ----------

    def populate_categories(self):
        self.category_list.blockSignals(True)
        self.category_list.clear()

        if not self.categories:
            self.categories = {
                "Electronics": True,
                "Books": True,
                "Tools & Home Improve": True
            }

        for name, active in self.categories.items():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Checked if active else Qt.CheckState.Unchecked)
            self.category_list.addItem(item)

        self.category_list.blockSignals(False)

        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(0)

    def on_category_checked(self, item):
        name = item.text()
        self.categories[name] = (item.checkState() == Qt.CheckState.Checked)

    def on_category_selected(self, current, previous):
        if current is None:
            self.current_category = None
            self.category_label.setText("Category: -")
            self.query_list.clear()
            return

        name = current.text()
        self.current_category = name
        self.category_label.setText(f"Category: {name}")
        self.load_queries_for_category(name)

    def load_queries_for_category(self, category):
        self.query_list.clear()
        qlist = self.queries.get(category, [])
        for q in qlist:
            self.query_list.addItem(q)

    # ---------- Query actions ----------

    def add_query(self):
        if not self.current_category:
            QMessageBox.warning(self, "No category", "Select a category first.")
            return
        text = self.query_input.text().strip()
        if not text:
            return
        self.query_list.addItem(text)
        self.query_input.clear()
        self.sync_queries_from_ui()

    def delete_query(self):
        if not self.current_category:
            return
        row = self.query_list.currentRow()
        if row < 0:
            return
        self.query_list.takeItem(row)
        self.sync_queries_from_ui()

    def sync_queries_from_ui(self):
        if not self.current_category:
            return
        qlist = []
        for i in range(self.query_list.count()):
            qlist.append(self.query_list.item(i).text())
        self.queries[self.current_category] = qlist

    # ---------- Save ----------

    def save_all(self):
        self.sync_queries_from_ui()
        save_json(CATEGORIES_FILE, self.categories)
        save_json(QUERIES_FILE, self.queries)
        QMessageBox.information(self, "Saved", "Categories and queries saved.")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(900, 500)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
