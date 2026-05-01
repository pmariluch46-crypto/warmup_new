"""
core/warm_up_engine.py  --  Phase execution engine for WarmUpPro.

Each category maps to a phase function.
All phase functions accept (driver, query, stop_event, read_speed) and return bool (success).

Browse pattern (all non-YouTube phases):
  1. Google search once
  2. Brief results glance (1-3s) + scroll
  3. For 300-400s: click organic result → visit site (2-level) → back×2 to Google
     → brief pause → click next result — never search again during this window
  4. Phase ends when the 300-400s window expires
"""

import time
import math
import random
import pyautogui
from urllib.parse import urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core import browser_bot as bot
from core.adaptive_scroll import (
    adaptive_browse_deep,
    adaptive_read_page,
    reset_session_fatigue,
)


# Sites preferred per category
_NEWS_SITES     = ["apnews.com", "reuters.com", "bbc.com", "cnn.com", "nbcnews.com",
                   "foxnews.com", "npr.org", "theguardian.com", "usatoday.com", "cbsnews.com"]
_WEATHER_SITES  = ["weather.com", "accuweather.com", "wunderground.com",
                   "weather.gov", "weatherbug.com"]
_RECIPE_SITES   = ["allrecipes.com", "foodnetwork.com", "seriouseats.com",
                   "bonappetit.com", "delish.com", "tasteofhome.com", "epicurious.com"]
_HEALTH_SITES   = ["healthline.com", "webmd.com", "medicalnewstoday.com",
                   "mayoclinic.org", "verywellhealth.com", "health.com"]
_TRAVEL_SITES   = ["tripadvisor.com", "lonelyplanet.com", "travelandleisure.com",
                   "timeout.com", "frommers.com", "fodors.com"]
_SHOPPING_SITES = ["ebay.com", "bestbuy.com", "target.com", "walmart.com",
                   "etsy.com", "newegg.com", "bhphotovideo.com"]
_TECH_SITES     = ["theverge.com", "techcrunch.com", "arstechnica.com",
                   "pcmag.com", "tomsguide.com", "digitaltrends.com", "cnet.com"]
_FINANCE_SITES  = ["investopedia.com", "nerdwallet.com", "bankrate.com",
                   "fool.com", "cnbc.com", "marketwatch.com"]
_REDDIT_DOMAIN  = "reddit.com"
_WIKI_DOMAIN    = "wikipedia.org"
_SKIP_DOMAINS   = ["google.com"]


# ==============================================================================
#  SHARED HELPERS
# ==============================================================================

def _read_page(driver, min_secs, max_secs, read_speed, stop_event):
    adaptive_read_page(bot, driver, min_secs, max_secs, read_speed, stop_event)


def _hover_links(driver, count=3):
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        visible = [l for l in links[:80]
                   if l.is_displayed() and l.text.strip() and
                   driver.execute_script(
                       "var r=arguments[0].getBoundingClientRect();"
                       "return r.top>=0&&r.top<window.innerHeight&&r.width>0;", l)]
        chosen = random.sample(visible, min(count, len(visible)))
        for l in chosen:
            bot.mouse_move_to_element(driver, l)
            bot.hover_jitter(driver, random.uniform(0.3, 1.2))
    except Exception:
        pass


def _distraction(driver, min_s=4, max_s=12, stop_event=None):
    dur = math.exp(random.gauss(math.log((min_s + max_s) / 2), 0.28))
    dur = max(min_s, min(max_s * 1.5, dur))
    end_t = time.time() + dur
    while time.time() < end_t:
        if stop_event and stop_event.is_set():
            return
        chunk = min(end_t - time.time(), 1.0)
        if chunk <= 0:
            break
        if random.random() < 0.4:
            bot.idle_mouse_drift(driver, chunk * 0.5)
        else:
            time.sleep(chunk)


def _accept_cookies(driver):
    accept_texts = [
        "Accept all", "Accept All", "Accept All Cookies", "Allow all", "Allow All",
        "I agree", "I Accept", "Agree", "OK", "Ok", "Got it", "Got It",
        "Continue", "Consent", "Confirm", "That's fine", "Yes", "Understood",
        "Reject all", "Decline", "Close", "Dismiss",
    ]
    css_selectors = [
        "#onetrust-accept-btn-handler", ".onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyButtonAccept",
        "#truste-consent-button",
        "[id*='cookie'] button[class*='accept']",
        "[id*='consent'] button[class*='accept']",
        "[class*='cookie'] button[class*='accept']",
        "[aria-label*='Accept']", "[data-testid*='accept']",
    ]
    for sel in css_selectors:
        try:
            btn = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            bot.human_click(driver, btn)
            bot.ln_sleep(0.6, 0.25)
            return True
        except Exception:
            continue
    for text in accept_texts:
        try:
            btn = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f'//button[normalize-space()="{text}"]')))
            bot.human_click(driver, btn)
            bot.ln_sleep(0.6, 0.25)
            return True
        except Exception:
            continue
    try:
        iframes = driver.find_elements(By.CSS_SELECTOR,
            "iframe[id*='consent'],iframe[id*='cookie'],iframe[src*='consent']")
        for iframe in iframes[:2]:
            try:
                driver.switch_to.frame(iframe)
                for text in accept_texts[:8]:
                    try:
                        btn = WebDriverWait(driver, 1).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, f'//button[normalize-space()="{text}"]')))
                        bot.human_click(driver, btn)
                        driver.switch_to.default_content()
                        bot.ln_sleep(0.6, 0.25)
                        return True
                    except Exception:
                        continue
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
    except Exception:
        pass
    return False


def _safe_click_organic(driver, preferred_sites=None, skip_domains=None):
    blocked = (skip_domains or []) + _SKIP_DOMAINS
    results = bot.get_organic_results(driver, max_results=10)
    if preferred_sites:
        for title, url in results:
            if any(d in url for d in preferred_sites) and not any(d in url for d in blocked):
                bot.click_result(driver, url)
                return title, url
    for title, url in results:
        if not any(d in url for d in blocked):
            bot.click_result(driver, url)
            return title, url
    return None, None


# ==============================================================================
#  NAVIGATION HELPERS
# ==============================================================================

def _click_back_button(driver):
    """Click the browser ← back button via pyautogui (isTrusted=true)."""
    try:
        info = driver.execute_script("""return {
            wx: window.screenX, wy: window.screenY,
            outerH: window.outerHeight, innerH: window.innerHeight
        };""")
        chrome_h = info['outerH'] - info['innerH']
        bx = info['wx'] + 72
        by = info['wy'] + max(28, int(chrome_h * 0.55))
        bx = max(5, min(bx, pyautogui.size()[0] - 5))
        by = max(5, min(by, pyautogui.size()[1] - 5))
        pyautogui.moveTo(bx, by, duration=random.uniform(0.20, 0.45))
        bot.ln_sleep(0.10, 0.12)
        pyautogui.hotkey('alt', 'left')
        bot.ln_sleep(2.0, 0.25)
        bot._reset_mouse(driver)
    except Exception:
        try:
            pyautogui.hotkey('alt', 'left')
            bot.ln_sleep(2.0, 0.25)
        except Exception:
            pass


def _quick_browse_landing(driver, stop_event):
    """2–5s on the landing page: meaningful initial scroll + hover links."""
    bot.scroll_page(driver, random.randint(300, 650))
    bot.ln_sleep(random.uniform(0.4, 1.0), 0.20)

    end_t = time.time() + random.uniform(1.5, 4.0)
    while time.time() < end_t and not stop_event.is_set():
        remaining = end_t - time.time()
        if remaining < 0.2:
            break
        roll = random.random()
        if roll < 0.52:
            bot.scroll_page(driver, random.randint(200, 520))
        elif roll < 0.74:
            _hover_links(driver, random.randint(1, 2))
        else:
            time.sleep(min(remaining, random.uniform(0.3, 1.0)))


def _browse_deep_page(driver, stop_event, read_speed=1.0):
    """Адаптивное глубокое чтение страницы."""
    adaptive_browse_deep(bot, driver, stop_event, read_speed)


def _click_internal_link(driver) -> bool:
    """
    Find and click a visible same-domain content link on the current page.
    Tries content areas first (main/article), falls back to full page.
    Returns True if a link was clicked.
    """
    try:
        current = driver.current_url
        host = urlparse(current).netloc

        candidates = []
        for container_sel in [
            'main a[href]', 'article a[href]',
            '#content a[href]', '.content a[href]',
            '.post a[href]', '.entry-content a[href]',
            'a[href]',
        ]:
            links = driver.find_elements(By.CSS_SELECTOR, container_sel)
            for l in links[:80]:
                try:
                    if not l.is_displayed():
                        continue
                    href = l.get_attribute('href') or ''
                    text = l.text.strip()
                    if not text or len(text) < 4 or len(text) > 100:
                        continue
                    if not href or href == current:
                        continue
                    if href.startswith('javascript') or href.startswith('mailto'):
                        continue
                    if '#' in href:
                        continue
                    link_host = urlparse(href).netloc
                    if host and link_host and link_host != host:
                        continue
                    path = urlparse(href).path.lower()
                    if any(path.endswith(ext) for ext in
                           ['.pdf', '.jpg', '.jpeg', '.png', '.zip', '.mp4', '.exe']):
                        continue
                    candidates.append(l)
                except Exception:
                    pass
            if candidates:
                break

        if not candidates:
            return False

        chosen = random.choice(candidates[:12])
        bot.mouse_move_to_element(driver, chosen)
        bot.ln_sleep(random.uniform(0.4, 0.9), 0.20)
        bot.human_click(driver, chosen)
        bot.ln_sleep(2.2, 0.25)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        return True
    except Exception:
        return False


def _visit_site(driver, stop_event):
    """
    Full 2-level site visit after landing from a Google result:
      1. Accept cookies
      2. 2-5s browse on landing page (scroll + hover)
      3. 70% chance: click internal link → deep browse → back
      4. Browser back button → Google results
    """
    bot.inject_stealth(driver)
    _accept_cookies(driver)
    if stop_event.is_set():
        return

    _quick_browse_landing(driver, stop_event)
    if stop_event.is_set():
        return

    went_deep = False
    if random.random() < 0.70:
        went_deep = _click_internal_link(driver)

    if went_deep and not stop_event.is_set():
        _browse_deep_page(driver, stop_event)
        if not stop_event.is_set():
            _click_back_button(driver)

    if not stop_event.is_set():
        _click_back_button(driver)


# ==============================================================================
#  SEARCH CYCLE ENGINE  (used by all non-YouTube phases)
# ==============================================================================

def _run_search_cycle(driver, query, stop_event, read_speed=0.7, preferred_sites=None):
    bot.google_search(driver, query)
    if stop_event.is_set():
        return False

    bot.check_and_wait_captcha(driver)
    if stop_event.is_set():
        return False

    bot.ln_sleep(random.uniform(1.5, 3.5), 0.22)
    _hover_links(driver, random.randint(2, 3))
    bot.scroll_page(driver, random.randint(120, 300))
    bot.ln_sleep(random.uniform(0.8, 2.0), 0.20)
    if stop_event.is_set():
        return False

    cycle_end    = time.time() + random.uniform(300, 400)
    skip_domains = list(_SKIP_DOMAINS)

    while time.time() < cycle_end and not stop_event.is_set():
        title, url = _safe_click_organic(
            driver, preferred_sites=preferred_sites, skip_domains=skip_domains)

        if not url:
            remaining = cycle_end - time.time()
            if remaining > 5:
                time.sleep(min(remaining, random.uniform(15, 40)))
            break

        try:
            domain = urlparse(url).netloc
            if domain:
                skip_domains.append(domain)
        except Exception:
            skip_domains.append(url)

        _visit_site(driver, stop_event)
        if stop_event.is_set():
            break

        if time.time() < cycle_end and not stop_event.is_set():
            bot.ln_sleep(random.uniform(1.5, 3.5), 0.25)
            _hover_links(driver, random.randint(1, 3))
            if random.random() < 0.55:
                bot.scroll_page(driver,
                                random.choice([1, -1]) * random.randint(80, 250))
                bot.ln_sleep(random.uniform(0.5, 1.5), 0.20)

    return True


# ==============================================================================
#  PHASE FUNCTIONS
# ==============================================================================

def phase_news(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _NEWS_SITES)


def phase_weather(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _WEATHER_SITES)


def phase_reddit(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, [_REDDIT_DOMAIN])


def phase_wikipedia(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, [_WIKI_DOMAIN])


def phase_shopping(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _SHOPPING_SITES)


def phase_food_recipes(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _RECIPE_SITES)


def phase_health(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _HEALTH_SITES)


def phase_travel(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _TRAVEL_SITES)


def phase_technology(driver, query, stop_event, read_speed=0.7):
    return _run_search_cycle(driver, query, stop_event, read_speed, _TECH_SITES)


def phase_youtube(driver, query, stop_event, read_speed=0.7):
    driver.get("https://www.youtube.com")
    bot.inject_stealth(driver)
    bot.ln_sleep(3.0, 0.22)
    bot._reset_mouse(driver)
    if stop_event.is_set(): return False
    _accept_cookies(driver)
    _hover_links(driver, 3)
    bot.ln_sleep(1.2, 0.25)

    search_done = False
    try:
        box = WebDriverWait(driver, 7).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#search")))
        bot.human_click(driver, box)
        bot.ln_sleep(0.5, 0.25)
        bot.human_type(box, query)
        bot.ln_sleep(0.7, 0.22)
        pyautogui.press('enter')
        bot.ln_sleep(3.0, 0.22)
        bot.inject_stealth(driver)
        bot._reset_mouse(driver)
        search_done = True
    except Exception:
        pass

    if not search_done:
        driver.get(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
        bot.inject_stealth(driver)
        bot.ln_sleep(3.0, 0.22)
        bot._reset_mouse(driver)

    if stop_event.is_set(): return False
    _hover_links(driver, 2)
    bot.ln_sleep(1.0, 0.25)

    video_clicked = False
    for sel in ["ytd-video-renderer a#video-title", "ytd-video-renderer h3 a", "a#video-title"]:
        try:
            video = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            bot.human_click(driver, video)
            bot.ln_sleep(3.5, 0.22)
            bot.inject_stealth(driver)
            bot._reset_mouse(driver)
            video_clicked = True
            break
        except Exception:
            continue

    if not video_clicked:
        return False
    if stop_event.is_set(): return False

    for skip_sel in [".ytp-skip-ad-button", "button.ytp-ad-skip-button",
                     ".ytp-ad-skip-button-modern"]:
        try:
            skip = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, skip_sel)))
            bot.ln_sleep(1.0, 0.28)
            bot.human_click(driver, skip)
            bot.ln_sleep(1.2, 0.22)
            break
        except Exception:
            break

    watch = random.uniform(55, 90) * read_speed
    end_t = time.time() + watch
    while time.time() < end_t:
        if stop_event.is_set(): break
        remaining = end_t - time.time()
        chunk = min(remaining, math.exp(random.gauss(math.log(14), 0.35)))
        time.sleep(max(3, chunk))
        if time.time() < end_t and random.random() < 0.4:
            bot.idle_mouse_drift(driver, min(remaining * 0.12, 2.0))

    try:
        player = driver.find_element(By.CSS_SELECTOR, ".html5-video-player")
        bot.human_click(driver, player)
        bot.ln_sleep(1.0, 0.25)
    except Exception:
        pass

    _distraction(driver, 4, 10, stop_event)
    return True


# ==============================================================================
#  CATEGORY → PHASE FUNCTION MAP
# ==============================================================================

PHASE_MAP = {
    "News & Events":     phase_news,
    "Weather":           phase_weather,
    "YouTube":           phase_youtube,
    "Reddit":            phase_reddit,
    "Wikipedia":         phase_wikipedia,
    "Shopping":          phase_shopping,
    "Food & Recipes":    phase_food_recipes,
    "Health & Wellness": phase_health,
    "Travel & Tourism":  phase_travel,
    "Technology":        phase_technology,
}


# ==============================================================================
#  IDLE PAUSE
# ==============================================================================

def run_idle_pause(driver, minutes, stop_event):
    end_t = time.time() + minutes * 60
    while time.time() < end_t:
        if stop_event.is_set():
            return
        remaining = end_t - time.time()
        roll = random.random()
        if roll < 0.04:
            try:
                bot.scroll_page(driver, random.randint(40, 120) * random.choice([1, -1]))
            except Exception:
                pass
            time.sleep(random.uniform(8, 20))
        elif roll < 0.12:
            try:
                bot.idle_mouse_drift(driver, random.uniform(1.5, 3.5))
            except Exception:
                pass
            time.sleep(random.uniform(15, 40))
        else:
            time.sleep(min(remaining, random.uniform(20, 60)))


# ==============================================================================
#  BROWSE BLOCK RUNNER
# ==============================================================================

def run_browse_block(driver, phases, read_speed, stop_event,
                     on_phase_start=None, on_phase_done=None, phase_offset=0):
    """
    Execute a list of phase dicts: [{"category": str, "query": str}, ...]
    Calls on_phase_start(index, total, category, query) before each phase.
    Calls on_phase_done(index, total, category, query, status, duration_s) after each phase.
    Returns number of phases successfully completed.
    """
    done  = 0
    total = len(phases)

    # Сбрасываем усталость в начале каждого блока
    reset_session_fatigue()

    for i, phase in enumerate(phases):
        if stop_event.is_set():
            break

        category = phase["category"]
        query    = phase["query"]
        fn       = PHASE_MAP.get(category)
        if fn is None:
            continue

        abs_index = phase_offset + i
        if on_phase_start:
            on_phase_start(abs_index, total + phase_offset, category, query)

        bot.check_and_wait_captcha(driver)
        if stop_event.is_set():
            break

        t_start = time.time()
        success = False
        try:
            success = fn(driver, query, stop_event, read_speed)
        except Exception:
            success = False

        duration_s = time.time() - t_start
        status = "done" if success else "crashed"

        if on_phase_done:
            on_phase_done(abs_index, total + phase_offset, category, query,
                          status, duration_s)

        done += 1 if success else 0

        # Inter-phase pause
        if not stop_event.is_set():
            pause = math.exp(random.gauss(math.log(5.0), 0.35))
            time.sleep(max(2.5, min(14.0, pause)))

    return done
