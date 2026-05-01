import time
import random
import ctypes
from core.mouse import (
    move_bezier_to,
    move_s_curve_to,
    micro_corrections
)


class MouseController:
    def __init__(self, mode="normal"):
        self.mode = mode

    def _human_jitter(self, x, y):
        """Микродвижения мыши перед кликом."""
        import pyautogui
        for _ in range(random.randint(1, 3)):
            jx = x + random.randint(-2, 2)
            jy = y + random.randint(-2, 2)
            move_s_curve_to(jx, jy, self.mode, steps_override=12, offset_scale=0.15)
            time.sleep(random.uniform(0.02, 0.06))

    def move_to(self, x, y):
        """Человеческое движение мыши."""
        # 10% шанс промаха
        if random.random() < 0.10:
            miss_x = x + random.randint(-8, 8)
            miss_y = y + random.randint(-8, 8)
            move_s_curve_to(miss_x, miss_y, self.mode, steps_override=45, offset_scale=0.35)
            time.sleep(random.uniform(0.05, 0.12))

        move_s_curve_to(x, y, self.mode, steps_override=55, offset_scale=0.30)

    def click(self, x, y):
        self.move_to(x, y)

        # микро‑дрожание
        self._human_jitter(x, y)

        # микро‑коррекция
        micro_corrections(x, y)

        time.sleep(random.uniform(0.05, 0.12))
        self.left_click()

    def super_click(self, x, y):
        self.move_to(x, y)

        # небольшая пауза как у человека
        time.sleep(random.uniform(0.03, 0.08))

        self._human_jitter(x, y)
        micro_corrections(x, y)

        time.sleep(random.uniform(0.02, 0.05))
        self.left_click()

    def scroll(self, amount):
        """Человеческий скролл с инерцией."""
        MOUSEEVENTF_WHEEL = 0x0800
        WHEEL_DELTA = 120

        direction = 1 if amount > 0 else -1
        total_ticks = abs(amount) // WHEEL_DELTA
        if total_ticks == 0:
            total_ticks = 1

        remaining = total_ticks
        while remaining > 0:
            burst = random.randint(1, min(4, remaining))
            remaining -= burst

            for _ in range(burst):
                delta = WHEEL_DELTA * direction

                # иногда человек чуть скроллит в обратную сторону
                if random.random() < 0.05:
                    delta = -delta

                ctypes.windll.user32.mouse_event(
                    MOUSEEVENTF_WHEEL, 0, 0,
                    ctypes.c_ulong(delta).value, 0
                )

                # естественная задержка
                time.sleep(random.uniform(0.01, 0.04))

            # пауза между “рывками”
            time.sleep(random.uniform(0.15, 0.35))

    def left_click(self):
        import pyautogui
        pyautogui.click()
