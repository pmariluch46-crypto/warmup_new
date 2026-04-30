import ctypes
import time
import platform
import random

# Определяем Windows версию
WIN_VERSION = platform.release()  # '10' или '11'

# Структуры для SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("mi", MOUSEINPUT)
    ]

# Флаги
MOUSEEVENTF_MOVE = 0x0001


def send_mouse_move(dx, dy):
    """Низкоуровневый сдвиг мыши через SendInput."""
    inp = INPUT()
    inp.type = 0  # INPUT_MOUSE
    inp.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def send_mouse_move_fallback(dx, dy):
    """Fallback для Windows 11 (mouse_event)."""
    ctypes.windll.user32.mouse_event(0x0001, dx, dy, 0, 0)


def move_absolute_smooth(x, y, steps=200):
    """Плавное движение мыши к абсолютной точке."""
    import pyautogui
    cur_x, cur_y = pyautogui.position()

    for i in range(1, steps + 1):
        t = i / steps

        nx = cur_x + (x - cur_x) * t
        ny = cur_y + (y - cur_y) * t

        dx = int(nx - cur_x)
        dy = int(ny - cur_y)

        # Выбор движка
        if WIN_VERSION == "10":
            send_mouse_move(dx, dy)
        else:
            send_mouse_move_fallback(dx, dy)

        cur_x, cur_y = nx, ny

        # 120–240 FPS
        time.sleep(random.uniform(0.004, 0.009))
