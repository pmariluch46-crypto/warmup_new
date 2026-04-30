from core.mouse_controller import MouseController
import time

mc = MouseController()
print("Тест: движение...")
mc.move_to(600, 300)
time.sleep(1)
print("Тест: супер-клик...")
mc.super_click(500, 500)
time.sleep(1)
print("Тест: скролл...")
mc.scroll(1200)
print("Готово.")