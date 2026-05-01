from main_window import MainWindow
from core.settings import Settings
from core.session_manager import SessionManager

if __name__ == "__main__":
    settings = Settings()
    session = SessionManager(settings)

    app = MainWindow(settings, session)
    app.mainloop()
