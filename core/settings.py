import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATH = BASE_DIR / "data" / "settings.json"


class Settings:
    """
    JSON-based settings storage.
    Supports both:
      - Attribute access:  settings.firefox_binary
      - Dict-style access: settings.get("key", default)
    """

    # Default values for all settings
    _DEFAULTS = {
        "firefox_binary":      "",
        "firefox_profile":     "",
        "geckodriver":         "",
        "close_after_session": True,
        "retry_crashes":       True,
        "max_retries":         1,
        "session_gap_min":     1,
        "read_speed":          0.7,
        "scheduled_jobs":      [],
        "scheduler_enabled":   False,
        "language":            "en",
    }

    def __init__(self, path=None):
        self.path  = Path(path) if path else DEFAULT_PATH
        self._data = dict(self._DEFAULTS)

        # Ensure folder exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Load from file
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
            except Exception:
                pass

    # ── Attribute-style access (settings.firefox_binary) ─────────────────
    def __getattr__(self, key):
        if key.startswith("_") or key == "path":
            raise AttributeError(key)
        if key in self._data:
            return self._data[key]
        raise AttributeError(f"Settings has no attribute '{key}'")

    def __setattr__(self, key, value):
        if key.startswith("_") or key == "path":
            super().__setattr__(key, value)
        else:
            self._data[key] = value

    # ── Dict-style access (settings.get("key", default)) ─────────────────
    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    # ── Dict-style bracket access (settings["key"]) ───────────────────────
    def __getitem__(self, key):
        return self._data.get(key)

    def __setitem__(self, key, value):
        self._data[key] = value
        self.save_all()

    # ── Save to disk ──────────────────────────────────────────────────────
    def save_all(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def __repr__(self):
        return f"Settings({self.path})"
