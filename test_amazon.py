"""
test_amazon.py  --  Тест адаптивного скролла и навигации на Amazon.

Запуск:
    python test_amazon.py

Скрипт откроет Firefox Portable, зайдёт на amazon.com,
прокрутит страницу товара и попробует перейти по внутренним ссылкам.
"""

import time
import random
import sys
import os

# ---------------------------------------------------------------------------
#  НАСТРОЙКИ — поменяй пути под свой Firefox Portable
# ---------------------------------------------------------------------------

FIREFOX_BINARY  = r"O:\FirefoxPortable\App\Firefox64\firefox.exe"
FIREFOX_PROFILE = r"O:\FirefoxPortable\Data\profile"
GECKODRIVER     = r"Q:\warmup_new - Copy\drivers\geckodriver.exe"

# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import browser_bot as bot
from core.adaptive_scroll import adaptive_browse_deep, reset_session_fatigue
from core.warm_up_engine import _hover_links, _accept_cookies

import threading
stop_event = threading.Event()


def test_amazon():
    print("Запускаем Firefox Portable...")
    driver = bot.create_driver(FIREFOX_BINARY, FIREFOX_PROFILE, GECKODRIVER)

    try:
        reset_session_fatigue()

        # Ждём пока Firefox полностью загрузится
        print("Ждём загрузки браузера...")
        time.sleep(4)

        # --- Открываем Amazon ---
        print("Открываем amazon.com...")
        bot.navigate_addressbar(driver, "https://www.amazon.com")
        bot.inject_stealth(driver)
        bot.ln_sleep(3.0, 0.22)
        bot._reset_mouse(driver)

        # Принимаем куки если есть
        _accept_cookies(driver)
        bot.ln_sleep(1.0, 0.20)

        # --- Беглый просмотр главной ---
        print("Просматриваем главную страницу...")
        _hover_links(driver, random.randint(2, 4))
        bot.scroll_page(driver, random.randint(300, 600))
        bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)
        bot.scroll_page(driver, random.randint(200, 400))
        bot.ln_sleep(random.uniform(0.8, 1.5), 0.20)

        # --- Ищем товар ---
        print("Ищем товар на Amazon...")
        queries = [
            "wireless headphones",
            "coffee maker",
            "laptop stand",
            "mechanical keyboard",
        ]
        query = random.choice(queries)
        print(f"  Запрос: {query}")
        bot.navigate_addressbar(driver, f"https://www.amazon.com/s?k={query.replace(' ', '+')}")
        bot.inject_stealth(driver)
        bot.ln_sleep(3.5, 0.22)
        bot._reset_mouse(driver)

        # --- Просматриваем результаты поиска ---
        print("Просматриваем результаты поиска...")
        _hover_links(driver, random.randint(2, 3))
        bot.scroll_page(driver, random.randint(400, 700))
        bot.ln_sleep(random.uniform(1.5, 3.0), 0.22)

        # Ещё немного скролла
        bot.scroll_page(driver, random.randint(300, 500))
        bot.ln_sleep(random.uniform(1.0, 2.0), 0.20)

        # --- Кликаем на первый товар ---
        print("Открываем страницу товара...")
        from selenium.webdriver.common.by import By
        try:
            items = driver.find_elements(
                By.CSS_SELECTOR,
                "div[data-component-type='s-search-result'] h2 a"
            )
            visible = [i for i in items if i.is_displayed()]
            if visible:
                chosen = random.choice(visible[:5])
                bot.mouse_move_to_element(driver, chosen)
                bot.ln_sleep(random.uniform(0.3, 0.7), 0.20)
                bot.human_click(driver, chosen)
                bot.inject_stealth(driver)
                bot.ln_sleep(3.5, 0.22)
                bot._reset_mouse(driver)
                print("  Товар открыт.")
            else:
                print("  Товары не найдены, пропускаем клик.")
        except Exception as e:
            print(f"  Ошибка клика по товару: {e}")

        # --- Адаптивный скролл страницы товара ---
        print("Адаптивный скролл страницы товара (15-30 сек)...")
        adaptive_browse_deep(bot, driver, stop_event, read_speed=0.8)
        print("  Скролл завершён.")

        # --- Hover по похожим товарам ---
        print("Осматриваем похожие товары...")
        _hover_links(driver, random.randint(2, 4))
        bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)

        # --- Скролл назад вверх (как будто вернулись перечитать) ---
        print("Возвращаемся наверх...")
        bot.scroll_page(driver, -random.randint(400, 800))
        bot.ln_sleep(random.uniform(1.5, 3.0), 0.22)

        # --- Финальный дрейф мыши ---
        print("Финальный просмотр...")
        bot.idle_mouse_drift(driver, random.uniform(2.0, 4.0))

        print("\nТест завершён успешно!")
        print("Браузер закроется через 5 секунд...")
        time.sleep(5)

    except Exception as e:
        print(f"\nОшибка во время теста: {e}")
        import traceback
        traceback.print_exc()

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("Готово.")


if __name__ == "__main__":
    test_amazon()