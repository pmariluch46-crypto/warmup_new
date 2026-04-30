from core.mouse_controller import MouseController
import time

mc = MouseController()

print("Тест движения...")
mc.move_to(600, 300)
time.sleep(1)

print("Тест супер-клика...")
mc.super_click(500, 500)
time.sleep(1)

print("Тест обычного клика...")
mc.click(400, 400)

print("Готово.")
