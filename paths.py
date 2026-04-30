"""
core/paths.py  --  Persistent data-directory resolution.

When running as a PyInstaller single-file EXE, __file__ inside frozen modules
points to a temporary extraction directory that is deleted on exit — settings
and edits would be lost every session.

This module always resolves the data directory to a folder NEXT TO the EXE
(or next to the project root when running from source), so all user data
survives across restarts.

First-run behaviour for JSON data files:
  If the persistent file doesn't exist yet, it is copied from the bundled
  read-only version inside the EXE (sys._MEIPASS).  After that the user's
  edits are preserved in the persistent copy.
"""

import os
import sys
import shutil


def data_dir() -> str:
    """Absolute path to the persistent data directory."""
    if getattr(sys, 'frozen', False):
        # Running as EXE — save next to the EXE file
        return os.path.join(os.path.dirname(sys.executable), 'data')
    # Running from source
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')


def data_file(filename: str) -> str:
    """
    Return the absolute path to a data file in the persistent directory.
    On the first EXE run, copies the bundled default from inside the EXE.
    """
    dest = os.path.join(data_dir(), filename)
    if not os.path.exists(dest):
        os.makedirs(data_dir(), exist_ok=True)
        if getattr(sys, 'frozen', False):
            # Pull the default from the PyInstaller bundle
            src = os.path.join(sys._MEIPASS, 'data', filename)
            if os.path.exists(src):
                shutil.copy2(src, dest)
    return dest
