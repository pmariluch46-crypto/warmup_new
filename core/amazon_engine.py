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


_IMAGE_THUMB_SELECTORS = [
    "#altImages li.item img",
    "#imageBlock_feature_div li img",
    "#thumbs-image-container img",
    ".imageThumbnail img",
    "[data-csa-c-type='widget'][data-csa-c-slot-id='desktop-image-atf'] img",
    "#imageBlock img.s-image",
]


def _scroll_images(driver, stop_event):
    """
    Randomly browse product images like a real shopper.
    - 30% chance: skip images entirely (not everyone checks them)
    - 70% chance: click 1-4 random thumbnails with natural pauses
    - Sometimes hover over main image without clicking
    - Sometimes zoom into main image (click to enlarge)
    """
    # 30% of the time skip images entirely — not everyone checks them
    if random.random() < 0.30:
        return

    try:
        thumbs = []
        for sel in _IMAGE_THUMB_SELECTORS:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            thumbs = [t for t in found[:10] if t.is_displayed()]
            if thumbs:
                break

        if not thumbs:
            # No thumbnails found — just hover over main image
            try:
                main_img = driver.find_element(By.CSS_SELECTOR,
                    "#imgBlkFront, #landingImage, #main-image, "
                    "#img-canvas img")
                if main_img.is_displayed():
                    bot.mouse_move_to_element(driver, main_img)
                    bot.ln_sleep(random.uniform(1.0, 3.0), 0.22)
            except Exception:
                pass
            return

        # Pick random subset — not sequential, truly random
        max_to_click = min(len(thumbs), 4)
        count   = random.randint(1, max_to_click)
        indices = random.sample(range(len(thumbs)), count)
        # Sort so we don't jump around too erratically
        indices.sort()

        for i, idx in enumerate(indices):
            if stop_event.is_set():
                return

            thumb = thumbs[idx]

            # Sometimes hover without clicking first — deciding whether to click
            bot.mouse_move_to_element(driver, thumb)
            bot.ln_sleep(random.uniform(0.4, 1.2), 0.20)

            # 85% click, 15% just hover and move on
            if random.random() < 0.85:
                bot.human_click(driver, thumb)
                # Pause looking at the enlarged image
                bot.ln_sleep(random.uniform(1.5, 4.5), 0.25)

                # Sometimes move mouse over the main image after clicking thumb
                if random.random() < 0.50:
                    try:
                        main_img = driver.find_element(
                            By.CSS_SELECTOR,
                            "#imgBlkFront, #landingImage, "
                            "#main-image, #img-canvas img")
                        if main_img.is_displayed():
                            bot.mouse_move_to_element(driver, main_img)
                            bot.hover_jitter(
                                driver, random.uniform(0.5, 2.0))
                    except Exception:
                        pass

                # Occasionally click main image to zoom in
                if random.random() < 0.25:
                    try:
                        main_img = driver.find_element(
                            By.CSS_SELECTOR,
                            "#imgBlkFront, #landingImage, #main-image")
                        if main_img.is_displayed():
                            bot.human_click(driver, main_img)
                            bot.ln_sleep(
                                random.uniform(1.5, 3.5), 0.22)
                            # Close zoom by pressing Escape or clicking away
                            import pyautogui
                            pyautogui.press('escape')
                            bot.ln_sleep(random.uniform(0.5, 1.0), 0.20)
                    except Exception:
                        pass
            else:
                # Just looked, moved on
                bot.ln_sleep(random.uniform(0.3, 0.8), 0.20)

    except Exception:
        pass


_DESCRIPTION_SELECTORS = [
    "#feature-bullets",
    "#productDescription",
    "#aplus",
    "#aplus_feature_div",
    "#productDescription_feature_div",
    ".a-section.a-spacing-medium.a-spacing-top-small",
]


def _read_description(driver, stop_event):
    try:
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

        bullets = driver.find_elements(
            By.CSS_SELECTOR, "#feature-bullets li span.a-list-item")
        visible = [b for b in bullets[:12] if b.is_displayed() and b.text.strip()]

        if visible:
            read_count = random.randint(1, max(1, len(visible)))
            for bullet in visible[:read_count]:
                if stop_event.is_set():
                    return
                bot.mouse_move_to_element(driver, bullet)
                bot.reading_pause(len(bullet.text))

        bot.scroll_natural(driver, random.randint(300, 700), stop_event)
        bot.ln_sleep(random.uniform(0.6, 1.8), 0.22)

    except Exception:
        pass


def _click_star_rating_link(driver, stop_event) -> bool:
    """
    Click the star rating / review count link directly under the product
    title — jumps straight to the reviews section on the page.
    Returns True if successfully clicked.
    """
    selectors = [
        "#acrCustomerReviewLink",
        "#averageCustomerReviews a[href*='#customerReviews']",
        "a[href*='#customerReviews']",
        "#reviews-medley-cmps-expand-head",
        "span#acrCustomerReviewText",
        "[data-hook='rating-out-of-text']",
        ".a-link-normal[href*='#reviews']",
    ]
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.is_displayed():
                # Move mouse naturally toward the star rating
                bot.mouse_move_to_element(driver, el)
                # Pause — looking at the star rating before clicking
                bot.ln_sleep(random.uniform(0.8, 2.0), 0.22)
                bot.human_click(driver, el)
                bot.ln_sleep(random.uniform(1.5, 3.0), 0.22)
                return True
        except Exception:
            continue
    return False


def _read_reviews(driver, stop_event):
    """
    Human-like review reading with two entry paths:
    - 40%: click the star rating link under the title (jumps to reviews)
    - 60%: scroll down naturally until reviews section is visible
    Then reads 1-4 individual reviews with natural pauses.
    """
    try:
        arrived_via_click = False

        # ── Entry path ───────────────────────────────────────────
        if random.random() < 0.40:
            # Click star rating link under product title
            arrived_via_click = _click_star_rating_link(driver, stop_event)
            if stop_event.is_set():
                return

        if not arrived_via_click:
            # Scroll down to reviews section naturally
            for sel in [
                "#reviewsMedley",
                "#customer-reviews-content",
                "#cm_cr-review_list",
                "[data-hook='reviews-medley-footer']",
                "#reviews-medley-cmps-expand-head",
            ]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        # Scroll toward reviews in natural steps
                        rect = driver.execute_script(
                            "return arguments[0].getBoundingClientRect();", el)
                        dist = max(0, int(rect['top']))
                        if dist > 100:
                            # Multi-step natural scroll toward reviews
                            steps = random.randint(2, 4)
                            per_step = dist // steps
                            for _ in range(steps):
                                if stop_event.is_set():
                                    return
                                bot.scroll_natural(
                                    driver,
                                    per_step + random.randint(-50, 50),
                                    stop_event)
                                bot.ln_sleep(
                                    random.uniform(0.8, 2.5), 0.22)
                        bot.ln_sleep(random.uniform(1.0, 2.2), 0.22)
                        break
                except Exception:
                    continue

        if stop_event.is_set():
            return

        # ── Look at overall star histogram first ─────────────────
        # Real users almost always check the rating distribution
        if random.random() < 0.70:
            for hist_sel in [
                "#histogramTable",
                ".cr-widget-Histogram",
                "#customer-reviews-overview-tab-review-summary",
                "[data-hook='cr-filter-info-review-rating-count']",
            ]:
                try:
                    hist = driver.find_element(By.CSS_SELECTOR, hist_sel)
                    if hist.is_displayed():
                        bot.mouse_move_to_element(driver, hist)
                        # Pause — studying the rating breakdown
                        bot.ln_sleep(random.uniform(1.5, 3.5), 0.22)

                        # Sometimes click a specific star filter
                        # (e.g. "only 1 star" or "only 5 star")
                        if random.random() < 0.25:
                            try:
                                star_links = driver.find_elements(
                                    By.CSS_SELECTOR,
                                    "#histogramTable tr a, "
                                    ".cr-widget-Histogram a"
                                )
                                star_links = [
                                    s for s in star_links if s.is_displayed()]
                                if star_links:
                                    chosen = random.choice(star_links[:5])
                                    bot.mouse_move_to_element(driver, chosen)
                                    bot.ln_sleep(
                                        random.uniform(0.5, 1.2), 0.20)
                                    bot.human_click(driver, chosen)
                                    bot.ln_sleep(
                                        random.uniform(2.5, 4.0), 0.22)
                                    bot.inject_stealth(driver)
                            except Exception:
                                pass
                        break
                except Exception:
                    continue

        if stop_event.is_set():
            return

        # ── Read individual reviews ───────────────────────────────
        reviews = []
        for sel in [
            "[data-hook='review'] [data-hook='review-body'] span",
            ".review-text-content span",
            "[data-hook='review-collapsed'] span",
            "[data-hook='review-body']",
        ]:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            reviews = [r for r in found
                       if r.is_displayed() and len(r.text.strip()) > 30]
            if reviews:
                break

        if not reviews:
            return

        read_count = random.randint(1, max(1, min(4, len(reviews))))

        for i, review in enumerate(reviews[:read_count]):
            if stop_event.is_set():
                return

            # Scroll review into view naturally
            if not bot._is_in_viewport(driver, review):
                bot.scroll_natural(driver,
                                   random.randint(150, 350), stop_event)
                bot.ln_sleep(random.uniform(0.5, 1.2), 0.20)

            # Move mouse to review text — reading it
            bot.mouse_move_to_element(driver, review)

            # Reading pause — proportional to review length
            bot.reading_pause(len(review.text))

            # Occasionally hover over the reviewer's star rating
            if random.random() < 0.45:
                try:
                    # Find star rating near this review
                    review_container = review.find_element(
                        By.XPATH,
                        "./ancestor::*[contains(@data-hook,'review')]"
                        "[1]"
                    )
                    star_el = review_container.find_element(
                        By.CSS_SELECTOR,
                        "[data-hook='review-star-rating'], "
                        ".review-rating"
                    )
                    if star_el.is_displayed():
                        bot.mouse_move_to_element(driver, star_el)
                        bot.ln_sleep(random.uniform(0.4, 1.0), 0.20)
                except Exception:
                    pass

            # Sometimes scroll a bit between reviews
            if i < read_count - 1 and random.random() < 0.55:
                bot.scroll_natural(driver,
                                   random.randint(80, 220), stop_event)
                bot.ln_sleep(random.uniform(0.6, 1.8), 0.20)

        # ── "See all reviews" click ───────────────────────────────
        # Only ~15% of the time — it's a separate page
        if random.random() < 0.15:
            try:
                for sel in [
                    "[data-hook='see-all-reviews-link-foot']",
                    "[data-hook='see-all-reviews-link-head']",
                    "a[href*='customerReviews']",
                    ".a-link-emphasis[href*='reviews']",
                ]:
                    see_all = driver.find_element(By.CSS_SELECTOR, sel)
                    if see_all.is_displayed():
                        bot.mouse_move_to_element(driver, see_all)
                        bot.ln_sleep(random.uniform(0.6, 1.5), 0.20)
                        bot.human_click(driver, see_all)
                        bot.ln_sleep(random.uniform(3.0, 5.0), 0.22)
                        bot.inject_stealth(driver)

                        # Read a few reviews on the full reviews page
                        bot.scroll_natural(
                            driver,
                            random.randint(300, 700), stop_event)
                        bot.ln_sleep(random.uniform(2.0, 5.0), 0.22)

                        if random.random() < 0.5:
                            bot.scroll_natural(
                                driver,
                                random.randint(200, 500), stop_event)
                            bot.ln_sleep(random.uniform(1.5, 3.5), 0.22)

                        # Go back to product page
                        driver.back()
                        bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
                        bot.inject_stealth(driver)
                        break
            except Exception:
                pass

    except Exception:
        pass


def _click_related_product(driver, stop_event) -> bool:
    try:
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
    Natural scrolling behaviour — reads page top to bottom like a real user.
    """
    bot.inject_stealth(driver)
    _accept_amazon_cookies(driver)
    _dismiss_amazon_popups(driver)

    if cfg.stop_event.is_set():
        return

    stay_s = math.exp(random.gauss(math.log(60), 0.60))
    stay_s = max(18.0, min(210.0, stay_s))
    end_t  = time.time() + stay_s

    # ── Initial page load — pause and look at title/main image ───
    bot.ln_sleep(random.uniform(1.8, 3.5), 0.22)
    bot.idle_mouse_drift(driver, random.uniform(1.0, 2.5))

    if cfg.stop_event.is_set():
        return

    # ── Scroll down naturally reading the page ───────────────────
    # 2-4 scroll steps with reading pauses between each
    scroll_steps = random.randint(2, 4)
    for _ in range(scroll_steps):
        if cfg.stop_event.is_set():
            return
        bot.scroll_natural(driver,
                           random.randint(200, 420), cfg.stop_event)
        bot.ln_sleep(random.uniform(1.5, 4.0), 0.25)

    # Occasionally scroll back up a bit — re-reading something
    if random.random() < 0.35 and not cfg.stop_event.is_set():
        bot.scroll_natural(driver,
                           -random.randint(120, 320), cfg.stop_event)
        bot.ln_sleep(random.uniform(1.0, 2.5), 0.22)

    if cfg.stop_event.is_set():
        return

    # ── Images ──────────────────────────────────────────────────
    _scroll_images(driver, cfg.stop_event)
    if cfg.stop_event.is_set():
        return

    # ── Price check ──────────────────────────────────────────────
    if random.random() < 0.70 and time.time() < end_t:
        try:
            for price_sel in [
                "#priceblock_ourprice", "#priceblock_dealprice",
                ".a-price .a-offscreen", "#apex_desktop_newAccordionRow"
            ]:
                price_el = driver.find_element(By.CSS_SELECTOR, price_sel)
                if price_el.is_displayed():
                    bot.mouse_move_to_element(driver, price_el)
                    bot.ln_sleep(random.uniform(0.5, 1.5), 0.22)
                    break
        except Exception:
            pass

    # ── Description ─────────────────────────────────────────────
    if end_t - time.time() > 20 and random.random() < 0.80:
        _read_description(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return

    # ── Reviews ─────────────────────────────────────────────────
    if end_t - time.time() > 35 and cfg.read_reviews and random.random() < 0.65:
        _read_reviews(driver, cfg.stop_event)
        if cfg.stop_event.is_set():
            return

    # ── Add to cart hover ────────────────────────────────────────
    if random.random() < 0.40 and time.time() < end_t:
        try:
            for cart_sel in [
                "#add-to-cart-button", "#submit.add-to-cart",
                "[name='submit.add-to-cart']"
            ]:
                cart_btn = driver.find_element(By.CSS_SELECTOR, cart_sel)
                if cart_btn.is_displayed():
                    bot.mouse_move_to_element(driver, cart_btn)
                    bot.hover_jitter(driver, random.uniform(0.5, 1.8))
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
        if roll < 0.30:
            direction = random.choice([1, -1])
            bot.scroll_natural(driver,
                               direction * random.randint(150, 400),
                               cfg.stop_event)
        elif roll < 0.44:
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
#  DIRECT AMAZON SEARCH
# ==============================================================================

def _search_on_amazon_directly(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    Go to amazon.com homepage via driver.get(), then type the search
    query ONLY into Amazon's search box — never into the address bar.
    """
    # Use driver.get() for homepage — address bar is only for Google
    driver.get("https://www.amazon.com")
    bot.inject_stealth(driver)
    bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)
    bot._reset_mouse(driver)

    if cfg.stop_event.is_set():
        return False

    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox")))
    except TimeoutException:
        return False

    _accept_amazon_cookies(driver)
    _dismiss_amazon_popups(driver)

    # Brief homepage glance
    bot.ln_sleep(random.uniform(1.2, 3.2), 0.25)
    bot.idle_mouse_drift(driver, random.uniform(0.8, 2.0))

    # Occasionally scroll homepage a little
    if random.random() < 0.25:
        bot.scroll_natural(driver, random.randint(150, 400), cfg.stop_event)
        bot.ln_sleep(random.uniform(0.8, 2.0), 0.25)

    if cfg.stop_event.is_set():
        return False

    # Always type into Amazon's search box
    try:
        search_box = driver.find_element(By.ID, "twotabsearchtextbox")
        bot.human_click(driver, search_box)
        bot.ln_sleep(random.uniform(0.3, 0.8), 0.22)
        bot.human_type(search_box, query)
        bot.ln_sleep(random.uniform(0.3, 0.7), 0.20)

        # Sometimes click search button, sometimes press Enter
        if random.random() < 0.35:
            try:
                search_btn = driver.find_element(
                    By.ID, "nav-search-submit-button")
                bot.human_click(driver, search_btn)
            except Exception:
                pyautogui.press('enter')
        else:
            pyautogui.press('enter')

        bot.ln_sleep(random.uniform(2.5, 4.2), 0.22)
        bot.inject_stealth(driver)
        return True

    except Exception:
        return False


# ==============================================================================
#  GOOGLE → AMAZON FLOW
# ==============================================================================

def _google_to_amazon(driver, query, cfg: AmazonSessionConfig) -> bool:
    """
    Search Google, click Amazon result, then visit the product page.
    """
    roll = random.random()
    if roll < 0.45:
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

    # Natural scroll through results before clicking
    if random.random() < 0.60:
        bot.scroll_natural(driver, random.randint(100, 400), cfg.stop_event)
        bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    results        = bot.get_organic_results(driver, max_results=10)
    amazon_results = [(t, u) for t, u in results if "amazon.com" in u]

    if not amazon_results:
        return False

    # Weighted choice — bias toward top results
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

    # Hover over a couple of non-Amazon results first (scanning)
    other_results = [(t, u) for t, u in results if u != chosen_url]
    hover_count   = random.randint(0, min(2, len(other_results)))
    for _, url in random.sample(other_results[:5], hover_count):
        try:
            for a in driver.find_elements(
                    By.CSS_SELECTOR, "div#search a[jsname][href]"):
                if (a.get_attribute("href") or "") == url and a.is_displayed():
                    bot.mouse_move_to_element(driver, a)
                    bot.ln_sleep(random.uniform(0.3, 1.0), 0.20)
                    break
        except Exception:
            pass

    # Click the Amazon result
    bot.click_result(driver, chosen_url)

    if cfg.stop_event.is_set():
        return False

    bot.inject_stealth(driver)
    bot._reset_mouse(driver)

    # Wait for Amazon page to fully load
    bot.ln_sleep(random.uniform(2.0, 3.5), 0.22)

    # ── KEY FIX: visit product page immediately here ──────────────
    # Don't fall back to the main loop which could mis-detect the page
    if _is_amazon_product_page(driver):
        _visit_product_page(driver, cfg)
    elif _is_amazon_search_page(driver):
        navigated = _pick_product_from_amazon_search(driver, cfg)
        if navigated and _is_amazon_product_page(driver):
            _visit_product_page(driver, cfg)

    return True


# ==============================================================================
#  AMAZON SEARCH PAGE → PRODUCT
# ==============================================================================

def _pick_product_from_amazon_search(driver, cfg: AmazonSessionConfig) -> bool:
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")))
    except TimeoutException:
        return False

    bot.ln_sleep(random.uniform(1.2, 3.0), 0.22)

    # Scroll through results naturally
    bot.scroll_natural(driver, random.randint(300, 800), cfg.stop_event)
    bot.ln_sleep(random.uniform(0.8, 1.8), 0.20)

    # Sometimes scroll back up
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
        weights    = [1.0 / (i + 1) for i in range(len(visible))]
        total_w    = sum(weights)
        r          = random.random() * total_w
        chosen     = visible[0]
        cumulative = 0
        for el, w in zip(visible, weights):
            cumulative += w
            if r <= cumulative:
                chosen = el
                break

        # Hover over a few results before clicking
        hover_pool = [v for v in visible[:8] if v != chosen]
        hover_count = random.randint(1, min(3, len(hover_pool)))
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
    40% go direct to Amazon, 60% via Google.
    Note: _google_to_amazon() handles its own product page visit internally.
    The main loop only handles direct Amazon visits.
    """
    end_t      = time.time() + cfg.session_minutes * 60
    total_time = cfg.session_minutes * 60
    query_pool = _load_queries_for_categories(cfg.categories)

    if not query_pool:
        if cfg.on_progress:
            cfg.on_progress("No queries found for selected categories.", 0)
        return

    query_idx     = 0
    products_done = 0

    def _progress(text):
        if cfg.on_progress and not cfg.stop_event.is_set():
            elapsed = time.time() - (end_t - total_time)
            pct     = min(99, int(elapsed / total_time * 100))
            cfg.on_progress(text, pct)

    _progress("Starting Amazon session…")

    while time.time() < end_t and not cfg.stop_event.is_set():

        # Pick next query
        if query_idx >= len(query_pool):
            random.shuffle(query_pool)
            query_idx = 0

        cat, query = query_pool[query_idx]
        query_idx += 1

        _progress(f"Searching: {query[:55]}")

        use_direct = random.random() < 0.40

        if use_direct:
            # ── Direct Amazon path ────────────────────────────────
            found = _search_on_amazon_directly(driver, query, cfg)

            if cfg.stop_event.is_set():
                break

            if not found:
                bot.ln_sleep(random.uniform(4.0, 9.0), 0.28)
                continue

            # On search results page — pick and visit a product
            if _is_amazon_search_page(driver):
                navigated = _pick_product_from_amazon_search(driver, cfg)
                if cfg.stop_event.is_set():
                    break
                if not navigated:
                    bot.ln_sleep(random.uniform(2.5, 6.0), 0.25)
                    continue

            # Visit product page
            if _is_amazon_product_page(driver):
                products_done += 1
                _progress(
                    f"Browsing product ({products_done} done) — {query[:35]}")
                _visit_product_page(driver, cfg)
                if cfg.stop_event.is_set():
                    break

                # After product: related item or go back
                roll = random.random()
                if roll < 0.35 and time.time() < end_t:
                    _progress("Checking related product…")
                    went = _click_related_product(driver, cfg.stop_event)
                    if went and _is_amazon_product_page(driver):
                        products_done += 1
                        _progress(
                            f"Browsing related ({products_done} done)")
                        _visit_product_page(driver, cfg)

                elif roll < 0.55 and time.time() < end_t:
                    try:
                        driver.back()
                        bot.ln_sleep(random.uniform(2.0, 4.0), 0.25)
                        bot.inject_stealth(driver)
                        bot._reset_mouse(driver)
                        if _is_amazon_search_page(driver):
                            nav = _pick_product_from_amazon_search(driver, cfg)
                            if nav and _is_amazon_product_page(driver):
                                products_done += 1
                                _progress(
                                    f"Browsing next result ({products_done} done)")
                                _visit_product_page(driver, cfg)
                    except Exception:
                        pass

        else:
            # ── Google → Amazon path ──────────────────────────────
            # _google_to_amazon handles product page visit internally
            products_before = products_done
            found = _google_to_amazon(driver, query, cfg)

            if cfg.stop_event.is_set():
                break

            if found:
                products_done += 1
                _progress(
                    f"Browsing product ({products_done} done) — {query[:35]}")

            if not found:
                bot.ln_sleep(random.uniform(4.0, 9.0), 0.28)
                continue

        # Inter-query pause
        if not cfg.stop_event.is_set() and time.time() < end_t:
            pause = math.exp(random.gauss(math.log(10.0), 0.45))
            pause = max(4.0, min(25.0, pause))
            time.sleep(pause)

    if cfg.on_progress:
        cfg.on_progress(
            f"Done — {products_done} product"
            f"{'s' if products_done != 1 else ''} visited.",
            100
        )
