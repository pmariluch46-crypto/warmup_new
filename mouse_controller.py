import time
import random
import ctypes
from core.mouse import (
    move_bezier_to,
    move_s_curve_to,
    move_linear_to,
    micro_corrections
)


class MouseController:
    def __init__(self, mode: str = "normal"):
        self.mode = mode

    def move_to(self, x: int, y: int):
        move_linear_to(x, y, self.mode)

    def click(self, x: int, y: int):
        move_bezier_to(x, y, self.mode)
        micro_corrections(x, y)
        time.sleep(random.uniform(0.03, 0.07))
        self.left_click()

    def super_click(self, x: int, y: int):
        import pyautogui
        start_x, start_y = pyautogui.position()
        distance = ((x - start_x)**2 + (y - start_y)**2) ** 0.5

        if distance < 120:
            move_s_curve_to(x, y, self.mode, steps_override=35, offset_scale=0.25)
        elif distance < 350:
            move_s_curve_to(x, y, self.mode, steps_override=55, offset_scale=0.45)
        else:
            mid_x = int(x + random.uniform(-20, 20))
            mid_y = int(y + random.uniform(-20, 20))
            move_s_curve_to(mid_x, mid_y, self.mode, steps_override=60, offset_scale=0.35)
            time.sleep(random.uniform(0.01, 0.03))
            move_s_curve_to(x, y, self.mode, steps_override=40, offset_scale=0.25)

        micro_corrections(x, y)
        time.sleep(random.uniform(0.01, 0.03))
        self.left_click()

    def scroll(self, amount: int):
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
                ctypes.windll.user32.mouse_event(
                    MOUSEEVENTF_WHEEL, 0, 0,
                    ctypes.c_ulong(delta).value, 0
                )
                time.sleep(random.uniform(0.008, 0.018))

            if remaining > 0:
                time.sleep(random.uniform(0.05, 0.15))

    def left_click(self):
        import pyautogui
        pyautogui.click()