import ctypes
import time
import random

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


MOUSEEVENTF_MOVE = 0x0001

# Накопитель субпиксельных остатков — ключ к плавности
_remainder_x = 0.0
_remainder_y = 0.0


def _send_relative(dx, dy):
    """Низкоуровневый сдвиг мыши через SendInput."""
    inp = INPUT()
    inp.type = 0
    inp.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def reset_remainder():
    """Сбросить накопитель (вызывать перед новым движением)."""
    global _remainder_x, _remainder_y
    _remainder_x = 0.0
    _remainder_y = 0.0


def apply_relative(dx, dy, delay: float = None):
    """
    Применяет относительное движение с накопительным округлением.

    dx, dy  — субпиксельные смещения (могут быть < 1.0)
    delay   — задержка после шага (сек). Если None — авто 60–70 FPS.

    Накопитель гарантирует, что ни один субпиксель не теряется:
    дробные остатки суммируются и применяются при следующем вызове.
    """
    global _remainder_x, _remainder_y

    # Лёгкий биомеханический шум (дрожание руки)
    dx += random.uniform(-0.12, 0.12)
    dy += random.uniform(-0.12, 0.12)

    # Ограничение скорости одного шага
    dx = max(min(dx, 4.0), -4.0)
    dy = max(min(dy, 4.0), -4.0)

    # Накапливаем дробную часть вместо потери при round()
    _remainder_x += dx
    _remainder_y += dy

    mx = int(_remainder_x)
    my = int(_remainder_y)

    _remainder_x -= mx
    _remainder_y -= my

    if mx != 0 or my != 0:
        _send_relative(mx, my)

    # Задержка
    if delay is not None:
        time.sleep(delay)
    else:
        time.sleep(1 / random.uniform(62, 68))
