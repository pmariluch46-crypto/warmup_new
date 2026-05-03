"""
core/amazon_engine.py -- Amazon Warm-up session engine.

Flow:
  1. Google search for "[query] amazon" (or plain query → prefer amazon result)
  2. Click Amazon product result from Google
  3. On product page: spend 10–200s doing human-like interactions
     (scroll, read bullets, check images, read reviews)
  4. Occasionally open 1–2 related products in NEW TABS and browse them
  5. 1–2 products per session get added to cart
     → if cart has more than 3 items, remove the oldest (first) one first
  6. After product: 50% go back → pick next result | 50% search new query
  7. Repeat until session_minutes expires or stop_event is set
"""

import time
import math
import random
import pyautogui

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from core import browser_bot as bot

# ==============================================================================
# CONFIG DATACLASS
# ==============================================================================

class AmazonSessionConfig:
    def __init__(self, categories, session_minutes, read_reviews,
                 stop_event, on_progress=None):
        self.categories      = categories       # list[str]
        self.session_minutes = session_minutes  # int
        self.read_reviews    = read_reviews     # bool
        self.stop_event      = stop_event       # threading.Event
        self.on_progress     = on_progress      # callable(text, pct) | None

# ==============================================================================
# AMAZON QUERY LOADER
# ==============================================================================

def _load_queries_for_categories(categories, on_progress=None):
    """
    Load amazon queries from data/amazon_queries.json for selected categories.
    Returns a flat list of (category, query) tuples.
    Surfaces errors via on_progress instead of silently returning empty.
    """
    from core.amazon_query_manager import load_amazon_queries
    try:
        data = load_amazon_queries()
    except Exception as e:
        if on_progress:
            on_progress(f"Failed to load queries: {e}", 0)
        return []

    pool = []
    for cat in categories:
        for q in data.get(cat, []):
            pool.append((cat, q))
    random.shuffle(pool)
    return pool

# ==============================================================================
# AMAZON-SPECIFIC PAGE HELPERS
# ==============================================================================

def _is_amazon_product_page(driver) -> bool:
    """True if current URL looks like an Amazon product detail page."""
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

def _scroll_images(driver, stop_event):
    """Cycle through product image thumbnails like a real shopper."""
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
    """Scroll through and hover over product description / feature bullets."""
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
        visible = [b for b in bullets[:10] if b.is_displayed() and b.text.strip()]
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

def _read_reviews(driver, stop_event):
    """Scroll to reviews section and read a few."""
    try:
        for sel in ["#reviewsMedley", "#customer-reviews-content", "#reviews-medley-footer"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", el)
                bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)
                break
            except Exception:
                continue

        reviews = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-hook='review'] [data-hook='review-body'] span, "
            ".review-text-content span"
        )
        visible = [r for r in reviews[:6] if r.is_displayed() and len(r.text.strip()) > 30]
        read_count = random.randint(1, max(1, min(3, len(visible))))
        for review in visible[:read_count]:
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, review)
            read_time = min(8.0, len(review.text) / 200.0 + random.uniform(1.0, 3.0))
            bot.ln_sleep(read_time, 0.20)
            if random.random() < 0.4:
                bot.scroll_page(driver, random.randint(100, 280))
                bot.ln_sleep(random.uniform(0.4, 1.0), 0.18)

        if random.random() < 0.4:
            try:
                hist = driver.find_element(
                    By.CSS_SELECTOR, "#histogramTable, .cr-widget-Histogram")
                bot.mouse_move_to_element(driver, hist)
                bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)
            except Exception:
                pass
    except Exception:
        pass

# ==============================================================================
# NEW-TAB PRODUCT BROWSING
# ==============================================================================

def _open_related_in_new_tab(driver, stop_event) -> bool:
    """
    Find a related/similar product link, open it in a new tab,
    browse it naturally, then close the tab and return to the original.
    Returns True if a new tab was successfully opened and browsed.
    """
    try:
        selectors = [
            "#similarities_feature_div a.a-link-normal[href*='/dp/']",
            "#sp_detail a.a-link-normal[href*='/dp/']",
            "#anonCarousel1 a[href*='/dp/']",
            ".p13n-sc-uncoverable-faceout a[href*='/dp/']",
            "[data-component-type='s-product-image'] a[href*='/dp/']",
        ]
        candidates = []
        for sel in selectors:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            candidates.extend([f for f in found if f.is_displayed()])
            if candidates:
                break

        if not candidates:
            return False

        chosen = random.choice(candidates[:6])
        href = chosen.get_attribute("href")
        if not href:
            return False

        # Scroll to the element so the user can see what they're about to open
        bot.mouse_move_to_element(driver, chosen)
        bot.ln_sleep(random.uniform(0.4, 1.0), 0.20)

        # Open in new tab via middle-click simulation (Ctrl+Click)
        original_tab = driver.current_window_handle
        original_handles = set(driver.window_handles)

        pyautogui.keyDown('ctrl')
        bot.ln_sleep(0.08, 0.05)
        bot.human_click(driver, chosen)
        bot.ln_sleep(0.12, 0.08)
        pyautogui.keyUp('ctrl')

        # Wait for the new tab to appear (up to 5s)
        deadline = time.time() + 5.0
        new_handle = None
        while time.time() < deadline:
            new_handles = set(driver.window_handles) - original_handles
            if new_handles:
                new_handle = new_handles.pop()
                break
            time.sleep(0.3)

        if not new_handle:
            # Ctrl+Click didn't open a new tab — fall back to JS open
            driver.execute_script(f"window.open('{href}', '_blank');")
            bot.ln_sleep(1.0, 0.20)
            new_handles = set(driver.window_handles) - original_handles
            if not new_handles:
                return False
            new_handle = new_handles.pop()

        # Switch to the new tab
        driver.switch_to.window(new_handle)
        bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)

        if stop_event.is_set():
            driver.close()
            driver.switch_to.window(original_tab)
            return False

        # Browse the product in the new tab — shorter stay, more focused
        _accept_amazon_cookies(driver)
        bot.scroll_page(driver, random.randint(200, 450))
        bot.ln_sleep(random.uniform(0.8, 1.6), 0.22)

        _scroll_images(driver, stop_event)
        if stop_event.is_set():
            driver.close()
            driver.switch_to.window(original_tab)
            return False

        _read_description(driver, stop_event)

        # Shorter natural browsing loop in new tab (15–60s)
        tab_end = time.time() + random.uniform(15, 60)
        while time.time() < tab_end and not stop_event.is_set():
            remaining = tab_end - time.time()
            if remaining < 0.5:
                break
            roll = random.random()
            if roll < 0.40:
                bot.scroll_page(driver, random.choice([1, -1]) * random.randint(80, 300))
                bot.ln_sleep(random.uniform(0.4, 1.2), 0.18)
            elif roll < 0.60:
                bot.idle_mouse_drift(driver, min(remaining * 0.3, 2.0))
            else:
                time.sleep(min(remaining, random.uniform(1.0, 3.0)))

        # Close the new tab and return to original
        driver.close()
        driver.switch_to.window(original_tab)
        bot.ln_sleep(random.uniform(0.8, 1.5), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        return True

    except Exception:
        # Always try to get back to the original tab on any error
        try:
            if original_tab in driver.window_handles:
                driver.switch_to.window(original_tab)
        except Exception:
            pass
        return False

# ==============================================================================
# CART MANAGEMENT
# ==============================================================================

def _get_cart_item_count(driver) -> int:
    """Return how many items are currently in the cart (0 if undetectable)."""
    try:
        count_el = driver.find_element(By.CSS_SELECTOR, "#nav-cart-count")
        return int(count_el.text.strip())
    except Exception:
        return 0

def _add_to_cart(driver, stop_event) -> bool:
    """
    Attempt to click the Add to Cart button on the current product page.
    Returns True if successfully added.
    """
    try:
        add_btn = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#add-to-cart-button, "
                "input#add-to-cart-button, "
                "[name='submit.add-to-cart']"
            ))
        )
        # Scroll button into view and hover naturally before clicking
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", add_btn)
        bot.ln_sleep(random.uniform(0.6, 1.4), 0.22)
        bot.mouse_move_to_element(driver, add_btn)
        bot.ln_sleep(random.uniform(0.3, 0.8), 0.18)
        bot.human_click(driver, add_btn)
        bot.ln_sleep(random.uniform(1.5, 3.0), 0.22)

        # Dismiss any "Added to cart" popup / side panel naturally
        # Try clicking "Continue shopping" or just pressing Escape
        for dismiss_sel in [
            "[data-action='a-popover-close']",
            "button[data-action='a-popover-close']",
            "#attach-close_sideSheet-link",
            ".a-popover-footer button",
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, dismiss_sel)
                if btn.is_displayed():
                    bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)
                    bot.human_click(driver, btn)
                    bot.ln_sleep(random.uniform(0.5, 1.0), 0.18)
                    break
            except Exception:
                continue
        else:
            # Nothing to dismiss found — press Escape as fallback
            pyautogui.press('escape')
            bot.ln_sleep(0.5, 0.18)

        return True

    except Exception:
        return False

def _remove_oldest_cart_item(driver, stop_event) -> bool:
    """
    Navigate to the cart page, find the first (oldest) item's delete button,
    and remove it. Returns True if an item was removed.
    """
    try:
        original_url = driver.current_url

        # Navigate to cart
        bot.navigate_addressbar(driver, "https://www.amazon.com/gp/cart/view.html")
        bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)

        if stop_event.is_set():
            return False

        # Wait for cart items to load
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-name='Active Items']")))
        except TimeoutException:
            pass

        # Find all delete buttons — first one = oldest item
        delete_buttons = driver.find_elements(
            By.CSS_SELECTOR,
            "input[value='Delete'], "
            "[data-action='delete'], "
            ".sc-action-delete input[type='submit']"
        )
        delete_buttons = [b for b in delete_buttons if b.is_displayed()]

        if not delete_buttons:
            return False

        first_delete = delete_buttons[0]

        # Scroll to the item and read it briefly (natural behavior)
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", first_delete)
        bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)
        bot.mouse_move_to_element(driver, first_delete)
        bot.ln_sleep(random.uniform(0.4, 0.9), 0.18)
        bot.human_click(driver, first_delete)
        bot.ln_sleep(random.uniform(1.5, 2.5), 0.22)

        # Navigate back to where we were
        if "amazon.com" in original_url:
            bot.navigate_addressbar(driver, original_url)
            bot.ln_sleep(random.uniform(2.0, 3.0), 0.22)
            bot.inject_stealth(driver)

        return True

    except Exception:
        return False

def _maybe_add_to_cart(driver, cfg: AmazonSessionConfig,
                       session_state: dict) -> bool:
    """
    Decide whether to add the current product to cart based on session quota
    (1–2 adds per session). Manages cart size: removes oldest if >3 items.
    Returns True if an item was added.
    """
    # Already hit the session add-to-cart limit
    if session_state['cart_adds'] >= session_state['cart_adds_target']:
        return False

    # ~40% chance to add this particular product
    if random.random() > 0.40:
        return False

    if cfg.stop_event.is_set():
        return False

    # Check current cart size — remove oldest if over 3
    cart_count = _get_cart_item_count(driver)
    if cart_count >= 3:
        _remove_oldest_cart_item(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return False
        bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)

    added = _add_to_cart(driver, cfg.stop_event)
    if added:
        session_state['cart_adds'] += 1
    return added

# ==============================================================================
# PRODUCT PAGE VISIT (core behaviour)
# ==============================================================================

def _visit_product_page(driver, cfg: AmazonSessionConfig,
                        session_state: dict, allow_new_tabs: bool = True):
    """
    Spend 10–200 seconds on a product page doing human-like actions.

    Buckets:
      short  (10–40s):   images only + quick scroll
      medium (40–100s):  images + description
      long   (100–200s): images + description + reviews + maybe new tab

    New-tab browsing: on medium/long stays, 35% chance to open a related
    product in a new tab and browse it before returning.

    Add to cart: attempted after main browsing, respecting session quota.
    """
    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)

    if cfg.stop_event.is_set():
        return

    # Decide stay duration (log-normal, most visits ~55s)
    stay_s = math.exp(random.gauss(math.log(55), 0.65))
    stay_s = max(10.0, min(200.0, stay_s))
    end_t  = time.time() + stay_s

    if stay_s < 40:
        bucket = "short"
    elif stay_s < 100:
        bucket = "medium"
    else:
        bucket = "long"

    # ── Initial page glance ──────────────────────────────────────────
    bot.scroll_page(driver, random.randint(200, 500))
    bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)
    if cfg.stop_event.is_set():
        return

    # ── Images (always) ─────────────────────────────────────────────
    _scroll_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # ── Description (medium+) ───────────────────────────────────────
    if bucket in ("medium", "long") and time.time() < end_t:
        _read_description(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return

    # ── Reviews (long only, if enabled) ─────────────────────────────
    if bucket == "long" and cfg.read_reviews and time.time() < end_t:
        if random.random() < 0.75:
            _read_reviews(driver, cfg.stop_event)
            if cfg.stop_event.is_set():
                return

    # ── Open a related product in a new tab (medium+, 35% chance) ───
    if allow_new_tabs and bucket in ("medium", "long") and time.time() < end_t:
        if random.random() < 0.35:
            _open_related_in_new_tab(driver, cfg.stop_event)
            if cfg.stop_event.is_set():
                return

    # ── Add to cart (respects session quota) ────────────────────────
    if time.time() < end_t and not cfg.stop_event.is_set():
        added = _maybe_add_to_cart(driver, cfg, session_state)

    # ── Fill remaining time with natural scrolling / mouse drift ─────
    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.5:
            break
        roll = random.random()
        if roll < 0.35:
            bot.scroll_page(driver,
                random.choice([1, -1]) * random.randint(100, 380))
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.18)
        elif roll < 0.55:
            bot.idle_mouse_drift(driver, min(remaining * 0.3, 2.5))
        elif roll < 0.68:
            bot.occasional_ctrl_f(driver, chance=1.0, context='amazon')
        else:
            time.sleep(min(remaining, random.uniform(1.0, 4.0)))

# ==============================================================================
# GOOGLE → AMAZON FLOW
# ==============================================================================

def _google_to_amazon(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    Search Google for the query, find an Amazon result, click it.
    Returns True if we landed on an Amazon product or search page.
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

    # Weighted pick — bias toward first result
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

    # Hover a couple results before clicking (natural)
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
# AMAZON SEARCH PAGE → PRODUCT
# ==============================================================================

def _pick_product_from_amazon_search(driver, cfg: AmazonSessionConfig) -> bool:
    """
    If we landed on an Amazon search results page, pick a product and click it.
    Returns True if we navigated to a product page.
    """
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")))
    except TimeoutException:
        return False

    bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)
    bot.scroll_page(driver, random.randint(300, 700))
    bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)

    try:
        products = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-component-type='s-search-result'] h2 a.a-link-normal"
        )
        visible = [p for p in products[:12] if p.is_displayed()]
        if not visible:
            return False

        # Weighted pick
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

        # Hover a few before clicking
        hover_count = random.randint(1, min(3, len(visible)))
        for el in random.sample(visible[:6], hover_count):
            if cfg.stop_event.is_set():
                return False
            bot.mouse_move_to_element(driver, el)
            bot.ln_sleep(random.uniform(0.3, 0.8), 0.18)

        bot.human_click(driver, chosen)
        bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        return True

    except Exception:
        return False

# ==============================================================================
# MAIN SESSION RUNNER
# ==============================================================================

def run_amazon_session(driver, cfg: AmazonSessionConfig):
    """
    Main entry point called from tab_amazon._worker.
    Runs until session_minutes elapsed or stop_event set.
    """
    end_t      = time.time() + cfg.session_minutes * 60
    total_time = cfg.session_minutes * 60

    query_pool = _load_queries_for_categories(cfg.categories, cfg.on_progress)
    if not query_pool:
        return

    # Per-session state
    session_state = {
        'cart_adds':        0,
        'cart_adds_target': random.randint(1, 2),  # 1 or 2 adds this session
    }

    query_idx    = 0
    products_done = 0

    def _progress(text):
        if cfg.on_progress and not cfg.stop_event.is_set():
            elapsed = time.time() - (end_t - total_time)
            pct = min(99, int(elapsed / total_time * 100))
            cfg.on_progress(text, pct)

    _progress("Starting Amazon session…")

    while time.time() < end_t and not cfg.stop_event.is_set():

        # ── Pick next query ──────────────────────────────────────────
        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0

        cat, query = query_pool[query_idx]
        query_idx += 1

        _progress(f"Searching: {query[:55]}")

        # ── Navigate to Amazon via Google ────────────────────────────
        found = _google_to_amazon(driver, query, cfg)
        if cfg.stop_event.is_set():
            break
        if not found:
            bot.ln_sleep(random.uniform(3.0, 7.0), 0.25)
            continue

        # ── If we landed on Amazon search page, pick a product ───────
        if _is_amazon_search_page(driver):
            navigated = _pick_product_from_amazon_search(driver, cfg)
            if cfg.stop_event.is_set():
                break
            if not navigated:
                bot.ln_sleep(random.uniform(2.0, 5.0), 0.22)
                continue

        # ── Visit the product page ───────────────────────────────────
        if _is_amazon_product_page(driver):
            products_done += 1
            _progress(f"Browsing product ({products_done} done)")
            _visit_product_page(driver, cfg, session_state, allow_new_tabs=True)
            if cfg.stop_event.is_set():
                break

            # ── After product: maybe go back and browse a related
            #    product in the SAME tab (no new tab this time)
            if random.random() < 0.40 and time.time() < end_t:
                _progress("Checking related product…")
                # Find a related link and navigate directly (same tab)
                try:
                    selectors = [
                        "#similarities_feature_div a.a-link-normal[href*='/dp/']",
                        "#sp_detail a.a-link-normal[href*='/dp/']",
                        "#anonCarousel1 a[href*='/dp/']",
                        ".p13n-sc-uncoverable-faceout a[href*='/dp/']",
                    ]
                    candidates = []
                    for sel in selectors:
                        found_els = driver.find_elements(By.CSS_SELECTOR, sel)
                        candidates.extend(
                            [f for f in found_els if f.is_displayed()])
                        if candidates:
                            break
                    if candidates:
                        chosen = random.choice(candidates[:6])
                        bot.mouse_move_to_element(driver, chosen)
                        bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)
                        bot.human_click(driver, chosen)
                        bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
                        bot.inject_stealth(driver)
                        bot._reset_mouse(driver)
                        if _is_amazon_product_page(driver):
                            products_done += 1
                            _progress(
                                f"Browsing related product ({products_done} done)")
                            # No new tabs from related product page
                            _visit_product_page(driver, cfg, session_state,
                                                allow_new_tabs=False)
                except Exception:
                    pass

            if cfg.stop_event.is_set():
                break

            # ── Decide: back to Google results OR new query ───────────
            if random.random() < 0.50:
                try:
                    driver.back()
                    bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
                    bot.inject_stealth(driver)
                    bot._reset_mouse(driver)

                    results = bot.get_organic_results(driver, max_results=10)
                    amazon_results = [
                        (t, u) for t, u in results if "amazon.com" in u
                    ]
                    if amazon_results and random.random() < 0.60:
                        _, next_url = random.choice(amazon_results)
                        bot.click_result(driver, next_url)
                        bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
                        bot.inject_stealth(driver)
                        if _is_amazon_product_page(driver):
                            products_done += 1
                            _progress(
                                f"Browsing product ({products_done} done)")
                            _visit_product_page(driver, cfg, session_state,
                                                allow_new_tabs=True)
                except Exception:
                    pass

        # ── Inter-query pause ────────────────────────────────────────
        if not cfg.stop_event.is_set() and time.time() < end_t:
            pause = math.exp(random.gauss(math.log(6.0), 0.40))
            pause = max(2.5, min(18.0, pause))
            time.sleep(pause)

    # ── Session complete ─────────────────────────────────────────────
    cart_info = (f", {session_state['cart_adds']} item"
                 f"{'s' if session_state['cart_adds'] != 1 else ''} added to cart"
                 if session_state['cart_adds'] > 0 else "")
    if cfg.on_progress:
        cfg.on_progress(
            f"Done — {products_done} product"
            f"{'s' if products_done != 1 else ''} visited{cart_info}.",
            100
        )
