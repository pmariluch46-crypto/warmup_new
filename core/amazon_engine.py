"""
core/amazon_engine.py -- Amazon Warm-up session engine.

Session flow:
  CYCLE (repeats until session ends):
    1. Google -> search "[query] amazon" -> click Amazon result
    2. Land on Amazon search results page
    3. Ctrl+Click 4-7 product thumbnails -> open in new tabs
    4. Assign each tab a visit type upfront (20% deep / 50% medium / 30% quick)
    5. Work through each tab:
         deep  (20%) : 3-7 min  - images -> description -> reviews -> review photos -> add to cart
         medium(50%) : 30s-2min - images + scrolling -> close
         quick (30%) : 20-40s  - quick glance -> close
    6. After all tabs closed -> stay on Amazon -> search next product in Amazon search bar
    7. Repeat steps 3-6 for a "stint":
         - SHORT stint : 15-18 min
         - LONG  stint : 20-30 min
    8. After stint ends -> switch back to Google tab -> new query -> new Amazon stint
    9. Stints alternate SHORT -> LONG -> SHORT -> LONG ... until session ends

Cart rule:
  - Max 4 items at any time
  - Before adding: check cart count -> while count >= 4 -> delete the very first/oldest item
  - Works regardless of how many items are manually in cart
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
        self.categories      = categories       # list[str]
        self.session_minutes = session_minutes  # int
        self.read_reviews    = read_reviews     # bool
        self.stop_event      = stop_event       # threading.Event
        self.on_progress     = on_progress      # callable(text, pct) | None

# Visit-type constants
VISIT_DEEP   = "deep"    # 20% -- 3-7 min, full engagement + add to cart
VISIT_MEDIUM = "medium"  # 50% -- 30s-2min, images + scroll
VISIT_QUICK  = "quick"   # 30% -- 20-40s, quick glance

# Stint length constants
STINT_SHORT = "short"    # 15-18 min on Amazon
STINT_LONG  = "long"     # 20-30 min on Amazon

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
# PAGE DETECTION HELPERS
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

# ==============================================================================
# COOKIE HELPER
# ==============================================================================

def _accept_amazon_cookies(driver):
    for sel in [
        "#sp-cc-accept", "input[name='accept']",
        "button[data-cel-widget='sp-cc-accept']",
        "#acceptCookies",
    ]:
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            bot.human_click(driver, btn)
            bot.ln_sleep(0.8, 0.20)
            return
        except Exception:
            continue

# ==============================================================================
# CART MANAGEMENT
# ==============================================================================

def _get_cart_count(driver) -> int:
    """Return current number of items shown in the cart badge."""
    try:
        el = driver.find_element(
            By.CSS_SELECTOR,
            "#nav-cart-count, span[data-csa-c-content-id='nav-cart-count']"
        )
        text = el.text.strip()
        return int(text) if text.isdigit() else 0
    except Exception:
        return 0

def _open_cart(driver):
    """Navigate to the cart page."""
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
    """Delete the very first (oldest) item visible in the cart."""
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
    """
    Ensure cart has fewer than 4 items.
    Keeps deleting the first/oldest item until count < 4.
    Works even if user manually filled the cart with many items.
    """
    try:
        count = _get_cart_count(driver)
        while count >= 4:
            _delete_first_cart_item(driver)
            bot.ln_sleep(random.uniform(0.8, 1.5), 0.20)
            count = _get_cart_count(driver)
    except Exception:
        pass

def _add_to_cart(driver) -> bool:
    """
    Add current product to cart after ensuring room (max 4 rule).
    Returns True if successfully added.
    """
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

                # Dismiss any "Added to cart" modal / side sheet
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
# PRODUCT PAGE INTERACTION HELPERS
# ==============================================================================

def _scroll_images(driver, stop_event):
    """Click through product image thumbnails like a real shopper."""
    try:
        thumbs = driver.find_elements(
            By.CSS_SELECTOR,
            "#altImages li.item img, #imageBlock_feature_div li img"
        )
        visible_thumbs = [t for t in thumbs[:8] if t.is_displayed()]
        if not visible_thumbs:
            return
        count = random.randint(2, min(len(visible_thumbs), 5))
        for thumb in random.sample(visible_thumbs, count):
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, thumb)
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)
            bot.human_click(driver, thumb)
            bot.ln_sleep(random.uniform(0.8, 2.5), 0.25)
    except Exception:
        pass

def _read_description(driver, stop_event):
    """Scroll to and hover over product description / feature bullets."""
    try:
        for sel in ["#feature-bullets", "#productDescription", "#aplus"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", el)
                bot.ln_sleep(random.uniform(0.6, 1.4), 0.20)
                break
            except Exception:
                continue

        bullets = driver.find_elements(
            By.CSS_SELECTOR, "#feature-bullets li span.a-list-item")
        visible = [b for b in bullets[:10]
                   if b.is_displayed() and b.text.strip()]
        read_count = random.randint(1, max(1, len(visible)))
        for bullet in visible[:read_count]:
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, bullet)
            bot.ln_sleep(random.uniform(0.8, 2.2), 0.25)

        bot.scroll_page(driver, random.randint(200, 500))
        bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)
    except Exception:
        pass

def _view_review_images(driver, stop_event):
    """
    Click and view customer review photos (the image strip under reviews).
    """
    try:
        img_selectors = [
            "[data-hook='review-image-tile'] img",
            ".review-image-tile img",
            "#cm_cr_dp_d_review_image_gallery img",
            "[data-hook='cr-media-acr-widget'] img",
            ".cr-lightbox-mobile-thumbnail img",
        ]
        review_imgs = []
        for sel in img_selectors:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            review_imgs.extend([i for i in found if i.is_displayed()])
            if review_imgs:
                break

        if not review_imgs:
            return

        click_count = random.randint(1, min(3, len(review_imgs)))
        for img in random.sample(review_imgs[:8], click_count):
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, img)
            bot.ln_sleep(random.uniform(0.4, 1.0), 0.20)
            bot.human_click(driver, img)
            # Look at the photo for a natural amount of time
            bot.ln_sleep(random.uniform(1.5, 4.0), 0.25)

            # Close lightbox if it opened
            for close_sel in [
                "button.a-popover-closebutton",
                ".cr-lightbox-close",
                "button[aria-label='Close']",
                ".a-icon-close",
            ]:
                try:
                    close = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, close_sel)))
                    bot.human_click(driver, close)
                    bot.ln_sleep(0.5, 0.18)
                    break
                except Exception:
                    pass
    except Exception:
        pass

def _read_reviews(driver, stop_event):
    """Scroll to reviews, read a few, and view customer review photos."""
    try:
        # Scroll to reviews section
        for sel in ["#reviewsMedley", "#customer-reviews-content",
                    "#reviews-medley-footer"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", el)
                bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)
                break
            except Exception:
                continue

        # Read review bodies
        reviews = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-hook='review'] [data-hook='review-body'] span, "
            ".review-text-content span"
        )
        visible = [r for r in reviews[:6]
                   if r.is_displayed() and len(r.text.strip()) > 30]
        read_count = random.randint(1, max(1, min(3, len(visible))))
        for review in visible[:read_count]:
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, review)
            read_time = min(8.0,
                len(review.text) / 200.0 + random.uniform(1.0, 3.0))
            bot.ln_sleep(read_time, 0.20)
            if random.random() < 0.4:
                bot.scroll_page(driver, random.randint(100, 280))
                bot.ln_sleep(random.uniform(0.4, 1.0), 0.18)

        # Check star rating histogram occasionally
        if random.random() < 0.4:
            try:
                hist = driver.find_element(
                    By.CSS_SELECTOR,
                    "#histogramTable, .cr-widget-Histogram")
                bot.mouse_move_to_element(driver, hist)
                bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)
            except Exception:
                pass

        # View customer review photos (70% chance)
        if stop_event.is_set():
            return
        if random.random() < 0.70:
            _view_review_images(driver, stop_event)

    except Exception:
        pass

# ==============================================================================
# TAB VISIT HANDLERS
# ==============================================================================

def _visit_deep(driver, cfg: AmazonSessionConfig):
    """
    Deep visit: 3-7 minutes.
    images -> description -> reviews -> review photos -> add to cart
    """
    stay_s = random.uniform(180, 420)  # 3-7 min
    end_t  = time.time() + stay_s

    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)

    if cfg.stop_event.is_set():
        return

    # Initial page glance
    bot.scroll_page(driver, random.randint(200, 500))
    bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)

    # 1. Product images
    _scroll_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # 2. Description / bullets
    if time.time() < end_t:
        _read_description(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # 3. Reviews + review photos
    if time.time() < end_t:
        _read_reviews(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # 4. Add to cart
    if time.time() < end_t:
        _add_to_cart(driver)
    if cfg.stop_event.is_set():
        return

    # 5. Fill remaining time with natural scrolling / mouse drift
    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.5:
            break
        roll = random.random()
        if roll < 0.35:
            bot.scroll_page(driver,
                random.choice([1, -1]) * random.randint(100, 350))
            bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)
        elif roll < 0.55:
            bot.idle_mouse_drift(driver, min(remaining * 0.3, 3.0))
        elif roll < 0.68:
            bot.occasional_ctrl_f(driver, chance=1.0, context='amazon')
        else:
            time.sleep(min(remaining, random.uniform(1.0, 4.0)))


def _visit_medium(driver, cfg: AmazonSessionConfig):
    """
    Medium visit: 30 seconds - 2 minutes.
    Glance at images + some scrolling.
    """
    stay_s = random.uniform(30, 120)
    end_t  = time.time() + stay_s

    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)

    if cfg.stop_event.is_set():
        return

    bot.scroll_page(driver, random.randint(150, 400))
    bot.ln_sleep(random.uniform(0.6, 1.5), 0.22)

    _scroll_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.4:
            break
        roll = random.random()
        if roll < 0.45:
            bot.scroll_page(driver,
                random.choice([1, -1]) * random.randint(100, 320))
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)
        elif roll < 0.65:
            bot.idle_mouse_drift(driver, min(remaining * 0.25, 2.0))
        else:
            time.sleep(min(remaining, random.uniform(1.0, 3.0)))


def _visit_quick(driver, cfg: AmazonSessionConfig):
    """
    Quick visit: 20-40 seconds.
    Quick glance, minimal interaction.
    """
    stay_s = random.uniform(20, 40)
    end_t  = time.time() + stay_s

    bot.inject_stealth(driver)

    if cfg.stop_event.is_set():
        return

    bot.scroll_page(driver, random.randint(100, 300))
    bot.ln_sleep(random.uniform(0.5, 1.2), 0.22)

    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.3:
            break
        if random.random() < 0.5:
            bot.scroll_page(driver, random.randint(80, 220))
        bot.ln_sleep(random.uniform(0.5, 1.5), 0.22)

# ==============================================================================
# TAB VISIT TYPE ASSIGNMENT
# ==============================================================================

def _assign_visit_types(tab_count: int) -> list:
    """
    Randomly assign visit types to tab_count tabs UPFRONT before visiting any.
    20% deep, 50% medium, 30% quick.
    Guarantees at least 1 deep if tab_count >= 3.
    """
    types = []
    for _ in range(tab_count):
        r = random.random()
        if r < 0.20:
            types.append(VISIT_DEEP)
        elif r < 0.70:
            types.append(VISIT_MEDIUM)
        else:
            types.append(VISIT_QUICK)

    # Guarantee at least 1 deep visit if we have enough tabs
    if tab_count >= 3 and VISIT_DEEP not in types:
        types[random.randint(0, tab_count - 1)] = VISIT_DEEP

    return types

# ==============================================================================
# CTRL+CLICK HELPER
# ==============================================================================

def _ctrl_click_element(driver, element):
    """Ctrl+Click an element to open its link in a new tab."""
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
        pass

# ==============================================================================
# OPEN TABS FROM AMAZON PAGES
# ==============================================================================

def _open_tabs_from_search_results(driver, stop_event) -> list:
    """
    From an Amazon search results page, Ctrl+Click 4-7 product thumbnails
    to open them in new tabs.
    Returns list of new tab handles.
    """
    original_handles = set(driver.window_handles)
    tab_count = random.randint(4, 7)

    product_selectors = [
        "[data-component-type='s-search-result'] h2 a.a-link-normal",
        "[data-component-type='s-search-result'] a.a-link-normal[href*='/dp/']",
        ".s-result-item h2 a",
    ]
    candidates = []
    for sel in product_selectors:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        candidates.extend([f for f in found if f.is_displayed()])
        if len(candidates) >= 10:
            break

    # Scroll to reveal more
    bot.scroll_page(driver, random.randint(200, 500))
    bot.ln_sleep(random.uniform(0.6, 1.2), 0.20)

    candidates = []
    for sel in product_selectors:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        candidates.extend([f for f in found if f.is_displayed()])
        if len(candidates) >= 10:
            break

    if not candidates:
        return []

    chosen = random.sample(candidates[:12], min(tab_count, len(candidates)))
    for el in chosen:
        if stop_event.is_set():
            break
        _ctrl_click_element(driver, el)
        bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)

    new_handles = [h for h in driver.window_handles
                   if h not in original_handles]
    return new_handles


def _open_tabs_from_product_page(driver, stop_event) -> list:
    """
    From an Amazon product page, Ctrl+Click 4-7 links from
    'Similar items', 'Customers also bought', and search results carousels.
    Returns list of new tab handles.
    """
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

    # Deduplicate by href
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

    new_handles = [h for h in driver.window_handles
                   if h not in original_handles]
    return new_handles

# ==============================================================================
# WORK THROUGH ALL OPEN TABS
# ==============================================================================

def _work_through_tabs(driver, tab_handles: list, visit_types: list,
                       cfg: AmazonSessionConfig, progress_fn):
    """
    Switch to each tab, perform assigned visit type, close the tab.
    Returns to original tab when done.
    """
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

        # Wait for page to load
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
            progress_fn(f"Deep visit ({label})")
            _visit_deep(driver, cfg)
        elif visit_type == VISIT_MEDIUM:
            progress_fn(f"Medium visit ({label})")
            _visit_medium(driver, cfg)
        else:
            progress_fn(f"Quick visit ({label})")
            _visit_quick(driver, cfg)

        if cfg.stop_event.is_set():
            break

        # Close this tab
        try:
            driver.close()
        except Exception:
            pass

        bot.ln_sleep(random.uniform(0.5, 1.2), 0.22)

    # Return to original tab (Amazon search results)
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
    """
    Type a new query in the Amazon search bar and submit.
    Used to stay on Amazon between product rounds without going back to Google.
    """
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
# NAVIGATE TO A PRODUCT PAGE THEN OPEN CAROUSEL TABS
# ==============================================================================

def _pick_product_and_open_tabs(driver, cfg: AmazonSessionConfig) -> list:
    """
    From an Amazon search results page:
      1. Click one product to land on its product page
      2. Open 4-7 tabs from carousels on that product page
    Returns list of new tab handles.
    """
    if not _is_amazon_search_page(driver):
        return []

    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "[data-component-type='s-search-result']")))
    except TimeoutException:
        return []

    bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)

    products = driver.find_elements(
        By.CSS_SELECTOR,
        "[data-component-type='s-search-result'] h2 a.a-link-normal"
    )
    visible = [p for p in products[:12] if p.is_displayed()]
    if not visible:
        return []

    # Pick one product — bias toward top results
    weights = [1.0 / (i + 1) for i in range(len(visible))]
    total_w = sum(weights)
    r = random.random() * total_w
    chosen = visible[0]
    cumulative = 0
    for el, w in zip(visible, weights):
        cumulative += w
        if r <= cumulative:
            chosen = el
            break

    bot.mouse_move_to_element(driver, chosen)
    bot.ln_sleep(random.uniform(0.4, 0.9), 0.20)
    bot.human_click(driver, chosen)
    bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
    bot.inject_stealth(driver)
    bot._reset_mouse(driver)

    if not _is_amazon_product_page(driver):
        return []

    # Open tabs from carousels on this product page
    return _open_tabs_from_product_page(driver, cfg.stop_event)

# ==============================================================================
# GOOGLE -> AMAZON
# ==============================================================================

def _google_to_amazon(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    Search Google for the query, find an Amazon result, click it.
    Returns True if we landed on an Amazon page.
    """
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
    bot.scroll_page(driver, random.randint(100, 300))
    bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    results = bot.get_organic_results(driver, max_results=10)
    amazon_results = [(t, u) for t, u in results if "amazon.com" in u]

    if not amazon_results:
        return False

    # Bias toward first result
    weights = [1.0 / (i + 1) for i in range(len(amazon_results))]
    total_w = sum(weights)
    r = random.random() * total_w
    chosen_title, chosen_url = amazon_results[0]
    cumulative = 0
    for (title, url), w in zip(amazon_results, weights):
        cumulative += w
        if r <= cumulative:
            chosen_title, chosen_url = title, url
            break

    # Hover a couple results before clicking
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
    """
    Run one continuous Amazon stint (SHORT: 15-18min or LONG: 20-30min).
    Loops: search Amazon -> open tabs -> work tabs -> repeat.
    Returns updated query_idx.
    """
    if stint_type == STINT_SHORT:
        stint_s = random.uniform(15 * 60, 18 * 60)
    else:
        stint_s = random.uniform(20 * 60, 30 * 60)

    stint_end    = time.time() + stint_s
    products_done = 0

    progress_fn(
        f"Amazon stint ({'short ~15-18min' if stint_type == STINT_SHORT else 'long ~20-30min'})"
    )

    while time.time() < stint_end and not cfg.stop_event.is_set():

        # Pick next query
        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0
        cat, query = query_pool[query_idx]
        query_idx += 1

        # Search Amazon directly (we're already on Amazon)
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

        # Navigate to a product page then open carousel tabs
        progress_fn(f"Opening product tabs for: {query[:45]}")
        new_tabs = _pick_product_and_open_tabs(driver, cfg)

        if cfg.stop_event.is_set():
            break

        if not new_tabs:
            bot.ln_sleep(random.uniform(3.0, 6.0), 0.25)
            continue

        # Assign all visit types upfront
        visit_types  = _assign_visit_types(len(new_tabs))
        deep_count   = visit_types.count(VISIT_DEEP)
        medium_count = visit_types.count(VISIT_MEDIUM)
        quick_count  = visit_types.count(VISIT_QUICK)
        progress_fn(
            f"{len(new_tabs)} tabs: "
            f"{deep_count} deep / {medium_count} medium / {quick_count} quick"
        )

        # Work through each tab
        _work_through_tabs(driver, new_tabs, visit_types, cfg, progress_fn)
        products_done += len(new_tabs)

        if cfg.stop_event.is_set():
            break

        # Inter-query pause before next round
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
    Main entry point called from tab_amazon._worker.

    Loop:
      1. Google -> search -> land on Amazon
      2. Run a SHORT Amazon stint (15-18 min) -- searching in Amazon search bar
      3. Go back to Google -> new query -> land on Amazon
      4. Run a LONG Amazon stint (20-30 min)
      5. Repeat (alternating SHORT/LONG) until session_minutes expires
    """
    session_end  = time.time() + cfg.session_minutes * 60
    total_time   = cfg.session_minutes * 60
    query_pool   = _load_queries_for_categories(cfg.categories)

    if not query_pool:
        if cfg.on_progress:
            cfg.on_progress("No queries found for selected categories.", 0)
        return

    query_idx    = 0
    stint_toggle = STINT_SHORT   # first stint is always SHORT
    google_tab   = driver.current_window_handle

    def _progress(text):
        if cfg.on_progress and not cfg.stop_event.is_set():
            elapsed = time.time() - (session_end - total_time)
            pct     = min(99, int(elapsed / total_time * 100))
            cfg.on_progress(text, pct)

    _progress("Starting Amazon session...")

    while time.time() < session_end and not cfg.stop_event.is_set():

        # ── Switch back to Google tab ────────────────────────────────────
        try:
            if google_tab in driver.window_handles:
                driver.switch_to.window(google_tab)
            elif driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
                google_tab = driver.current_window_handle
        except Exception:
            pass

        # ── Pick Google query ────────────────────────────────────────────
        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0
        cat, query = query_pool[query_idx]
        query_idx += 1

        # ── Google -> Amazon ─────────────────────────────────────────────
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

        # Remember the current tab as google_tab for this cycle
        google_tab = driver.current_window_handle

        # ── First round: open tabs directly from the Amazon search page ──
        # (this is the landing from Google -- we're on Amazon search results)
        progress_fn = _progress
        progress_fn(f"Opening product tabs (first round after Google)")
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

        # ── Run the Amazon stint (stays on Amazon, uses Amazon search bar) ──
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

        # Alternate SHORT <-> LONG for next cycle
        stint_toggle = STINT_LONG if stint_toggle == STINT_SHORT else STINT_SHORT

        # Brief pause before returning to Google
        if time.time() < session_end and not cfg.stop_event.is_set():
            bot.ln_sleep(random.uniform(3.0, 8.0), 0.28)

    # ── Session complete ──────────────────────────────────────────────────
    if cfg.on_progress:
        cfg.on_progress("Amazon session complete.", 100)
