"""
core/geckodriver_util.py  --  Locate or extract geckodriver.exe.
"""

import os
import sys
import shutil
import tempfile

# Known locations to search (in priority order)
_SEARCH_PATHS = [
    # Bundled inside PyInstaller .exe
    lambda: os.path.join(getattr(sys, '_MEIPASS', ''), 'assets', 'geckodriver.exe'),
    # App assets folder (dev mode)
    lambda: os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'assets', 'geckodriver.exe'),
    # Existing AutoBrowse_Transfer installation
    lambda: r"C:\Users\Administrator\AppData\Roaming\adspower_global\cwd_global\flower_141\geckodriver.exe",
    # Desktop AutoBrowse_Transfer folder
    lambda: os.path.join(os.path.expanduser("~"), "Desktop",
                         "AutoBrowse_Transfer", "geckodriver.exe"),
    # System PATH
    lambda: shutil.which("geckodriver") or "",
]


def find():
    """
    Return the path to geckodriver.exe if found, else empty string.
    When running as a PyInstaller bundle, extracts to a temp file first.
    """
    for fn in _SEARCH_PATHS:
        try:
            path = fn()
            if path and os.path.isfile(path):
                # If inside a PyInstaller bundle, copy to temp so it's executable
                if getattr(sys, 'frozen', False) and '_MEIPASS' in path:
                    dst = os.path.join(tempfile.gettempdir(),
                                       'warmuppro_geckodriver.exe')
                    shutil.copy2(path, dst)
                    return dst
                return path
        except Exception:
            continue
    return ""


def auto_detect_profile(firefox_binary_path):
    """
    Given a path to firefox.exe inside a FirefoxPortable installation,
    try to auto-detect the profile directory.
    Looks for Data/profile relative to the FirefoxPortable root.
    """
    if not firefox_binary_path:
        return ""
    # Walk up from the binary to find FirefoxPortable root
    current = os.path.dirname(firefox_binary_path)
    for _ in range(5):
        candidate = os.path.join(current, "Data", "profile")
        if os.path.isdir(candidate):
            return candidate
        current = os.path.dirname(current)
    return ""


def validate(firefox_binary, firefox_profile, geckodriver_path):
    """
    Returns (ok: bool, message: str)
    """
    if not firefox_binary or not os.path.isfile(firefox_binary):
        return False, f"Firefox binary not found: {firefox_binary}"
    if not firefox_profile or not os.path.isdir(firefox_profile):
        return False, f"Firefox profile directory not found: {firefox_profile}"
    if not geckodriver_path or not os.path.isfile(geckodriver_path):
        bundled = find()
        if bundled:
            geckodriver_path = bundled
        else:
            return False, f"geckodriver not found: {geckodriver_path}"
    return True, "All paths OK"
