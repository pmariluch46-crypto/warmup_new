"""
core/adaptive_scroll.py  --  Адаптивный человекоподобный скролл.

Подключается к browser_bot.py и warm_up_engine.py.
Не требует изменений в остальных файлах.

Использование:
    from core.adaptive_scroll import adaptive_read_page, adaptive_browse_deep

Заменяет:
    _read_page(...)       →  adaptive_read_page(...)
    _browse_deep_page(...)→  adaptive_browse_deep(...)
"""

import time
import math
import random


# ==============================================================================
#  ВНУТРЕННЕЕ СОСТОЯНИЕ СЕССИИ
#  Имитирует накопленную усталость и привыкание за сессию
# ==============================================================================

_session_fatigue = 0.0          # 0.0 = свежий, 1.0 = устал
_session_start   = time.time()


def reset_session_fatigue():
    """Вызывать в начале каждой новой сессии просмотра."""
    global _session_fatigue, _session_start
    _session_fatigue = 0.0
    _session_start   = time.time()


def _update_fatigue(elapsed_minutes: float):
    """Усталость растёт логарифмически — быстро в начале, медленно потом."""
    global _session_fatigue
    _session_fatigue = min(1.0, math.log1p(elapsed_minutes / 15.0) * 0.7)


def _fatigue_factor() -> float:
    """Возвращает множитель скорости: 1.0 = бодрый, 0.65 = уставший."""
    return 1.0 - _session_fatigue * 0.35


# ==============================================================================
#  АДАПТИВНЫЙ РАЗМЕР ЧАНКА
#  Зависит от позиции на странице и «интереса» к контенту
# ==============================================================================

def _chunk_size(progress: float, interest: float, read_speed: float) -> int:
    """
    progress  — 0.0 (начало) → 1.0 (конец страницы)
    interest  — 0.0 (скучно) → 1.0 (очень интересно)
    read_speed — общий множитель скорости из настроек

    Логика:
    - Начало страницы: быстрый скролл (заголовки, шапка)
    - Середина: адаптивно — если интересно, мелкие шаги; если скучно, крупные
    - Конец: замедление (футер, связанные статьи)
    """
    if progress < 0.15:
        # Быстрый просмотр начала
        base = random.randint(350, 600)
    elif progress < 0.80:
        # Основной контент — зависит от интереса
        if interest > 0.6:
            # Интересно — читаем медленно, мелкие шаги
            base = random.randint(120, 280)
        elif interest > 0.3:
            base = random.randint(220, 420)
        else:
            # Скучно — быстро листаем
            base = random.randint(380, 680)
    else:
        # Конец страницы — замедляемся
        base = random.randint(100, 250)

    # Усталость увеличивает чанк (уставший человек листает быстрее, менее внимательно)
    fatigue_boost = int(_session_fatigue * 120)
    base += fatigue_boost

    # read_speed: < 1.0 = медленнее, > 1.0 = быстрее
    base = int(base / max(read_speed, 0.3))

    return max(80, min(base, 750))


# ==============================================================================
#  ПАУЗА МЕЖДУ ЧАНКАМИ
#  Имитирует глаза, читающие строки
# ==============================================================================

def _reading_pause(chunk_px: int, interest: float, read_speed: float) -> float:
    """
    Пауза пропорциональна размеру чанка (больше прокрутили = больше читать)
    и интересу (интереснее = дольше смотрим).

    Усталость удлиняет паузы в начале сессии (человек внимателен),
    но к концу сессии сокращает (уже не читает, просто листает).
    """
    # Базовое время чтения: ~0.8px/ms при нормальном чтении
    base = chunk_px / random.uniform(700, 1100)

    # Интерес замедляет
    interest_mult = 1.0 + interest * 1.2

    # Усталость в начале сессии → внимательнее; в конце → быстрее
    if _session_fatigue < 0.4:
        fatigue_mult = 1.0 + _session_fatigue * 0.5
    else:
        fatigue_mult = max(0.6, 1.2 - _session_fatigue * 0.8)

    pause = base * interest_mult * fatigue_mult / max(read_speed, 0.3)

    # Jitter ±20%
    pause *= random.uniform(0.80, 1.20)

    return max(0.4, min(pause, 8.0))


# ==============================================================================
#  "ЗАЧИТАЛСЯ" — случайная длинная пауза
#  Человек нашёл что-то интересное и остановился
# ==============================================================================

def _maybe_deep_read_pause(interest: float, stop_event) -> bool:
    """
    С вероятностью зависящей от интереса делает длинную паузу (3–12с).
    Возвращает True если пауза была.
    """
    prob = 0.08 + interest * 0.20   # 8–28% шанс
    if random.random() > prob:
        return False

    duration = random.uniform(3.0, 12.0) * (1.0 + interest)
    duration = min(duration, 15.0)

    end_t = time.time() + duration
    while time.time() < end_t:
        if stop_event and stop_event.is_set():
            return True
        time.sleep(min(end_t - time.time(), 0.5))

    return True


# ==============================================================================
#  УМНЫЙ СКРОЛЛ НАЗАД
#  Не случайный, а возврат к «якорю» — месту где было интересно
# ==============================================================================

def _smart_scroll_back(bot, driver, anchor_px: int, current_px: int, stop_event):
    """
    Возвращается к anchor_px (место где был интерес),
    делает паузу, потом листает дальше.
    """
    if current_px <= anchor_px + 100:
        return

    back_dist = current_px - anchor_px
    back_dist = min(back_dist, random.randint(200, 500))

    # Скролл назад — медленнее чем вперёд (человек ищет место)
    steps = random.randint(2, 4)
    for _ in range(steps):
        if stop_event and stop_event.is_set():
            return
        chunk = back_dist // steps
        bot.scroll_page(driver, -chunk)
        time.sleep(random.uniform(0.3, 0.8))

    # Пауза — перечитываем
    time.sleep(random.uniform(2.0, 5.0))

    # Листаем вперёд обратно
    if random.random() < 0.6 and not (stop_event and stop_event.is_set()):
        bot.scroll_page(driver, back_dist + random.randint(50, 150))
        time.sleep(random.uniform(0.5, 1.2))


# ==============================================================================
#  ОСНОВНАЯ ФУНКЦИЯ: ГЛУБОКОЕ ЧТЕНИЕ СТРАНИЦЫ
#  Заменяет _browse_deep_page в warm_up_engine.py
# ==============================================================================

def adaptive_browse_deep(bot, driver, stop_event, read_speed: float = 1.0):
    """
    Полная сессия чтения страницы с адаптивным скроллом.

    Отличия от оригинального _browse_deep_page:
    - Размер чанка зависит от позиции и интереса
    - Паузы адаптируются к контенту
    - "Зачитался" режим (случайная длинная остановка)
    - Умный скролл назад к якорю (а не случайный)
    - Учитывает усталость сессии
    """
    # Обновляем усталость
    elapsed = (time.time() - _session_start) / 60.0
    _update_fatigue(elapsed)

    try:
        page_h     = driver.execute_script(
            "return Math.max(document.body.scrollHeight,"
            " document.documentElement.scrollHeight);")
        viewport_h = driver.execute_script("return window.innerHeight;")
    except Exception:
        page_h, viewport_h = 3000, 900

    max_scroll    = max(page_h - viewport_h, 200)
    target_scroll = int(max_scroll * random.uniform(0.80, 1.00))
    scrolled      = 0

    session_dur = max(15.0, min(35.0, random.uniform(15, 30) * (1.0 / max(read_speed, 0.3))))
    end_t       = time.time() + session_dur

    # Интерес к странице — генерируется один раз для всей страницы
    # (некоторые страницы просто интереснее других)
    page_interest = random.betavariate(2, 3)   # чаще низкий-средний

    # Якорь — позиция где был пик интереса (для умного возврата)
    interest_anchor    = 0
    interest_anchor_px = 0
    went_back          = False

    while (scrolled < target_scroll
           and not (stop_event and stop_event.is_set())
           and time.time() < end_t):

        remaining = end_t - time.time()
        if remaining < 0.5:
            break

        progress = scrolled / max(target_scroll, 1)

        # Локальный интерес — варьируется по ходу страницы
        local_interest = min(1.0, page_interest + random.gauss(0, 0.15))
        local_interest = max(0.0, local_interest)

        # Обновляем якорь если интерес вырос
        if local_interest > interest_anchor:
            interest_anchor    = local_interest
            interest_anchor_px = scrolled

        # Пауза чтения
        chunk = _chunk_size(progress, local_interest, read_speed)
        pause = _reading_pause(chunk, local_interest, read_speed)
        pause = min(pause, remaining * 0.4)

        # Дополнительные действия во время паузы
        roll = random.random()
        if roll < 0.14 and not (stop_event and stop_event.is_set()):
            try:
                from core.warm_up_engine import _hover_links
                _hover_links(driver, 1)
            except Exception:
                pass
            time.sleep(max(0, pause - 0.4))
        elif roll < 0.22 and not (stop_event and stop_event.is_set()):
            try:
                bot.idle_mouse_drift(driver, min(pause * 0.6, 1.5))
            except Exception:
                time.sleep(pause)
        elif roll < 0.27 and not (stop_event and stop_event.is_set()):
            try:
                bot.select_random_text(driver)
            except Exception:
                pass
            time.sleep(max(0, pause - 0.3))
        else:
            time.sleep(pause)

        if stop_event and stop_event.is_set():
            break

        # "Зачитался" — длинная пауза
        _maybe_deep_read_pause(local_interest, stop_event)

        if stop_event and stop_event.is_set():
            break

        # Иногда маленький скролл назад (перечитываем строку)
        if random.random() < 0.07 and scrolled > 100:
            mini_back = random.randint(40, 120)
            bot.scroll_page(driver, -mini_back)
            time.sleep(random.uniform(0.3, 0.9))
            bot.scroll_page(driver, mini_back)
            time.sleep(random.uniform(0.2, 0.5))

        # Основной скролл вперёд
        actual_chunk = min(chunk, target_scroll - scrolled)
        bot.scroll_page(driver, actual_chunk)
        scrolled += actual_chunk
        bot.ln_sleep(random.uniform(0.2, 0.5), 0.15)

    # Умный скролл назад к якорю (30% шанс, только если далеко ушли)
    if (not went_back
            and random.random() < 0.30
            and scrolled > 400
            and not (stop_event and stop_event.is_set())):
        _smart_scroll_back(bot, driver, interest_anchor_px, scrolled, stop_event)


# ==============================================================================
#  ЛЁГКОЕ ЧТЕНИЕ
#  Заменяет _read_page в warm_up_engine.py
#  Используется на страницах результатов Google и при беглом просмотре
# ==============================================================================

def adaptive_read_page(bot, driver, min_secs, max_secs, read_speed, stop_event):
    """
    Адаптивная версия _read_page.
    Более живая: скорость скролла меняется, добавлены паузы разного типа.
    """
    elapsed = (time.time() - _session_start) / 60.0
    _update_fatigue(elapsed)

    budget = math.exp(random.gauss(
        math.log(max(1, (min_secs + max_secs) / 2 * read_speed)), 0.18))
    budget = max(min_secs * read_speed * 0.6,
                 min(max_secs * read_speed * 1.4, budget))
    end_t  = time.time() + budget

    # Интерес к этой конкретной странице
    page_interest = random.betavariate(2, 3)

    scroll_count = 0

    while time.time() < end_t:
        if stop_event and stop_event.is_set():
            return
        remaining = end_t - time.time()
        if remaining <= 0.5:
            break

        roll = random.random()

        if roll < 0.40:
            # Скролл вниз — адаптивный размер
            chunk = int(random.randint(100, 380) / max(read_speed, 0.3))
            # Если уже много листали — иногда крупнее
            if scroll_count > 4:
                chunk = int(chunk * random.uniform(1.0, 1.5))
            bot.scroll_page(driver, min(chunk, 500))
            scroll_count += 1
            # Пауза после скролла
            pause = _reading_pause(chunk, page_interest, read_speed)
            time.sleep(min(pause, remaining * 0.35))

        elif roll < 0.54:
            # Скролл вверх — беглый возврат
            back = random.randint(50, 180)
            bot.scroll_page(driver, -back)
            time.sleep(random.uniform(0.4, 1.2))

        elif roll < 0.65:
            # Дрейф мыши
            try:
                bot.idle_mouse_drift(driver, min(remaining * 0.20, 2.5))
            except Exception:
                time.sleep(min(remaining * 0.15, 1.5))

        elif roll < 0.74:
            # Hover по ссылкам
            try:
                from core.warm_up_engine import _hover_links
                _hover_links(driver, random.randint(1, 3))
            except Exception:
                pass

        elif roll < 0.80:
            # Выделение текста
            try:
                bot.select_random_text(driver)
            except Exception:
                pass

        elif roll < 0.85:
            # Ctrl+F
            try:
                bot.occasional_ctrl_f(driver, chance=1.0)
            except Exception:
                pass

        else:
            # Просто пауза — смотрим в экран
            pause = min(remaining * 0.3, random.uniform(1.5, 6.0))
            # Иногда длинная пауза — отвлёкся
            if random.random() < 0.15:
                pause = min(remaining * 0.4, random.uniform(5.0, 14.0))
            time.sleep(pause)