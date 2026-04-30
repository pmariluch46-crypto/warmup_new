"""
core/amazon_engine.py  --  Amazon Warm-up session engine.

Flow:
  1. Google search for "[query] site:amazon.com" (or plain query → prefer amazon result)
  2. Click Amazon product result from Google
  3. On product page: spend 10–200s doing human-like interactions
     (the longer the stay, the more actions are performed)
  4. After product: 50% go back → pick next result | 50% search new query
  5. Repeat until session_minutes expires or stop_event is set
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
#  CONFIG DATACLASS
# ==============================================================================

class AmazonSessionConfig:
    def __init__(self, categories, session_minutes, read_reviews,
                 stop_event, on_progress=None):
        self.categories       = categories       # list[str]
        self.session_minutes  = session_minutes  # int
        self.read_reviews     = read_reviews     # bool
        self.stop_event       = stop_event       # threading.Event
        self.on_progress      = on_progress      # callable(text, pct) | None


# ==============================================================================
#  AMAZON QUERY LOADER
# ==============================================================================

def _load_queries_for_categories(categories):
    """
    Load amazon queries from data/amazon_queries.json for selected categories.
    Returns a flat list of (category, query) tuples.
    """
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
#  AMAZON-SPECIFIC PAGE HELPERS
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
        # Scroll to feature bullets
        for sel in ["#feature-bullets", "#productDescription", "#aplus"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", el)
                bot.ln_sleep(random.uniform(0.6, 1.4), 0.20)
                break
            except Exception:
                continue

        # Read bullets
        bullets = driver.find_elements(
            By.CSS_SELECTOR, "#feature-bullets li span.a-list-item")
        visible = [b for b in bullets[:10] if b.is_displayed() and b.text.strip()]
        read_count = random.randint(1, max(1, len(visible)))
        for bullet in visible[:read_count]:
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, bullet)
            bot.ln_sleep(random.uniform(0.8, 2.2), 0.25)

        # Scroll description a bit
        bot.scroll_page(driver, random.randint(200, 500))
        bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    except Exception:
        pass


def _read_reviews(driver, stop_event):
    """Scroll to reviews section and read a few."""
    try:
        # Navigate to reviews section
        for sel in ["#reviewsMedley", "#customer-reviews-content", "#reviews-medley-footer"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", el)
                bot.ln_sleep(random.uniform(1.0, 2.0), 0.22)
                break
            except Exception:
                continue

        # Read individual review cards
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
            # Time proportional to review length
            read_time = min(8.0, len(review.text) / 200.0 + random.uniform(1.0, 3.0))
            bot.ln_sleep(read_time, 0.20)
            # Occasionally scroll a bit while reading
            if random.random() < 0.4:
                bot.scroll_page(driver, random.randint(100, 280))
                bot.ln_sleep(random.uniform(0.4, 1.0), 0.18)

        # Check star rating histogram
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


def _click_related_product(driver, stop_event) -> bool:
    """
    Click a related / sponsored / carousel product.
    Returns True if navigation happened.
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
        bot.mouse_move_to_element(driver, chosen)
        bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)
        bot.human_click(driver, chosen)
        bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        return True
    except Exception:
        return False


# ==============================================================================
#  PRODUCT PAGE VISIT  (core behaviour)
# ==============================================================================

def _visit_product_page(driver, cfg: AmazonSessionConfig):
    """
    Spend 10–200 seconds on a product page.
    The longer the stay, the more actions are performed.
    Short stay  (10–40s):  images only OR quick scroll
    Medium stay (40–100s): images + description
    Long stay  (100–200s): images + description + reviews + maybe related
    """
    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)

    if cfg.stop_event.is_set():
        return

    # Decide how long to spend on this product
    # Use log-normal so most visits are medium length, occasionally very long
    stay_s = math.exp(random.gauss(math.log(55), 0.65))
    stay_s = max(10.0, min(200.0, stay_s))
    end_t  = time.time() + stay_s

    # Bucket: short / medium / long
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

    # ── Images (always, even on short stays) ────────────────────────
    _scroll_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # ── Description (medium+) ───────────────────────────────────────
    if bucket in ("medium", "long") and time.time() < end_t:
        _read_description(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return

    # ── Reviews (long only, and only if enabled) ─────────────────────
    if bucket == "long" and cfg.read_reviews and time.time() < end_t:
        if random.random() < 0.75:
            _read_reviews(driver, cfg.stop_event)
            if cfg.stop_event.is_set():
                return

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
#  GOOGLE → AMAZON FLOW
# ==============================================================================

def _google_to_amazon(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    Search Google for the query, find an Amazon result, click it.
    Returns True if we landed on an Amazon product or search page.
    """
    # Mimic how real users search for Amazon products:
    # most just append "amazon" to their query — exactly like your screenshot shows.
    # Occasionally they search without it and click the Amazon result naturally.
    roll = random.random()
    if roll < 0.60:
        search_q = f"{query} amazon"           # "humster case silent amazon"
    elif roll < 0.85:
        search_q = f"{query} amazon.com"       # slightly more explicit
    else:
        search_q = query                        # natural search, pick amazon result

    bot.google_search(driver, search_q)
    if cfg.stop_event.is_set():
        return False

    bot.check_and_wait_captcha(driver)
    if cfg.stop_event.is_set():
        return False

    # Brief glance at results
    bot.ln_sleep(random.uniform(1.2, 3.0), 0.22)
    bot.scroll_page(driver, random.randint(100, 300))
    bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    # Find amazon.com result
    results = bot.get_organic_results(driver, max_results=10)
    amazon_results = [(t, u) for t, u in results if "amazon.com" in u]

    if not amazon_results:
        # No amazon result found — try clicking first non-google result anyway
        return False

    # Pick one (bias toward first but occasionally pick 2nd/3rd)
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

    # Hover a couple results before clicking (natural behaviour)
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
#  AMAZON SEARCH PAGE → PRODUCT
# ==============================================================================

def _pick_product_from_amazon_search(driver, cfg: AmazonSessionConfig) -> bool:
    """
    If we landed on an Amazon search results page, pick a product and click it.
    Returns True if we navigated to a product page.
    """
    try:
        # Wait for search results
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")))
    except TimeoutException:
        return False

    bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)

    # Scroll a bit to see more results
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

        # Bias toward top results
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
#  MAIN SESSION RUNNER
# ==============================================================================

def run_amazon_session(driver, cfg: AmazonSessionConfig):
    """
    Main entry point called from tab_amazon._worker.
    Runs until session_minutes elapsed or stop_event set.
    """
    end_t        = time.time() + cfg.session_minutes * 60
    query_pool   = _load_queries_for_categories(cfg.categories)
    total_time   = cfg.session_minutes * 60

    if not query_pool:
        if cfg.on_progress:
            cfg.on_progress("No queries found for selected categories.", 0)
        return

    query_idx      = 0
    products_done  = 0
    on_amazon      = False   # True if browser is currently on amazon.com

    def _progress(text):
        if cfg.on_progress and not cfg.stop_event.is_set():
            elapsed  = time.time() - (end_t - total_time)
            pct      = min(99, int(elapsed / total_time * 100))
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
            # Short pause and try next query
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
            _visit_product_page(driver, cfg)
            if cfg.stop_event.is_set():
                break

            # ── After product: maybe click related, then decide next ──
            went_related = False
            if random.random() < 0.40 and time.time() < end_t:
                _progress("Checking related product…")
                went_related = _click_related_product(driver, cfg.stop_event)
                if went_related and _is_amazon_product_page(driver):
                    products_done += 1
                    _progress(f"Browsing related product ({products_done} done)")
                    _visit_product_page(driver, cfg)
                    if cfg.stop_event.is_set():
                        break

            # ── Decide: back to Google results OR new query ───────────
            # 50% go back to previous Google results page
            if random.random() < 0.50 and not went_related:
                try:
                    driver.back()
                    bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
                    bot.inject_stealth(driver)
                    bot._reset_mouse(driver)
                    # Pick another amazon result from the same SERP
                    results = bot.get_organic_results(driver, max_results=10)
                    amazon_results = [
                        (t, u) for t, u in results
                        if "amazon.com" in u
                    ]
                    if amazon_results and random.random() < 0.60:
                        _, next_url = random.choice(amazon_results)
                        bot.click_result(driver, next_url)
                        bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
                        bot.inject_stealth(driver)
                        if _is_amazon_product_page(driver):
                            products_done += 1
                            _progress(f"Browsing product ({products_done} done)")
                            _visit_product_page(driver, cfg)
                except Exception:
                    pass
            # else: loop continues → new query → new Google search

        # ── Inter-query pause ────────────────────────────────────────
        if not cfg.stop_event.is_set() and time.time() < end_t:
            pause = math.exp(random.gauss(math.log(6.0), 0.40))
            pause = max(2.5, min(18.0, pause))
            time.sleep(pause)

    # ── Session complete ─────────────────────────────────────────────
    if cfg.on_progress:
        cfg.on_progress(
            f"Done — {products_done} product{'s' if products_done != 1 else ''} visited.",
            100
        )