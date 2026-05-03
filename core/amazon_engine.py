"""
core/amazon_engine.py -- Amazon Warm-up session engine.

Flow:
  1. Either go directly to amazon.com and search there (40%)
     OR search Google for the query and click Amazon result (60%)
  2. On product page: spend time doing human-like interactions
  3. After product: browse related items, go back, or pick new query
  4. Repeat until session_minutes expires or stop_event is set
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
#  CONFIG
# ==============================================================================

class AmazonSessionConfig:
    def __init__(self, categories, session_minutes, read_reviews,
                 stop_event, on_progress=None):
        self.categories      = categories
        self.session_minutes = session_minutes
        self.read_reviews    = read_reviews
        self.stop_event      = stop_event
        self.on_progress     = on_progress


# ==============================================================================
#  QUERY LOADER
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
#  PAGE DETECTION
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
        return "amazon.com" in url and ("/s?" in url or "/s/" in url)
    except Exception:
        return False


def _is_amazon_page(driver) -> bool:
    try:
        return "amazon.com" in driver.current_url
    except Exception:
        return False


# ==============================================================================
#  AMAZON PAGE HELPERS
# ==============================================================================

def _accept_amazon_cookies(driver):
    for sel in [
        "#sp-cc-accept", "input[name='accept']",
        "button[data-cel-widget='sp-cc-accept']",
        "#acceptCookies",
        "button[aria-label='Accept cookies']",
    ]:
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            bot.human_click(driver, btn)
            bot.ln_sleep(0.8, 0.20)
            return
        except Exception:
            continue


def _dismiss_amazon_popups(driver):
    """Dismiss sign-in popups, location prompts etc."""
    for sel in [
        "#nav-flyout-ya-signin a.nav-action-signin-button",
        "button[data-action-type='DISMISS']",
        ".a-popover-footer .a-button-primary",
        "#a-popover-content button.a-button-close",
    ]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed():
                bot.human_click(driver, btn)
                bot.ln_sleep(0.6, 0.20)
                return
        except Exception:
            continue


# FIX: Robust image thumbnail selectors — Amazon changes these frequently
_IMAGE_THUMB_SELECTORS = [
    "#altImages li.item img",
    "#imageBlock_feature_div li img",
    "#thumbs-image-container img",
    ".imageThumbnail img",
    "[data-csa-c-type='widget'][data-csa-c-slot-id='desktop-image-atf'] img",
    "#imageBlock img.s-image",
]


def _scroll_images(driver, stop_event):
    """Cycle through product image thumbnails like a real shopper."""
    try:
        thumbs = []
        for sel in _IMAGE_THUMB_SELECTORS:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            thumbs = [t for t in found[:10] if t.is_displayed()]
            if thumbs:
                break

        if not thumbs:
            return

        count = random.randint(2, min(len(thumbs), 5))
        indices = random.sample(range(len(thumbs)), count)
        # FIX: click in a somewhat sequential order (not random jumps)
        indices.sort()

        for idx in indices:
            if stop_event.is_set():
                return
            thumb = thumbs[idx]
            bot.mouse_move_to_element(driver, thumb)
            # FIX: pause and look at each thumbnail before clicking
            bot.ln_sleep(random.uniform(0.5, 1.5), 0.22)
            bot.human_click(driver, thumb)
            # FIX: actually spend time looking at the large image
            bot.ln_sleep(random.uniform(1.2, 3.5), 0.25)

        # FIX: sometimes zoom into the main image
        if random.random() < 0.35:
            try:
                main_img = driver.find_element(By.CSS_SELECTOR,
                    "#imgBlkFront, #landingImage, #main-image")
                if main_img.is_displayed():
                    bot.mouse_move_to_element(driver, main_img)
                    bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)
            except Exception:
                pass

    except Exception:
        pass


# FIX: More robust description reading with multiple fallback selectors
_DESCRIPTION_SELECTORS = [
    "#feature-bullets",
    "#productDescription",
    "#aplus",
    "#aplus_feature_div",
    "#productDescription_feature_div",
    ".a-section.a-spacing-medium.a-spacing-top-small",
]


def _read_description(driver, stop_event):
    """Scroll through and read product description / feature bullets."""
    try:
        # Find description section
        desc_el = None
        for sel in _DESCRIPTION_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    desc_el = el
                    break
            except Exception:
                continue

        if desc_el:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", desc_el)
            bot.ln_sleep(random.uniform(0.8, 1.8), 0.22)

        # Read bullets
        bullets = driver.find_elements(
            By.CSS_SELECTOR, "#feature-bullets li span.a-list-item")
        visible = [b for b in bullets[:12] if b.is_displayed() and b.text.strip()]

        if visible:
            read_count = random.randint(1, max(1, len(visible)))
            for bullet in visible[:read_count]:
                if stop_event.is_set():
                    return
                bot.mouse_move_to_element(driver, bullet)
                # FIX: reading time proportional to bullet text length
                bot.reading_pause(len(bullet.text))

        # FIX: natural multi-step scroll through description
        scroll_amount = random.randint(300, 700)
        bot.scroll_natural(driver, scroll_amount, stop_event)
        bot.ln_sleep(random.uniform(0.6, 1.8), 0.22)

    except Exception:
        pass


def _read_reviews(driver, stop_event):
    """Scroll to reviews section and read a few."""
    try:
        # FIX: more reliable selectors for reviews section
        review_selectors = [
            "#reviewsMedley",
            "#customer-reviews-content",
            "#reviews-medley-footer",
            "#cm_cr-review_list",
            "[data-hook='reviews-medley-footer']",
        ]

        for sel in review_selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el)
                    bot.ln_sleep(random.uniform(1.2, 2.5), 0.22)
                    break
            except Exception:
                continue

        # FIX: Check overall star rating histogram first (natural user behaviour)
        if random.random() < 0.55:
            try:
                for hist_sel in ["#histogramTable", ".cr-widget-Histogram",
                                 "#customer-reviews-overview-tab-review-summary"]:
                    hist = driver.find_element(By.CSS_SELECTOR, hist_sel)
                    if hist.is_displayed():
                        bot.mouse_move_to_element(driver, hist)
                        bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)
                        break
            except Exception:
                pass

        # Read individual reviews
        review_selectors_text = [
            "[data-hook='review'] [data-hook='review-body'] span",
            ".review-text-content span",
            "[data-hook='review-collapsed'] span",
        ]
        reviews = []
        for sel in review_selectors_text:
            reviews = driver.find_elements(By.CSS_SELECTOR, sel)
            reviews = [r for r in reviews if r.is_displayed() and len(r.text.strip()) > 30]
            if reviews:
                break

        read_count = random.randint(1, max(1, min(3, len(reviews))))
        for review in reviews[:read_count]:
            if stop_event.is_set():
                return
            bot.mouse_move_to_element(driver, review)
            bot.reading_pause(len(review.text))

            if random.random() < 0.4:
                bot.scroll_natural(driver, random.randint(100, 280), stop_event)
                bot.ln_sleep(random.uniform(0.4, 1.0), 0.18)

        # FIX: occasionally click "See all reviews"
        if random.random() < 0.20:
            try:
                for sel in ["[data-hook='see-all-reviews-link-foot']",
                            "a[href*='#reviews']",
                            ".a-link-emphasis[href*='customerReviews']"]:
                    see_all = driver.find_element(By.CSS_SELECTOR, sel)
                    if see_all.is_displayed():
                        bot.mouse_move_to_element(driver, see_all)
                        bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)
                        bot.human_click(driver, see_all)
                        bot.ln_sleep(random.uniform(3.0, 5.0), 0.22)
                        bot.inject_stealth(driver)
                        # Scroll a few reviews on the full reviews page
                        bot.scroll_natural(driver, random.randint(400, 900), stop_event)
                        bot.ln_sleep(random.uniform(1.5, 3.5), 0.22)
                        driver.back()
                        bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
                        bot.inject_stealth(driver)
                        break
            except Exception:
                pass

    except Exception:
        pass


def _click_related_product(driver, stop_event) -> bool:
    """Click a related / sponsored / carousel product."""
    try:
        # FIX: expanded and more up-to-date selectors
        selectors = [
            "#similarities_feature_div a.a-link-normal[href*='/dp/']",
            "#sp_detail a.a-link-normal[href*='/dp/']",
            "#anonCarousel1 a[href*='/dp/']",
            "#anonCarousel2 a[href*='/dp/']",
            ".p13n-sc-uncoverable-faceout a[href*='/dp/']",
            "[data-component-type='s-product-image'] a[href*='/dp/']",
            "#purchase-sims-feature a[href*='/dp/']",
            "#session-sims-feature a[href*='/dp/']",
            "[data-feature-name='similarities'] a[href*='/dp/']",
            ".a-carousel-card a[href*='/dp/']",
        ]

        candidates = []
        for sel in selectors:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            new = [f for f in found if f.is_displayed() and f not in candidates]
            candidates.extend(new)
            if len(candidates) >= 6:
                break

        if not candidates:
            return False

        # FIX: hover over a few before choosing, like window shopping
        preview_count = min(random.randint(1, 3), len(candidates))
        for el in random.sample(candidates[:6], preview_count):
            if stop_event.is_set():
                return False
            bot.mouse_move_to_element(driver, el)
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)

        chosen = random.choice(candidates[:6])
        bot.human_click(driver, chosen)
        bot.ln_sleep(random.uniform(2.8, 4.5), 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        return True

    except Exception:
        return False


# ==============================================================================
#  PRODUCT PAGE VISIT
# ==============================================================================

def _visit_product_page(driver, cfg: AmazonSessionConfig):
    """
    Spend time on a product page doing human-like interactions.
    FIX: removed hard bucket cutoffs, behavior now flows naturally
    based on available time and random decisions.
    """
    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)
    _dismiss_amazon_popups(driver)

    if cfg.stop_event.is_set():
        return

    # FIX: log-normal stay time, but now drives probability of each action
    # rather than hard bucket cutoffs
    stay_s = math.exp(random.gauss(math.log(60), 0.60))
    stay_s = max(12.0, min(210.0, stay_s))
    end_t = time.time() + stay_s

    # ── Initial page glance ─────────────────────────────────────
    # FIX: scroll a variable amount, not always the same range
    bot.scroll_natural(driver, random.randint(150, 450), cfg.stop_event)
    bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)

    if cfg.stop_event.is_set():
        return

    # ── Images ──────────────────────────────────────────────────
    _scroll_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # ── Price / availability check (quick hover) ─────────────────
    if random.random() < 0.70 and time.time() < end_t:
        try:
            for price_sel in ["#priceblock_ourprice", "#priceblock_dealprice",
                               ".a-price .a-offscreen", "#apex_desktop_newAccordionRow"]:
                price_el = driver.find_element(By.CSS_SELECTOR, price_sel)
                if price_el.is_displayed():
                    bot.mouse_move_to_element(driver, price_el)
                    bot.ln_sleep(random.uniform(0.5, 1.5), 0.22)
                    break
        except Exception:
            pass

    # ── Description ─────────────────────────────────────────────
    time_left = end_t - time.time()
    if time_left > 20 and random.random() < 0.80:
        _read_description(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return

    # ── Reviews ─────────────────────────────────────────────────
    time_left = end_t - time.time()
    if time_left > 35 and cfg.read_reviews and random.random() < 0.65:
        _read_reviews(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return

    # ── Add to cart hover (doesn't actually add — just hovers) ───
    if random.random() < 0.40 and time.time() < end_t:
        try:
            for cart_sel in ["#add-to-cart-button", "#submit.add-to-cart",
                             "[name='submit.add-to-cart']"]:
                cart_btn = driver.find_element(By.CSS_SELECTOR, cart_sel)
                if cart_btn.is_displayed():
                    bot.mouse_move_to_element(driver, cart_btn)
                    bot.hover_jitter(driver, random.uniform(0.5, 1.8))
                    # FIX: don't actually click — just look at it
                    bot.ln_sleep(random.uniform(0.8, 2.0), 0.22)
                    break
        except Exception:
            pass

    # ── Fill remaining time naturally ────────────────────────────
    while time.time() < end_t and not cfg.stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.5:
            break

        roll = random.random()

        if roll < 0.28:
            # Natural scroll (up or down)
            direction = random.choice([1, -1])
            bot.scroll_natural(driver, direction * random.randint(150, 400),
                               cfg.stop_event)
        elif roll < 0.42:
            bot.idle_mouse_drift(driver, min(remaining * 0.3, 3.0))
        elif roll < 0.54:
            bot.occasional_ctrl_f(driver, chance=1.0, context='amazon')
        elif roll < 0.62:
            bot.occasional_zoom(driver, chance=1.0)
        elif roll < 0.68:
            bot.hover_image_area(driver, cfg.stop_event)
        elif roll < 0.73:
            bot.occasional_right_click(driver, chance=1.0)
        elif roll < 0.78:
            bot.occasional_tab_switch(driver, chance=1.0)
        else:
            time.sleep(min(remaining, random.uniform(1.2, 5.0)))


# ==============================================================================
#  DIRECT AMAZON SEARCH (new natural flow)
# ==============================================================================

def _search_on_amazon_directly(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    FIX: Go directly to amazon.com and search there.
    This is how ~40% of real shoppers behave — they bookmark Amazon
    and search directly, not via Google.
    """
    # Navigate to Amazon homepage via driver.get —
    # address bar is reserved for Google searches only
    driver.get("https://www.amazon.com")
    bot.inject_stealth(driver)
    bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
    bot._reset_mouse(driver)

    if cfg.stop_event.is_set():
        return False

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox")))
    except TimeoutException:
        return False

    _accept_amazon_cookies(driver)
    _dismiss_amazon_popups(driver)

    # FIX: brief homepage glance before searching (natural)
    bot.ln_sleep(random.uniform(1.0, 3.0), 0.25)
    bot.idle_mouse_drift(driver, random.uniform(1.0, 2.5))

    # Optional: browse homepage a little (30% of Amazon-direct visits)
    if random.random() < 0.30:
        bot.scroll_natural(driver, random.randint(200, 500), cfg.stop_event)
        bot.ln_sleep(random.uniform(1.0, 2.5), 0.25)

    # Type in Amazon's search box
    try:
        search_box = driver.find_element(By.ID, "twotabsearchtextbox")
        bot.human_click(driver, search_box)
        bot.ln_sleep(random.uniform(0.3, 0.8), 0.22)
        bot.human_type(search_box, query)
        bot.ln_sleep(random.uniform(0.3, 0.7), 0.20)

        # FIX: sometimes use the search button, sometimes press Enter
        if random.random() < 0.35:
            try:
                search_btn = driver.find_element(By.ID, "nav-search-submit-button")
                bot.human_click(driver, search_btn)
            except Exception:
                pyautogui.press('enter')
        else:
            pyautogui.press('enter')

        bot.ln_sleep(random.uniform(2.5, 4.0), 0.22)
        bot.inject_stealth(driver)
        return True

    except Exception:
        return False


# ==============================================================================
#  GOOGLE → AMAZON FLOW
# ==============================================================================

def _google_to_amazon(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    Search Google for the query, find an Amazon result, click it.
    FIX: more varied and natural search query patterns.
    """
    roll = random.random()
    if roll < 0.45:
        # Most natural: plain product search, click Amazon result
        search_q = query
    elif roll < 0.65:
        search_q = f"{query} amazon"
    elif roll < 0.80:
        search_q = f"buy {query}"
    elif roll < 0.90:
        search_q = f"{query} review"
    else:
        search_q = f"best {query}"

    bot.google_search(driver, search_q)

    if cfg.stop_event.is_set():
        return False

    bot.check_and_wait_captcha(driver)
    if cfg.stop_event.is_set():
        return False

    bot.ln_sleep(random.uniform(1.5, 3.5), 0.22)

    # FIX: natural scroll through results before clicking
    if random.random() < 0.60:
        bot.scroll_natural(driver, random.randint(100, 400), cfg.stop_event)
        bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    results = bot.get_organic_results(driver, max_results=10)
    amazon_results = [(t, u) for t, u in results if "amazon.com" in u]

    if not amazon_results:
        return False

    # Weighted choice — bias toward top results
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

    # FIX: hover over non-amazon results too before clicking (scanning behaviour)
    all_results = [(t, u) for t, u in results if u != chosen_url]
    hover_count = random.randint(0, min(2, len(all_results)))
    for title, url in random.sample(all_results[:5], hover_count):
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "div#search a[jsname][href]")
            for a in els:
                if (a.get_attribute("href") or "") == url and a.is_displayed():
                    bot.mouse_move_to_element(driver, a)
                    bot.ln_sleep(random.uniform(0.3, 1.0), 0.20)
                    break
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
    """Pick a product from Amazon search results page."""
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")))
    except TimeoutException:
        return False

    bot.ln_sleep(random.uniform(1.2, 3.0), 0.22)

    # FIX: scroll through results naturally, not a single big scroll
    bot.scroll_natural(driver, random.randint(300, 800), cfg.stop_event)
    bot.ln_sleep(random.uniform(0.8, 1.8), 0.20)

    # FIX: sometimes scroll back up a bit (re-reading results)
    if random.random() < 0.30:
        bot.scroll_natural(driver, -random.randint(100, 300), cfg.stop_event)
        bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)

    try:
        products = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-component-type='s-search-result'] h2 a.a-link-normal"
        )
        visible = [p for p in products[:15] if p.is_displayed()]
        if not visible:
            return False

        # Weighted choice
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

        # FIX: hover over more results before clicking
        hover_count = random.randint(1, min(4, len(visible)))
        hover_pool = [v for v in visible[:8] if v != chosen]
        for el in random.sample(hover_pool, min(hover_count, len(hover_pool))):
            if cfg.stop_event.is_set():
                return False
            bot.mouse_move_to_element(driver, el)
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)

        bot.human_click(driver, chosen)
        bot.ln_sleep(random.uniform(2.8, 4.5), 0.22)
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
    Main entry point. Runs until session_minutes elapsed or stop_event set.
    FIX: Mixed entry strategy — 40% go direct to Amazon, 60% via Google.
    """
    end_t = time.time() + cfg.session_minutes * 60
    total_time = cfg.session_minutes * 60
    query_pool = _load_queries_for_categories(cfg.categories)

    if not query_pool:
        if cfg.on_progress:
            cfg.on_progress("No queries found for selected categories.", 0)
        return

    query_idx = 0
    products_done = 0

    def _progress(text):
        if cfg.on_progress and not cfg.stop_event.is_set():
            elapsed = time.time() - (end_t - total_time)
            pct = min(99, int(elapsed / total_time * 100))
            cfg.on_progress(text, pct)

    _progress("Starting Amazon session…")

    while time.time() < end_t and not cfg.stop_event.is_set():

        # ── Pick next query ─────────────────────────────────────
        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0

        cat, query = query_pool[query_idx]
        query_idx += 1

        _progress(f"Searching: {query[:55]}")

        # ── FIX: decide entry path per query, not per session ───
        use_direct = random.random() < 0.40  # 40% go straight to Amazon

        if use_direct:
            found = _search_on_amazon_directly(driver, query, cfg)
        else:
            found = _google_to_amazon(driver, query, cfg)

        if cfg.stop_event.is_set():
            break

        if not found:
            bot.ln_sleep(random.uniform(4.0, 9.0), 0.28)
            continue

        # ── If on Amazon search page, pick a product ─────────────
        if _is_amazon_search_page(driver):
            navigated = _pick_product_from_amazon_search(driver, cfg)
            if cfg.stop_event.is_set():
                break
            if not navigated:
                bot.ln_sleep(random.uniform(2.5, 6.0), 0.25)
                continue

        # ── Visit the product page ───────────────────────────────
        if _is_amazon_product_page(driver):
            products_done += 1
            _progress(f"Browsing product ({products_done} done) — {query[:35]}")
            _visit_product_page(driver, cfg)
            if cfg.stop_event.is_set():
                break

            # ── FIX: after product, pick one of several natural actions ──
            roll = random.random()

            if roll < 0.35 and time.time() < end_t:
                # Browse a related product
                _progress("Checking related product…")
                went_related = _click_related_product(driver, cfg.stop_event)
                if went_related and _is_amazon_product_page(driver):
                    products_done += 1
                    _progress(f"Browsing related ({products_done} done)")
                    _visit_product_page(driver, cfg)
                    if cfg.stop_event.is_set():
                        break

            elif roll < 0.55 and time.time() < end_t:
                # Go back to search/Google results and pick another result
                try:
                    driver.back()
                    bot.ln_sleep(random.uniform(2.0, 4.0), 0.25)
                    bot.inject_stealth(driver)
                    bot._reset_mouse(driver)

                    if _is_amazon_search_page(driver):
                        # Back on Amazon search — pick another product
                        navigated = _pick_product_from_amazon_search(driver, cfg)
                        if navigated and _is_amazon_product_page(driver):
                            products_done += 1
                            _progress(f"Browsing next result ({products_done} done)")
                            _visit_product_page(driver, cfg)
                    else:
                        # Back on Google — maybe click another Amazon result
                        results = bot.get_organic_results(driver, max_results=10)
                        amazon_results = [
                            (t, u) for t, u in results if "amazon.com" in u
                        ]
                        if amazon_results and random.random() < 0.65:
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

            # else: roll >= 0.55 — just move on to next query naturally

        # ── Inter-query pause ─────────────────────────────────────
        # FIX: longer and more variable pauses between queries
        if not cfg.stop_event.is_set() and time.time() < end_t:
            pause = math.exp(random.gauss(math.log(10.0), 0.45))
            pause = max(4.0, min(25.0, pause))
            time.sleep(pause)

    # ── Session complete ──────────────────────────────────────────
    if cfg.on_progress:
        cfg.on_progress(
            f"Done — {products_done} product{'s' if products_done != 1 else ''} visited.",
            100
        )
