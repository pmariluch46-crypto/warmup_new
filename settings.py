import json
import os


class Settings:
    """
    Simple JSON-based settings storage.
    Compatible with dict-like .get(key, default) and .set(key, value).
    """

    def __init__(self, path="data/settings.json"):
        self.path = path
        self._data = {}

        # Ensure folder exists
        folder = os.path.dirname(self.path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)

        # Load settings if file exists
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    # ────────────────────────────────────────────────────────────────
    # dict-like GET with default (important!)
    # ────────────────────────────────────────────────────────────────
    def get(self, key, default=None):
        return self._data.get(key, default)

    # ────────────────────────────────────────────────────────────────
    # dict-like SET
    # ────────────────────────────────────────────────────────────────
    def set(self, key, value):
        self._data[key] = value

    # ────────────────────────────────────────────────────────────────
    # Save settings to disk
    # ────────────────────────────────────────────────────────────────
    def save_all(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print("Failed to save settings:", e)

    # ────────────────────────────────────────────────────────────────
    # Optional: allow dict-style access settings["key"]
    # ────────────────────────────────────────────────────────────────
    def __getitem__(self, key):
        return self._data.get(key)

    def __setitem__(self, key, value):
        self._data[key] = value
        self.save_all()
