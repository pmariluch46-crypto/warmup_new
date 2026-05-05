"""
core/amazon_engine.py -- Amazon Warm-up session engine.

KEY FIXES in this version:
  - _deep_browse_images: each thumbnail clicked exactly ONCE, tracked by index
  - _visit_deep: strictly top-to-bottom, never jumps back up until add-to-cart phase
  - mouse_move_to_element NOT used during scrolling phases — cursor micro-drifts only
  - Lightbox removed — was causing stuck sessions
  - All scroll is continuous wheel, no scrollIntoView teleports during deep visit
"""

import time
import math
import random
import pyautogui

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

from core import browser_bot as bot

# ==============================================================================
# CONFIG
# ==============================================================================

class AmazonSessionConfig:
    def __init__(self, categories, session_minutes, read_reviews,
                 stop_event, on_progress=None):
        self.categories      = categories
        self.session_minutes = session_minutes
        self.read_reviews    = read_reviews
        self.stop_event      = stop_event
        self.on_progress     = on_progress

VISIT_DEEP   = "deep"
VISIT_MEDIUM = "medium"
VISIT_QUICK  = "quick"

STINT_SHORT = "short"
STINT_LONG  = "long"

# ==============================================================================
# QUERY LOADER
# ==============================================================================

def _load_queries_for_categories(categories):
    from core.amazon_query_manager import load_amazon_queries
    try:
        data = load_amazon_queries()
    except Exception:
        data = {}
    pool = []
    for cat in categories:
        for q in data.get(cat, []):
            pool.append((cat, q))
    random.shuffle(pool)
    return pool

# ==============================================================================
# PAGE DETECTION
# ==============================================================================

def _is_amazon_product_page(driver) -> bool:
    try:
        url = driver.current_url
        return "amazon.com" in url and ("/dp/" in url or "/gp/product/" in url)
    except Exception:
        return False

def _is_amazon_search_page(driver) -> bool:
    try:
        url = driver.current_url
        return "amazon.com" in url and "/s?" in url
    except Exception:
        return False

def _is_on_amazon(driver) -> bool:
    try:
        return "amazon.com" in driver.current_url
    except Exception:
        return False

def _accept_amazon_cookies(driver):
    for sel in ["#sp-cc-accept", "input[name='accept']",
                "button[data-cel-widget='sp-cc-accept']", "#acceptCookies"]:
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            bot.human_click(driver, btn)
            bot.ln_sleep(0.8, 0.20)
            return
        except Exception:
            continue

# ==============================================================================
# SCROLL HELPERS
# ==============================================================================

def _scroll_chunk(driver, pixels):
    """
    Scroll pixels with variable speed and cursor micro-drift.
    Never teleports — pure wheel scroll with natural pauses.
    """
    if pixels == 0:
        return

    direction = 1 if pixels > 0 else -1
    remaining = abs(pixels)

    try:
        vw = driver.execute_script("return window.innerWidth;")
        vh = driver.execute_script("return window.innerHeight;")
    except Exception:
        vw, vh = 1200, 800

    ox, oy = bot._screen_origin(driver)

    while remaining > 0:
        upper = max(41, min(remaining, random.choice([80, 120, 200, 280])))
        sub = random.randint(40, upper)
        remaining -= sub

        bot.scroll_page(driver, direction * sub)

        # Cursor micro-drift — never stationary during scroll
        drift_x = random.randint(-18, 18)
        drift_y = random.randint(-12, 12)
        new_vx = max(60, min(vw - 30, bot._mx + drift_x))
        new_vy = max(80, min(vh - 60, bot._my + drift_y))
        sx = max(5, min(pyautogui.size()[0] - 5, ox + new_vx))
        sy = max(5, min(pyautogui.size()[1] - 5, oy + new_vy))
        pyautogui.moveTo(sx, sy, duration=random.uniform(0.03, 0.09))
        bot._mx = new_vx
        bot._my = new_vy

        # Variable pause — mix of fast and slow
        roll = random.random()
        if roll < 0.12:
            time.sleep(random.uniform(0.8, 2.0))   # reading pause
        elif roll < 0.30:
            time.sleep(random.uniform(0.25, 0.65))  # medium pause
        else:
            time.sleep(random.uniform(0.05, 0.18))  # quick continues


def _scroll_down_to_element(driver, element, stop_event, margin=120):
    """
    Scroll DOWN only until element is visible in viewport.
    Never jumps — pure wheel scroll. Never scrolls UP.
    Used during the top-to-bottom deep visit pass.
    """
    for _ in range(50):
        if stop_event.is_set():
            return
        try:
            rect = driver.execute_script("""
                var r = arguments[0].getBoundingClientRect();
                return {top: r.top, bottom: r.bottom, vh: window.innerHeight};
            """, element)
            top    = rect['top']
            bottom = rect['bottom']
            vh     = rect['vh']

            # Visible enough — stop
            if top >= margin and bottom <= vh - 40:
                return
            # Need to scroll down more
            if bottom > vh - 40:
                gap = bottom - (vh - 40)
                _scroll_chunk(driver, max(60, int(gap * 0.65)))
                time.sleep(random.uniform(0.15, 0.35))
            else:
                # Element is above viewport — shouldn't happen in top-to-bottom
                # but if it does, just return rather than scroll up
                return
        except Exception:
            break


def _get_element_y(driver, element) -> int:
    try:
        return int(driver.execute_script(
            "return arguments[0].getBoundingClientRect().top + window.scrollY;",
            element))
    except Exception:
        return -1


def _current_scroll_y(driver) -> int:
    try:
        return int(driver.execute_script("return window.scrollY;"))
    except Exception:
        return 0


def _get_element_viewport_top(driver, element) -> float:
    """Return element's top position relative to viewport."""
    try:
        return driver.execute_script(
            "return arguments[0].getBoundingClientRect().top;", element)
    except Exception:
        return -1


def _move_cursor_over_element(driver, element):
    """
    Move cursor to an element WITHOUT calling scrollIntoView.
    Only moves the physical mouse — does not scroll the page.
    Used during deep visit phases where we control scrolling ourselves.
    """
    try:
        info = driver.execute_script("""
            var r = arguments[0].getBoundingClientRect();
            return {
                cx: Math.round(window.screenX +
                    Math.round((window.outerWidth - window.innerWidth) / 2) +
                    r.left + r.width / 2),
                cy: Math.round(window.screenY +
                    (window.outerHeight - window.innerHeight) +
                    r.top + r.height / 2),
                w: r.width, h: r.height,
                inView: (r.top >= 0 && r.bottom <= window.innerHeight)
            };
        """, element)

        if not info['inView']:
            return  # don't move mouse to off-screen elements

        ox = random.gauss(0, max(1, info['w'] * 0.12))
        oy = random.gauss(0, max(1, info['h'] * 0.12))
        tx = int(info['cx'] + ox)
        ty = int(info['cy'] + oy)
        tx, ty = bot._clamp_screen(tx, ty)

        # Convert screen coords back to viewport coords for path building
        try:
            win_x = driver.execute_script("return window.screenX;")
            win_y = driver.execute_script("return window.screenY;")
            chrome_h = driver.execute_script(
                "return window.outerHeight - window.innerHeight;")
            chrome_w = driver.execute_script(
                "return Math.round((window.outerWidth - window.innerWidth) / 2);")
            tvx = tx - win_x - chrome_w
            tvy = ty - win_y - chrome_h
        except Exception:
            tvx = tx - 100
            tvy = ty - 100

        try:
            vw = driver.execute_script("return window.innerWidth;")
            vh = driver.execute_script("return window.innerHeight;")
        except Exception:
            vw, vh = 1200, 800

        tvx = max(10, min(vw - 25, tvx))
        tvy = max(10, min(vh - 10, tvy))

        path = bot._build_path((bot._mx, bot._my), (tvx, tvy),
                               overshoot=random.random() < 0.04)
        bot._move_path(driver, path)
        bot._mx = tvx
        bot._my = tvy
    except Exception:
        pass


# ==============================================================================
# CART MANAGEMENT
# ==============================================================================

def _get_cart_count(driver) -> int:
    try:
        el = driver.find_element(
            By.CSS_SELECTOR,
            "#nav-cart-count, span[data-csa-c-content-id='nav-cart-count']")
        text = el.text.strip()
        return int(text) if text.isdigit() else 0
    except Exception:
        return 0


def _open_cart(driver):
    try:
        cart_link = driver.find_element(By.CSS_SELECTOR, "#nav-cart")
        bot.human_click(driver, cart_link)
        bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
        bot.inject_stealth(driver)
    except Exception:
        try:
            driver.get("https://www.amazon.com/gp/cart/view.html")
            bot.ln_sleep(random.uniform(2.0, 3.0), 0.22)
            bot.inject_stealth(driver)
        except Exception:
            pass


def _delete_first_cart_item(driver):
    try:
        _open_cart(driver)
        bot.ln_sleep(random.uniform(0.8, 1.5), 0.20)
        delete_selectors = [
            "input[value='Delete']",
            "span[data-action='delete'] input",
            "a[data-action='delete']",
            "[data-feature-id='delete'] input",
            "input[data-action='delete']",
            ".sc-action-delete input",
            "span.a-declarative[data-action='delete']",
        ]
        for sel in delete_selectors:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            visible = [b for b in btns if b.is_displayed()]
            if visible:
                bot.mouse_move_to_element(driver, visible[0])
                bot.ln_sleep(random.uniform(0.4, 0.9), 0.20)
                bot.human_click(driver, visible[0])
                bot.ln_sleep(random.uniform(1.5, 2.5), 0.22)
                return
    except Exception:
        pass


def _ensure_cart_has_room(driver):
    try:
        count = _get_cart_count(driver)
        while count >= 4:
            _delete_first_cart_item(driver)
            bot.ln_sleep(random.uniform(0.8, 1.5), 0.20)
            count = _get_cart_count(driver)
    except Exception:
        pass


def _add_to_cart(driver) -> bool:
    try:
        _ensure_cart_has_room(driver)
        add_selectors = [
            "#add-to-cart-button",
            "input#add-to-cart-button",
            "input[name='submit.add-to-cart']",
            "#buybox #add-to-cart-button",
            "span#submit\\.add-to-cart input",
        ]
        for sel in add_selectors:
            try:
                btn = WebDriverWait(driver, 4).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                if not btn.is_displayed():
                    continue
                bot.mouse_move_to_element(driver, btn)
                bot.ln_sleep(random.uniform(0.5, 1.2), 0.22)
                bot.human_click(driver, btn)
                bot.ln_sleep(random.uniform(1.8, 3.0), 0.22)
                for close_sel in [
                    "#attach-sidesheet-checkout-button",
                    "button[data-action='a-popover-close']",
                    "#hlb-ptc-btn-native",
                    ".a-popover-closebutton",
                    "button.a-button-close",
                ]:
                    try:
                        close = WebDriverWait(driver, 2).until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR, close_sel)))
                        bot.human_click(driver, close)
                        bot.ln_sleep(0.8, 0.18)
                        break
                    except Exception:
                        pass
                return True
            except Exception:
                continue
        return False
    except Exception:
        return False


# ==============================================================================
# DEEP VISIT — PHASE HELPERS
# Each phase receives the page and scrolls FURTHER DOWN from where it was.
# Nothing ever scrolls back up until the final add-to-cart phase.
# ==============================================================================

def _phase_title_and_images(driver, stop_event):
    """
    Phase 1+2: We're at the top of the page.
    Glance at title/price, then click each thumbnail image ONCE.
    No lightbox. No scrollIntoView. Cursor moves to each visible thumb only.
    """
    bot.ln_sleep(random.uniform(1.2, 2.5), 0.22)

    # Glance at title and price — cursor moves but page doesn't scroll
    for sel in ["#productTitle", "#corePriceDisplay_desktop_feature_div",
                "#averageCustomerReviews"]:
        if stop_event.is_set():
            return
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.is_displayed():
                _move_cursor_over_element(driver, el)
                bot.ln_sleep(random.uniform(0.8, 2.0), 0.22)
        except Exception:
            pass

    if stop_event.is_set():
        return

    # Click image thumbnails — each one exactly ONCE, in order, no revisits
    try:
        thumbs = driver.find_elements(
            By.CSS_SELECTOR,
            "#altImages li.item img, #imageBlock_feature_div li img"
        )
        # Build a deduplicated ordered list by src to prevent revisits
        seen_srcs = set()
        unique_thumbs = []
        for t in thumbs[:10]:
            try:
                src = t.get_attribute("src") or ""
                if src and src not in seen_srcs and t.is_displayed():
                    seen_srcs.add(src)
                    unique_thumbs.append(t)
            except Exception:
                pass

        for thumb in unique_thumbs:
            if stop_event.is_set():
                return
            # Only interact if thumb is currently visible in viewport
            try:
                top = driver.execute_script(
                    "return arguments[0].getBoundingClientRect().top;", thumb)
                vh = driver.execute_script("return window.innerHeight;")
                if top < 0 or top > vh:
                    continue  # skip if not visible — do NOT scroll to it
            except Exception:
                continue

            _move_cursor_over_element(driver, thumb)
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)

            # Click via screen coords (not human_click — avoids scrollIntoView)
            try:
                sx, sy = bot._element_screen_point(driver, thumb)
                sx, sy = bot._clamp_screen(sx, sy)
                bot._si_click(sx, sy)
                bot.ln_sleep(random.uniform(1.0, 2.5), 0.25)
            except Exception:
                pass

    except Exception:
        pass

    bot.ln_sleep(random.uniform(0.5, 1.0), 0.20)


def _phase_feature_bullets(driver, stop_event):
    """
    Phase 3: Scroll down to feature bullets section and read each one.
    Scrolls DOWN continuously — does not jump.
    """
    # Scroll down until bullets section appears
    try:
        bullets_el = driver.find_element(By.CSS_SELECTOR, "#feature-bullets")
        _scroll_down_to_element(driver, bullets_el, stop_event)
    except Exception:
        _scroll_chunk(driver, random.randint(250, 500))

    if stop_event.is_set():
        return

    bot.ln_sleep(random.uniform(0.8, 1.5), 0.22)

    try:
        bullets = driver.find_elements(
            By.CSS_SELECTOR, "#feature-bullets li span.a-list-item")
        visible = [b for b in bullets[:12]
                   if b.is_displayed() and b.text.strip()]

        for bullet in visible:
            if stop_event.is_set():
                return
            _move_cursor_over_element(driver, bullet)
            read_t = len(bullet.text) / random.uniform(180, 300)
            read_t = max(0.6, min(3.5, read_t))
            bot.ln_sleep(read_t, 0.22)
            # Occasionally scroll a tiny bit between bullets
            if random.random() < 0.35:
                _scroll_chunk(driver, random.randint(50, 130))
                bot.ln_sleep(random.uniform(0.2, 0.5), 0.18)
    except Exception:
        pass


def _phase_description_and_specs(driver, stop_event):
    """
    Phase 4: Scroll down to Description and Product Information.
    Spend 20-45s at each section reading. No jumps — continuous downward scroll.
    """
    sections = [
        ("#productDescription",                    "Description"),
        ("#aplus",                                 "Description"),
        ("#productDetails_techSpec_section_1",     "Product information"),
        ("#productDetails_detailBullets_sections1","Product information"),
        ("#detailBullets_feature_div",             "Product information"),
    ]

    for sel, label in sections:
        if stop_event.is_set():
            return
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if not el.is_displayed():
                continue

            # Check if it's below current scroll position — skip if above us
            el_y = _get_element_y(driver, el)
            current_y = _current_scroll_y(driver)
            if el_y < current_y - 100:
                continue  # already passed this section, don't scroll back up

            # Scroll down to it
            _scroll_down_to_element(driver, el, stop_event)
            if stop_event.is_set():
                return

            bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)

            # Read text items by moving cursor over them
            texts = el.find_elements(By.CSS_SELECTOR, "p, li, span, td")
            visible_texts = [t for t in texts[:15]
                             if t.is_displayed() and len(t.text.strip()) > 10]

            section_end = time.time() + random.uniform(20, 45)
            text_idx = 0
            while time.time() < section_end and not stop_event.is_set():
                if visible_texts and text_idx < len(visible_texts):
                    try:
                        _move_cursor_over_element(driver, visible_texts[text_idx])
                        read_t = min(
                            section_end - time.time(),
                            len(visible_texts[text_idx].text) / random.uniform(150, 250)
                        )
                        bot.ln_sleep(max(0.4, read_t), 0.22)
                        text_idx += 1
                        # Scroll down a little between text items
                        if random.random() < 0.40:
                            _scroll_chunk(driver, random.randint(40, 120))
                            bot.ln_sleep(random.uniform(0.2, 0.6), 0.18)
                    except Exception:
                        text_idx += 1
                else:
                    remaining = section_end - time.time()
                    if remaining > 0.5:
                        bot.idle_mouse_drift(driver, min(remaining, 2.5))

            # Scroll a bit further down after section
            _scroll_chunk(driver, random.randint(80, 200))
            bot.ln_sleep(random.uniform(0.4, 1.0), 0.20)

        except Exception:
            continue


def _phase_customers_also_viewed(driver, stop_event):
    """
    Phase 5: Scroll to 'Customers who viewed' carousel.
    Click arrows to browse, hover items, maybe open one in a new tab.
    """
    carousel_selectors = [
        "#similarities_feature_div",
        "#sims-consolidated-1_feature_div",
        "#sims-consolidated-2_feature_div",
        "[cel_widget_id*='ASSOCIATED']",
        "#sp_detail",
        "#purchase-sims-feature",
    ]

    carousel = None
    for sel in carousel_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.is_displayed():
                el_y = _get_element_y(driver, el)
                current_y = _current_scroll_y(driver)
                if el_y >= current_y - 100:  # only if below or near current pos
                    carousel = el
                    break
        except Exception:
            continue

    if not carousel or stop_event.is_set():
        return

    _scroll_down_to_element(driver, carousel, stop_event)
    if stop_event.is_set():
        return

    bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)
    _move_cursor_over_element(driver, carousel)
    bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)

    # Click carousel arrows
    arrow_clicks = random.randint(2, 4)
    for _ in range(arrow_clicks):
        if stop_event.is_set():
            return
        for arrow_sel in [
            ".a-carousel-goto-nextpage",
            "button.a-carousel-goto-nextpage",
            "[aria-label='Next page']",
            ".a-carousel-right",
        ]:
            try:
                arrows = driver.find_elements(By.CSS_SELECTOR, arrow_sel)
                visible_arrows = [a for a in arrows if a.is_displayed()]
                if visible_arrows:
                    _move_cursor_over_element(driver, visible_arrows[0])
                    bot.ln_sleep(random.uniform(0.3, 0.7), 0.18)
                    sx, sy = bot._element_screen_point(driver, visible_arrows[0])
                    sx, sy = bot._clamp_screen(sx, sy)
                    bot._si_click(sx, sy)
                    bot.ln_sleep(random.uniform(0.8, 1.6), 0.22)
                    break
            except Exception:
                continue

    # Hover 2-3 product thumbnails
    try:
        carousel_imgs = carousel.find_elements(
            By.CSS_SELECTOR, "img[src], a[href*='/dp/'] img")
        visible_imgs = [i for i in carousel_imgs[:8] if i.is_displayed()]
        hover_count = random.randint(1, max(1, min(3, len(visible_imgs))))
        for img in random.sample(visible_imgs, hover_count):
            if stop_event.is_set():
                return
            _move_cursor_over_element(driver, img)
            bot.ln_sleep(random.uniform(0.5, 1.4), 0.20)
    except Exception:
        pass

    # 35% chance: Ctrl+Click one item into a new tab for a quick browse
    if random.random() < 0.35 and not stop_event.is_set():
        original_tab = driver.current_window_handle
        original_handles = set(driver.window_handles)
        try:
            links = carousel.find_elements(By.CSS_SELECTOR, "a[href*='/dp/']")
            visible_links = [l for l in links[:8] if l.is_displayed()]
            if visible_links:
                chosen = random.choice(visible_links)
                _move_cursor_over_element(driver, chosen)
                bot.ln_sleep(random.uniform(0.3, 0.7), 0.18)
                pyautogui.keyDown('ctrl')
                time.sleep(random.uniform(0.05, 0.10))
                sx, sy = bot._element_screen_point(driver, chosen)
                sx, sy = bot._clamp_screen(sx, sy)
                bot._si_click(sx, sy)
                time.sleep(random.uniform(0.08, 0.15))
                pyautogui.keyUp('ctrl')
                bot.ln_sleep(random.uniform(1.5, 3.0), 0.22)

                new_handles = set(driver.window_handles) - original_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    driver.switch_to.window(new_tab)
                    bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
                    bot.inject_stealth(driver)
                    bot._reset_mouse(driver)

                    # Quick browse 15-35 seconds
                    browse_end = time.time() + random.uniform(15, 35)
                    _scroll_chunk(driver, random.randint(200, 450))
                    bot.ln_sleep(random.uniform(0.8, 1.5), 0.22)
                    while time.time() < browse_end and not stop_event.is_set():
                        remaining = browse_end - time.time()
                        if remaining < 0.5:
                            break
                        _scroll_chunk(driver,
                            random.choice([1, -1]) * random.randint(80, 250))
                        bot.ln_sleep(
                            random.uniform(0.5, min(remaining, 2.5)), 0.22)

                    driver.close()
                    driver.switch_to.window(original_tab)
                    bot.ln_sleep(random.uniform(0.8, 1.5), 0.22)
                    bot.inject_stealth(driver)
                    bot._reset_mouse(driver)
        except Exception:
            try:
                pyautogui.keyUp('ctrl')
            except Exception:
                pass
            try:
                if original_tab in driver.window_handles:
                    driver.switch_to.window(original_tab)
            except Exception:
                pass


def _phase_product_videos(driver, stop_event):
    """
    Phase 6: Scroll to Product Videos, watch 1-2.
    Only scrolls down — skips if section is above current position.
    """
    video_selectors = [
        "#product-video-section",
        "#dp-desktop-video-carousel",
        "[cel_widget_id*='video']",
        "#videos-block",
        ".vse-lv-card",
    ]

    for sel in video_selectors:
        if stop_event.is_set():
            return
        try:
            section = driver.find_element(By.CSS_SELECTOR, sel)
            if not section.is_displayed():
                continue

            el_y = _get_element_y(driver, section)
            current_y = _current_scroll_y(driver)
            if el_y < current_y - 100:
                continue  # above us — skip

            _scroll_down_to_element(driver, section, stop_event)
            if stop_event.is_set():
                return

            bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)
            _move_cursor_over_element(driver, section)

            video_btns = driver.find_elements(
                By.CSS_SELECTOR,
                ".vse-lv-card, [data-video-url] img, .product-video-thumbnail, "
                "button[class*='video'], [aria-label*='video' i]"
            )
            visible_vids = [v for v in video_btns[:5] if v.is_displayed()]
            if not visible_vids:
                return

            watch_count = random.randint(1, min(2, len(visible_vids)))
            for vid_btn in visible_vids[:watch_count]:
                if stop_event.is_set():
                    return
                _move_cursor_over_element(driver, vid_btn)
                bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)
                sx, sy = bot._element_screen_point(driver, vid_btn)
                sx, sy = bot._clamp_screen(sx, sy)
                bot._si_click(sx, sy)

                watch_s   = random.uniform(15, 45)
                watch_end = time.time() + watch_s
                bot.ln_sleep(random.uniform(1.5, 3.0), 0.22)

                while time.time() < watch_end and not stop_event.is_set():
                    remaining = watch_end - time.time()
                    if remaining < 0.5:
                        break
                    if random.random() < 0.3:
                        bot.idle_mouse_drift(driver, min(remaining * 0.2, 2.0))
                    else:
                        time.sleep(min(remaining, random.uniform(2.0, 5.0)))

                # Close video
                for close_sel in ["button[aria-label='Close']",
                                  ".a-popover-closebutton",
                                  "button.close"]:
                    try:
                        close = driver.find_element(By.CSS_SELECTOR, close_sel)
                        if close.is_displayed():
                            bot.human_click(driver, close)
                            bot.ln_sleep(0.5, 0.18)
                            break
                    except Exception:
                        continue

                bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)
            return
        except Exception:
            continue


def _phase_customer_photos_and_reviews(driver, stop_event):
    """
    Phase 7: Customer photos + read reviews. 40-80s total.
    Scrolls down only. Stops at reviews — never goes past them.
    """
    section_end = time.time() + random.uniform(40, 80)

    # Customer photos
    photo_selectors = [
        "#cr-media-acr-plus-section",
        "[data-hook='cr-media-gallery-by-feature']",
        "#cm_cr_dp_d_review_image_gallery",
        "[data-hook='cr-media-thumb-section']",
    ]
    for sel in photo_selectors:
        if stop_event.is_set() or time.time() >= section_end:
            return
        try:
            section = driver.find_element(By.CSS_SELECTOR, sel)
            if not section.is_displayed():
                continue

            el_y = _get_element_y(driver, section)
            current_y = _current_scroll_y(driver)
            if el_y < current_y - 100:
                continue

            _scroll_down_to_element(driver, section, stop_event)
            if stop_event.is_set():
                return

            bot.ln_sleep(random.uniform(0.8, 1.5), 0.22)
            _move_cursor_over_element(driver, section)
            bot.ln_sleep(random.uniform(0.5, 1.0), 0.20)

            photo_imgs = section.find_elements(By.CSS_SELECTOR, "img[src]")
            visible_photos = [p for p in photo_imgs[:8] if p.is_displayed()]
            if visible_photos:
                click_count = random.randint(1, min(3, len(visible_photos)))
                for photo in random.sample(visible_photos, click_count):
                    if stop_event.is_set() or time.time() >= section_end:
                        break
                    _move_cursor_over_element(driver, photo)
                    bot.ln_sleep(random.uniform(0.4, 0.9), 0.18)
                    sx, sy = bot._element_screen_point(driver, photo)
                    sx, sy = bot._clamp_screen(sx, sy)
                    bot._si_click(sx, sy)
                    bot.ln_sleep(random.uniform(2.0, 4.0), 0.25)
                    # Close lightbox
                    for close_sel in ["button.a-popover-closebutton",
                                      ".cr-lightbox-close",
                                      "button[aria-label='Close']"]:
                        try:
                            close = WebDriverWait(driver, 2).until(
                                EC.element_to_be_clickable(
                                    (By.CSS_SELECTOR, close_sel)))
                            bot.human_click(driver, close)
                            bot.ln_sleep(0.5, 0.18)
                            break
                        except Exception:
                            pass
            break
        except Exception:
            continue

    # Read reviews
    if stop_event.is_set() or time.time() >= section_end:
        return

    try:
        reviews = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-hook='review'] [data-hook='review-body'] span, "
            ".review-text-content span"
        )
        visible_reviews = [r for r in reviews[:10]
                           if r.is_displayed() and len(r.text.strip()) > 30]

        read_count = random.randint(2, max(2, min(4, len(visible_reviews))))
        for review in visible_reviews[:read_count]:
            if stop_event.is_set() or time.time() >= section_end:
                break

            el_y = _get_element_y(driver, review)
            current_y = _current_scroll_y(driver)
            if el_y < current_y - 100:
                continue  # already passed

            _scroll_down_to_element(driver, review, stop_event)
            if stop_event.is_set():
                break

            _move_cursor_over_element(driver, review)
            read_t = min(
                section_end - time.time(),
                len(review.text) / random.uniform(150, 220) + random.uniform(1.5, 3.0)
            )
            bot.ln_sleep(max(1.5, read_t), 0.20)
            _scroll_chunk(driver, random.randint(60, 180))
            bot.ln_sleep(random.uniform(0.3, 0.8), 0.18)
    except Exception:
        pass

    # Fill remaining time naturally
    while time.time() < section_end and not stop_event.is_set():
        remaining = section_end - time.time()
        if remaining < 0.5:
            break
        if random.random() < 0.4:
            _scroll_chunk(driver, random.randint(60, 180))
        bot.ln_sleep(random.uniform(0.5, min(remaining, 2.0)), 0.22)


def _phase_scroll_to_top_and_add_cart(driver, stop_event):
    """
    Phase 8: Scroll back to top naturally, check price, hesitate, add to cart.
    This is the ONLY phase that scrolls upward.
    """
    if stop_event.is_set():
        return

    current_y = _current_scroll_y(driver)
    if current_y > 200:
        remaining_up = current_y
        while remaining_up > 80 and not stop_event.is_set():
            chunk = random.randint(150, 420)
            chunk = min(chunk, remaining_up)
            _scroll_chunk(driver, -chunk)
            remaining_up -= chunk
            if random.random() < 0.20:
                bot.ln_sleep(random.uniform(0.4, 1.2), 0.22)
            else:
                bot.ln_sleep(random.uniform(0.08, 0.30), 0.18)

    if stop_event.is_set():
        return

    bot.ln_sleep(random.uniform(1.5, 3.0), 0.25)

    # Check price again
    for price_sel in ["#priceblock_ourprice", "#priceblock_dealprice",
                      ".a-price .a-offscreen", "#corePrice_feature_div",
                      "#corePriceDisplay_desktop_feature_div"]:
        try:
            price_el = driver.find_element(By.CSS_SELECTOR, price_sel)
            if price_el.is_displayed():
                _move_cursor_over_element(driver, price_el)
                bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)
                break
        except Exception:
            continue

    if stop_event.is_set():
        return

    # Hover Add to Cart with hesitation before clicking
    for atc_sel in ["#add-to-cart-button", "input#add-to-cart-button",
                    "input[name='submit.add-to-cart']",
                    "#buybox #add-to-cart-button"]:
        try:
            atc_btn = driver.find_element(By.CSS_SELECTOR, atc_sel)
            if atc_btn.is_displayed():
                bot.mouse_move_to_element(driver, atc_btn)
                bot.ln_sleep(random.uniform(2.0, 4.5), 0.25)
                bot.hover_jitter(driver, random.uniform(0.8, 2.0))
                break
        except Exception:
            continue

    if stop_event.is_set():
        return

    _add_to_cart(driver)
    bot.ln_sleep(random.uniform(2.0, 4.0), 0.25)


# ==============================================================================
# TAB VISIT HANDLERS
# ==============================================================================

def _visit_deep(driver, cfg: AmazonSessionConfig):
    """
    DEEP visit: 3-7 minutes. Strictly top-to-bottom.

    Phase 1+2 : Top — title/price glance + click each image thumbnail ONCE
    Phase 3   : Scroll down → feature bullets (read each)
    Phase 4   : Scroll down → Description + Product Information (20-45s each)
    Phase 5   : Scroll down → Customers also viewed carousel (arrows + hover)
    Phase 6   : Scroll down → Product Videos (watch 1-2)
    Phase 7   : Scroll down → Customer photos + reviews (40-80s)
    Phase 8   : Scroll back UP → check price → hesitate → Add to Cart

    RULES:
    - Never scrolls up between phases 1-7
    - mouse_move_to_element (which calls scrollIntoView) is NEVER called
      during phases 1-7 — only _move_cursor_over_element is used
    - Each section is only visited if it's below current scroll position
    """
    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)

    if cfg.stop_event.is_set():
        return

    bot.ln_sleep(random.uniform(0.5, 1.0), 0.18)

    # Phase 1+2: title glance + images
    _phase_title_and_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # Phase 3: feature bullets
    _phase_feature_bullets(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # Phase 4: description + specs
    _phase_description_and_specs(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # Phase 5: customers also viewed carousel
    _phase_customers_also_viewed(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # Phase 6: product videos
    _phase_product_videos(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # Phase 7: customer photos + reviews
    _phase_customer_photos_and_reviews(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # Phase 8: scroll up + add to cart
    _phase_scroll_to_top_and_add_cart(driver, cfg.stop_event)


def _visit_medium(driver, cfg: AmazonSessionConfig):
    """
    Medium visit: 30 seconds - 2 minutes.
    Glance at images + some scrolling. No reviews, no deep reading.
    """
    stay_s = random.uniform(30, 120)
    end_t  = time.time() + stay_s

    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)

    if cfg.stop_event.is_set():
        return

    _scroll_chunk(driver, random.randint(150, 400))
    bot.ln_sleep(random.uniform(0.6, 1.5), 0.22)

    # Browse 1-3 images without revisiting
    try:
        thumbs = driver.find_elements(
            By.CSS_SELECTOR,
            "#altImages li.item img, #imageBlock_feature_div li img")
        seen_srcs = set()
        unique_thumbs = []
        for t in thumbs[:6]:
            try:
                src = t.get_attribute("src") or ""
                if src and src not in seen_srcs and t.is_displayed():
                    seen_srcs.add(src)
                    unique_thumbs.append(t)
            except Exception:
                pass

        count = random.randint(1, max(1, min(3, len(unique_thumbs))))
        for thumb in unique_thumbs[:count]:
            if cfg.stop_event.is_set() or time.time() >= end_t:
                break
            bot.mouse_move_to_element(driver, thumb)
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)
            bot.human_click(driver, thumb)
            bot.ln_sleep(random.uniform(0.8, 2.0), 0.22)
    except Exception:
        pass

    if cfg.stop_event.is_set():
        return

    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.4:
            break
        roll = random.random()
        if roll < 0.45:
            _scroll_chunk(driver,
                random.choice([1, -1]) * random.randint(100, 320))
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)
        elif roll < 0.65:
            bot.idle_mouse_drift(driver, min(remaining * 0.25, 2.0))
        else:
            time.sleep(min(remaining, random.uniform(1.0, 3.0)))


def _visit_quick(driver, cfg: AmazonSessionConfig):
    """Quick visit: 20-40 seconds. Quick glance, minimal interaction."""
    stay_s = random.uniform(20, 40)
    end_t  = time.time() + stay_s

    bot.inject_stealth(driver)

    if cfg.stop_event.is_set():
        return

    _scroll_chunk(driver, random.randint(100, 300))
    bot.ln_sleep(random.uniform(0.5, 1.2), 0.22)

    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.3:
            break
        if random.random() < 0.5:
            _scroll_chunk(driver, random.randint(80, 220))
        bot.ln_sleep(random.uniform(0.5, 1.5), 0.22)


# ==============================================================================
# TAB VISIT TYPE ASSIGNMENT
# ==============================================================================

def _assign_visit_types(tab_count: int) -> list:
    """20% deep, 50% medium, 30% quick. Guarantees at least 1 deep if >= 3 tabs."""
    types = []
    for _ in range(tab_count):
        r = random.random()
        if r < 0.20:
            types.append(VISIT_DEEP)
        elif r < 0.70:
            types.append(VISIT_MEDIUM)
        else:
            types.append(VISIT_QUICK)
    if tab_count >= 3 and VISIT_DEEP not in types:
        types[random.randint(0, tab_count - 1)] = VISIT_DEEP
    return types


# ==============================================================================
# CTRL+CLICK HELPER
# ==============================================================================

def _ctrl_click_element(driver, element):
    try:
        bot.mouse_move_to_element(driver, element)
        bot.ln_sleep(random.uniform(0.3, 0.8), 0.20)
        sx, sy = bot._element_screen_point(driver, element)
        sx, sy = bot._clamp_screen(sx, sy)
        pyautogui.keyDown('ctrl')
        time.sleep(random.uniform(0.05, 0.12))
        pyautogui.click(sx, sy)
        time.sleep(random.uniform(0.08, 0.15))
        pyautogui.keyUp('ctrl')
        bot.ln_sleep(random.uniform(0.8, 1.5), 0.22)
    except Exception:
        try:
            pyautogui.keyUp('ctrl')
        except Exception:
            pass


# ==============================================================================
# OPEN TABS FROM AMAZON PAGES
# ==============================================================================

def _get_product_links_on_page(driver) -> list:
    selectors = [
        "[data-component-type='s-search-result'] h2 a.a-link-normal",
        "[data-component-type='s-search-result'] a.a-link-normal[href*='/dp/']",
        ".s-result-item h2 a[href*='/dp/']",
        ".s-card-container a.a-link-normal[href*='/dp/']",
    ]
    seen_hrefs = set()
    results = []
    for sel in selectors:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                if not el.is_displayed():
                    continue
                href = el.get_attribute("href") or ""
                if "/dp/" not in href or href in seen_hrefs:
                    continue
                seen_hrefs.add(href)
                results.append(el)
            except Exception:
                pass
    return results


def _human_browse_search_results(driver, stop_event) -> list:
    original_handles = set(driver.window_handles)

    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")))
    except TimeoutException:
        return []

    bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)
    bot.idle_mouse_drift(driver, random.uniform(0.8, 1.8))

    # Scroll page 1
    total_scroll = random.randint(1800, 3200)
    scrolled = 0
    while scrolled < total_scroll and not stop_event.is_set():
        chunk = random.randint(180, 480)
        _scroll_chunk(driver, chunk)
        scrolled += chunk
        bot.ln_sleep(random.uniform(0.6, 2.2), 0.28)
        if random.random() < 0.45:
            links = _get_product_links_on_page(driver)
            if links:
                bot.mouse_move_to_element(driver, random.choice(links[:8]))
                bot.ln_sleep(random.uniform(0.3, 1.0), 0.22)

    if stop_event.is_set():
        return []

    page1_links = _get_product_links_on_page(driver)
    if not page1_links:
        return []

    p1_count  = random.randint(3, min(5, len(page1_links)))
    pool      = page1_links[2:] if len(page1_links) > 4 else page1_links
    p1_chosen = random.sample(pool[:14], min(p1_count, len(pool)))

    for el in p1_chosen:
        if stop_event.is_set():
            break
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", el)
            bot.ln_sleep(random.uniform(0.4, 1.0), 0.22)
        except Exception:
            pass
        _ctrl_click_element(driver, el)
        bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)

    if stop_event.is_set():
        return [h for h in driver.window_handles if h not in original_handles]

    # Page 2
    try:
        next_btn = None
        for sel in ["a.s-pagination-next", "li.a-last a",
                    "a[aria-label='Go to next page']", ".a-pagination .a-last a"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            visible = [e for e in els if e.is_displayed()]
            if visible:
                next_btn = visible[0]
                break

        if next_btn:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", next_btn)
            bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)
            bot.mouse_move_to_element(driver, next_btn)
            bot.ln_sleep(random.uniform(0.4, 1.0), 0.20)
            bot.human_click(driver, next_btn)
            bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
            bot.inject_stealth(driver)
            bot._reset_mouse(driver)

            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR,
                         "[data-component-type='s-search-result']")))
            except TimeoutException:
                pass

            bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)

            p2_scroll = random.randint(1000, 2200)
            p2_scrolled = 0
            while p2_scrolled < p2_scroll and not stop_event.is_set():
                chunk = random.randint(200, 480)
                _scroll_chunk(driver, chunk)
                p2_scrolled += chunk
                bot.ln_sleep(random.uniform(0.5, 1.8), 0.28)

            if not stop_event.is_set():
                page2_links = _get_product_links_on_page(driver)
                p2_count = random.randint(1, min(3, len(page2_links)))
                p2_chosen = random.sample(
                    page2_links[:12], min(p2_count, len(page2_links)))
                for el in p2_chosen:
                    if stop_event.is_set():
                        break
                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", el)
                        bot.ln_sleep(random.uniform(0.4, 1.0), 0.22)
                    except Exception:
                        pass
                    _ctrl_click_element(driver, el)
                    bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)
    except Exception:
        pass

    return [h for h in driver.window_handles if h not in original_handles]


def _open_tabs_from_product_page(driver, stop_event) -> list:
    original_handles = set(driver.window_handles)
    tab_count = random.randint(4, 7)

    carousel_selectors = [
        "#similarities_feature_div a.a-link-normal[href*='/dp/']",
        "#sp_detail a.a-link-normal[href*='/dp/']",
        "#anonCarousel1 a[href*='/dp/']",
        "#anonCarousel2 a[href*='/dp/']",
        "#purchase-sims-feature a[href*='/dp/']",
        "[data-feature-name='purchase-sims-feature'] a[href*='/dp/']",
        "#browseTech a[href*='/dp/']",
        ".p13n-sc-uncoverable-faceout a[href*='/dp/']",
        "[data-component-type='s-product-image'] a[href*='/dp/']",
        "#desktop-rhf-title-feature_div a[href*='/dp/']",
    ]

    candidates = []
    for sel in carousel_selectors:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        candidates.extend([f for f in found if f.is_displayed()])

    seen_hrefs = set()
    unique_candidates = []
    for el in candidates:
        try:
            href = el.get_attribute("href") or ""
            if href and href not in seen_hrefs:
                seen_hrefs.add(href)
                unique_candidates.append(el)
        except Exception:
            pass

    if not unique_candidates:
        return []

    chosen = random.sample(
        unique_candidates[:15],
        min(tab_count, len(unique_candidates))
    )
    for el in chosen:
        if stop_event.is_set():
            break
        _ctrl_click_element(driver, el)
        bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)

    return [h for h in driver.window_handles if h not in original_handles]


# ==============================================================================
# WORK THROUGH ALL OPEN TABS
# ==============================================================================

def _work_through_tabs(driver, tab_handles: list, visit_types: list,
                       cfg: AmazonSessionConfig, progress_fn):
    original_handle = driver.current_window_handle

    for i, handle in enumerate(tab_handles):
        if cfg.stop_event.is_set():
            break
        if handle not in driver.window_handles:
            continue

        visit_type = visit_types[i] if i < len(visit_types) else VISIT_QUICK

        try:
            driver.switch_to.window(handle)
        except Exception:
            continue

        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script(
                    "return document.readyState") == "complete")
        except Exception:
            pass

        bot.inject_stealth(driver)
        bot._reset_mouse(driver)

        label = f"tab {i+1}/{len(tab_handles)}"
        if visit_type == VISIT_DEEP:
            progress_fn(f"Deep visit ({label}) — adding to cart")
            _visit_deep(driver, cfg)
        elif visit_type == VISIT_MEDIUM:
            progress_fn(f"Medium visit ({label})")
            _visit_medium(driver, cfg)
        else:
            progress_fn(f"Quick visit ({label})")
            _visit_quick(driver, cfg)

        if cfg.stop_event.is_set():
            break

        try:
            driver.close()
        except Exception:
            pass

        bot.ln_sleep(random.uniform(0.5, 1.2), 0.22)

    # Return to search results tab
    try:
        if original_handle in driver.window_handles:
            driver.switch_to.window(original_handle)
        elif driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])
    except Exception:
        pass

    bot.inject_stealth(driver)
    bot._reset_mouse(driver)


# ==============================================================================
# AMAZON SEARCH BAR
# ==============================================================================

def _search_amazon_directly(driver, query: str) -> bool:
    try:
        search_box = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "#twotabsearchtextbox, input[name='field-keywords']")))
        bot.mouse_move_to_element(driver, search_box)
        bot.ln_sleep(random.uniform(0.3, 0.8), 0.20)
        bot.human_click(driver, search_box)
        bot.ln_sleep(random.uniform(0.2, 0.5), 0.18)
        search_box.clear()
        bot.ln_sleep(random.uniform(0.1, 0.3), 0.15)
        bot.human_type(search_box, query)
        bot.ln_sleep(random.uniform(0.3, 0.7), 0.18)
        pyautogui.press('enter')
        bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        return True
    except Exception:
        return False


# ==============================================================================
# BROWSE SEARCH RESULTS AND OPEN TABS
# ==============================================================================

def _pick_product_and_open_tabs(driver, cfg: AmazonSessionConfig) -> list:
    if not _is_amazon_search_page(driver):
        return []
    return _human_browse_search_results(driver, cfg.stop_event)


# ==============================================================================
# GOOGLE -> AMAZON
# ==============================================================================

def _google_to_amazon(driver, query, cfg: AmazonSessionConfig) -> bool:
    roll = random.random()
    if roll < 0.60:
        search_q = f"{query} amazon"
    elif roll < 0.85:
        search_q = f"{query} amazon.com"
    else:
        search_q = query

    bot.google_search(driver, search_q)
    if cfg.stop_event.is_set():
        return False

    bot.check_and_wait_captcha(driver)
    if cfg.stop_event.is_set():
        return False

    bot.ln_sleep(random.uniform(1.2, 3.0), 0.22)
    _scroll_chunk(driver, random.randint(100, 300))
    bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    results = bot.get_organic_results(driver, max_results=10)
    amazon_results = [(t, u) for t, u in results if "amazon.com" in u]
    if not amazon_results:
        return False

    weights    = [1.0 / (i + 1) for i in range(len(amazon_results))]
    total_w    = sum(weights)
    r          = random.random() * total_w
    chosen_url = amazon_results[0][1]
    cumulative = 0
    for (title, url), w in zip(amazon_results, weights):
        cumulative += w
        if r <= cumulative:
            chosen_url = url
            break

    for title, url in amazon_results[:3]:
        if url == chosen_url:
            break
        try:
            els = driver.find_elements(
                By.CSS_SELECTOR, f"div#search a[href='{url}']")
            if els and els[0].is_displayed():
                bot.mouse_move_to_element(driver, els[0])
                bot.ln_sleep(random.uniform(0.3, 0.9), 0.20)
        except Exception:
            pass

    bot.click_result(driver, chosen_url)
    if cfg.stop_event.is_set():
        return False

    bot.inject_stealth(driver)
    bot._reset_mouse(driver)
    return True


# ==============================================================================
# ONE AMAZON STINT
# ==============================================================================

def _run_amazon_stint(driver, cfg: AmazonSessionConfig,
                      stint_type: str, query_pool: list,
                      query_idx: int, progress_fn) -> int:
    if stint_type == STINT_SHORT:
        stint_s = random.uniform(15 * 60, 18 * 60)
    else:
        stint_s = random.uniform(20 * 60, 30 * 60)

    stint_end     = time.time() + stint_s
    products_done = 0

    progress_fn(
        f"Amazon stint "
        f"({'short ~15-18min' if stint_type == STINT_SHORT else 'long ~20-30min'})"
    )

    while time.time() < stint_end and not cfg.stop_event.is_set():
        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0
        cat, query = query_pool[query_idx]
        query_idx += 1

        progress_fn(f"Searching Amazon: {query[:50]}")
        searched = _search_amazon_directly(driver, query)

        if cfg.stop_event.is_set():
            break
        if not searched:
            bot.ln_sleep(random.uniform(3.0, 6.0), 0.25)
            continue

        bot.check_and_wait_captcha(driver)
        if cfg.stop_event.is_set():
            break

        progress_fn(f"Opening product tabs for: {query[:45]}")
        new_tabs = _pick_product_and_open_tabs(driver, cfg)

        if cfg.stop_event.is_set():
            break
        if not new_tabs:
            bot.ln_sleep(random.uniform(3.0, 6.0), 0.25)
            continue

        visit_types  = _assign_visit_types(len(new_tabs))
        deep_count   = visit_types.count(VISIT_DEEP)
        medium_count = visit_types.count(VISIT_MEDIUM)
        quick_count  = visit_types.count(VISIT_QUICK)
        progress_fn(
            f"{len(new_tabs)} tabs: "
            f"{deep_count} deep / {medium_count} medium / {quick_count} quick"
        )

        _work_through_tabs(driver, new_tabs, visit_types, cfg, progress_fn)
        products_done += len(new_tabs)

        if cfg.stop_event.is_set():
            break

        if time.time() < stint_end:
            pause = math.exp(random.gauss(math.log(6.0), 0.40))
            pause = max(2.5, min(15.0, pause))
            time.sleep(pause)

    progress_fn(f"Stint done — {products_done} tabs visited")
    return query_idx


# ==============================================================================
# MAIN SESSION RUNNER
# ==============================================================================

def run_amazon_session(driver, cfg: AmazonSessionConfig):
    """
    Main entry point.
    Loop: Google -> Amazon -> SHORT stint -> Google -> Amazon -> LONG stint -> repeat
    """
    session_end  = time.time() + cfg.session_minutes * 60
    total_time   = cfg.session_minutes * 60
    query_pool   = _load_queries_for_categories(cfg.categories)

    if not query_pool:
        if cfg.on_progress:
            cfg.on_progress("No queries found for selected categories.", 0)
        return

    query_idx    = 0
    stint_toggle = STINT_SHORT
    google_tab   = driver.current_window_handle

    def _progress(text):
        if cfg.on_progress and not cfg.stop_event.is_set():
            elapsed = time.time() - (session_end - total_time)
            pct     = min(99, int(elapsed / total_time * 100))
            cfg.on_progress(text, pct)

    _progress("Starting Amazon session...")

    while time.time() < session_end and not cfg.stop_event.is_set():

        try:
            if google_tab in driver.window_handles:
                driver.switch_to.window(google_tab)
            elif driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
                google_tab = driver.current_window_handle
        except Exception:
            pass

        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0
        cat, query = query_pool[query_idx]
        query_idx += 1

        _progress(f"Googling: {query[:55]}")
        found = _google_to_amazon(driver, query, cfg)

        if cfg.stop_event.is_set():
            break
        if not found:
            bot.ln_sleep(random.uniform(3.0, 7.0), 0.25)
            continue

        bot.check_and_wait_captcha(driver)
        if cfg.stop_event.is_set():
            break

        google_tab = driver.current_window_handle

        _progress("Opening product tabs (first round after Google)")
        first_tabs = _pick_product_and_open_tabs(driver, cfg)

        if cfg.stop_event.is_set():
            break

        if first_tabs:
            visit_types = _assign_visit_types(len(first_tabs))
            d = visit_types.count(VISIT_DEEP)
            m = visit_types.count(VISIT_MEDIUM)
            q = visit_types.count(VISIT_QUICK)
            _progress(f"{len(first_tabs)} tabs: {d} deep / {m} medium / {q} quick")
            _work_through_tabs(driver, first_tabs, visit_types, cfg, _progress)

        if cfg.stop_event.is_set():
            break

        query_idx = _run_amazon_stint(
            driver=driver,
            cfg=cfg,
            stint_type=stint_toggle,
            query_pool=query_pool,
            query_idx=query_idx,
            progress_fn=_progress,
        )

        if cfg.stop_event.is_set():
            break

        stint_toggle = STINT_LONG if stint_toggle == STINT_SHORT else STINT_SHORT

        if time.time() < session_end and not cfg.stop_event.is_set():
            bot.ln_sleep(random.uniform(3.0, 8.0), 0.28)

    if cfg.on_progress:
        cfg.on_progress("Amazon session complete.", 100)
