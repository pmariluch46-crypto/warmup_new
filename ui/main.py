import sys
from pathlib import Path

# Ensure project root is in sys.path so `core` and `ui` imports work
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from core.settings import Settings
from ui.main_window import MainWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("WarmUpPro")

    icon_path = BASE_DIR / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = Settings()
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())
