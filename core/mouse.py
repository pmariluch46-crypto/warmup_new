import random
import time
import math
from core.mouse_engine_relative import apply_relative, reset_remainder


# ---------------------------------------------------------
#  Адаптивный множитель скорости
# ---------------------------------------------------------
def get_speed_factor(distance: float) -> float:
    if distance > 800:
        return 0.55
    if distance > 500:
        return 0.75
    if distance > 300:
        return 1.0
    if distance > 150:
        return 1.25
    return 1.45


# ---------------------------------------------------------
#  Адаптивная биомеханика (зависит от расстояния)
# ---------------------------------------------------------
def biomech_offset(distance: float) -> float:
    if distance > 600:
        return random.uniform(0.8, 1.2)
    if distance > 300:
        return random.uniform(1.0, 1.4)
    if distance > 150:
        return random.uniform(1.2, 1.6)
    return random.uniform(1.4, 2.0)


# ---------------------------------------------------------
#  Динамическая задержка шага (ускорение → пик → торможение)
#
#  t            — прогресс 0.0..1.0
#  speed_factor — множитель скорости движения
#
#  Логика: sin(t*π) даёт 0 на краях и 1 в середине.
#  FPS растёт от ~60 до ~130 в середине пути и падает обратно.
#  Это имитирует естественное ускорение/торможение руки.
# ---------------------------------------------------------
def _step_delay(t: float, speed_factor: float) -> float:
    velocity = math.sin(t * math.pi)              # 0 → 1 → 0
    fps = 60 + 70 * velocity                      # 60 → 130 → 60 FPS
    fps *= speed_factor                           # быстрее/медленнее
    fps = max(fps, 40)                            # не ниже 40 FPS
    # Добавляем лёгкий jitter ±5% для нерегулярности
    fps *= random.uniform(0.95, 1.05)
    return 1.0 / fps


# ---------------------------------------------------------
#  ПРЯМОЕ ДВИЖЕНИЕ (ease-in-out + динамический FPS)
# ---------------------------------------------------------
def move_linear_to(x: int, y: int, profile: str = "normal"):
    import pyautogui
    start_x, start_y = pyautogui.position()

    distance = math.dist((start_x, start_y), (x, y))
    if distance < 1:
        return

    speed = get_speed_factor(distance)
    steps = int(random.randint(110, 150) * speed)
    steps = max(steps, 10)

    prev_x, prev_y = float(start_x), float(start_y)
    reset_remainder()

    for i in range(1, steps + 1):
        t = i / steps
        ease = (1 - math.cos(t * math.pi)) / 2

        nx = start_x + (x - start_x) * ease
        ny = start_y + (y - start_y) * ease

        dx = nx - prev_x
        dy = ny - prev_y

        apply_relative(dx, dy, delay=_step_delay(t, speed))

        prev_x = nx
        prev_y = ny


# ---------------------------------------------------------
#  Bezier (адаптивная скорость + биомеханика + динамический FPS)
# ---------------------------------------------------------
def move_bezier_to(x: int, y: int, profile: str = "normal"):
    import pyautogui
    start_x, start_y = pyautogui.position()

    distance = math.dist((start_x, start_y), (x, y))
    if distance < 1:
        return

    speed = get_speed_factor(distance)
    bio = biomech_offset(distance)

    steps = int(random.randint(140, 200) * speed)
    steps = max(steps, 10)

    c1x = start_x + (x - start_x) * 0.3 + random.uniform(-60, 60) * bio
    c1y = start_y + (y - start_y) * 0.3 + random.uniform(-60, 60) * bio
    c2x = start_x + (x - start_x) * 0.7 + random.uniform(-60, 60) * bio
    c2y = start_y + (y - start_y) * 0.7 + random.uniform(-60, 60) * bio

    prev_x, prev_y = float(start_x), float(start_y)
    reset_remainder()

    for i in range(1, steps + 1):
        t = i / steps

        bx = (
            (1 - t)**3 * start_x +
            3 * (1 - t)**2 * t * c1x +
            3 * (1 - t) * t**2 * c2x +
            t**3 * x
        )
        by = (
            (1 - t)**3 * start_y +
            3 * (1 - t)**2 * t * c1y +
            3 * (1 - t) * t**2 * c2y +
            t**3 * y
        )

        dx = bx - prev_x
        dy = by - prev_y

        apply_relative(dx, dy, delay=_step_delay(t, speed))

        prev_x = bx
        prev_y = by


# ---------------------------------------------------------
#  S‑кривая (исправленная: смещение перпендикулярно пути)
#
#  Раньше смещение шло случайно по X или Y — это давало зигзаг.
#  Теперь смещение строго перпендикулярно вектору движения,
#  как настоящий дугообразный жест руки.
# ---------------------------------------------------------
def move_s_curve_to(
    x: int,
    y: int,
    profile: str = "normal",
    steps_override: int = None,
    offset_scale: float = 1.0
):
    import pyautogui
    start_x, start_y = pyautogui.position()

    distance = math.dist((start_x, start_y), (x, y))
    if distance < 1:
        return

    speed = get_speed_factor(distance)
    bio = biomech_offset(distance)

    base_steps = steps_override if steps_override else random.randint(140, 200)
    steps = int(base_steps * speed)
    steps = max(steps, 10)

    # Единичный вектор вдоль пути и перпендикуляр к нему
    vx = (x - start_x) / distance
    vy = (y - start_y) / distance
    perp_x = -vy   # перпендикуляр (поворот на 90°)
    perp_y = vx

    # Амплитуда дуги — зависит от расстояния и scale
    amplitude = random.uniform(10, 25) * offset_scale * bio
    # Случайная сторона изгиба
    if random.random() < 0.5:
        amplitude = -amplitude

    prev_x, prev_y = float(start_x), float(start_y)
    reset_remainder()

    for i in range(1, steps + 1):
        t = i / steps

        # Линейная интерполяция по прямой
        lx = start_x + (x - start_x) * t
        ly = start_y + (y - start_y) * t

        # Перпендикулярное смещение: sin даёт дугу (0 → макс → 0)
        offset = math.sin(t * math.pi) * amplitude * speed
        nx = lx + perp_x * offset
        ny = ly + perp_y * offset

        dx = nx - prev_x
        dy = ny - prev_y

        apply_relative(dx, dy, delay=_step_delay(t, speed))

        prev_x = nx
        prev_y = ny


# ---------------------------------------------------------
#  Микро‑коррекции в конце движения
#  Имитируют финальную подводку руки к цели
# ---------------------------------------------------------
def micro_corrections(x: int, y: int):
    corrections = random.randint(1, 3)
    for _ in range(corrections):
        # Отклонение уменьшается с каждой коррекцией
        spread = random.uniform(2, 5)
        cx = x + random.uniform(-spread, spread)
        cy = y + random.uniform(-spread, spread)
        move_linear_to(int(cx), int(cy))
        time.sleep(random.uniform(0.008, 0.025))

    # Финальная точная подводка прямо в цель
    move_linear_to(x, y)
