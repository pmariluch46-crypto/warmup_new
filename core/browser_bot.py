"""
core/browser_bot.py  --  Human-like Firefox automation engine.

All paths (Firefox binary, profile, geckodriver) are passed in at runtime
so the app can work with any user-selected Firefox installation.
"""

import time
import math
import random
import ctypes
import ctypes.wintypes
import pyautogui
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

pyautogui.PAUSE    = 0
pyautogui.FAILSAFE = False

_SCREEN_W, _SCREEN_H = pyautogui.size()
_MARGIN = 15


# ==============================================================================
#  WIN32 SENDINPUT
# ==============================================================================

_INPUT_MOUSE   = 0
_MEVF_MOVE     = 0x0001
_MEVF_LDOWN    = 0x0002
_MEVF_LUP      = 0x0004
_MEVF_WHEEL    = 0x0800
_MEVF_ABS      = 0x8000


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("_i",)
    _fields_    = [("type", ctypes.c_ulong), ("_i", _I)]


def _si(flags, x=0, y=0, data=0):
    inp = _INPUT(type=_INPUT_MOUSE)
    inp.mi.dx, inp.mi.dy = x, y
    inp.mi.mouseData  = ctypes.c_ulong(data).value
    inp.mi.dwFlags    = flags
    inp.mi.time       = 0
    inp.mi.dwExtraInfo = 0
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _si_abs(x, y):
    sw = ctypes.windll.user32.GetSystemMetrics(0)
    sh = ctypes.windll.user32.GetSystemMetrics(1)
    return int(x * 65535 / max(sw - 1, 1)), int(y * 65535 / max(sh - 1, 1))


def _si_ldown(x, y):
    ax, ay = _si_abs(x, y)
    _si(_MEVF_LDOWN | _MEVF_ABS | _MEVF_MOVE, ax, ay)


def _si_lup(x, y):
    ax, ay = _si_abs(x, y)
    _si(_MEVF_LUP | _MEVF_ABS | _MEVF_MOVE, ax, ay)


def _si_move(x, y):
    ax, ay = _si_abs(x, y)
    _si(_MEVF_MOVE | _MEVF_ABS, ax, ay)


def _si_click(x, y):
    _si_ldown(x, y)
    time.sleep(random.uniform(0.04, 0.09))  # variable hold time
    _si_lup(x, y)


def _si_dblclick(x, y):
    _si_click(x, y)
    time.sleep(random.uniform(0.09, 0.18))
    _si_click(x, y)


def _si_wheel(ticks):
    _si(_MEVF_WHEEL, 0, 0, int(ticks * 120))


VIEWPORT_W = _SCREEN_W
VIEWPORT_H = _SCREEN_H


# ==============================================================================
#  TIMING
# ==============================================================================

def ln_sleep(center, sigma=0.25):
    val = math.exp(random.gauss(math.log(max(center, 0.001)), sigma))
    time.sleep(max(0.01, val))


def reaction_delay():
    ln_sleep(0.22, 0.30)


# FIX: Variable reading pace — humans read at different speeds
def reading_pause(text_length):
    """Pause proportional to text length, with natural variance."""
    base = text_length / random.uniform(900, 1400)  # chars per second reading speed
    base = max(0.8, min(12.0, base))
    ln_sleep(base, 0.22)


# ==============================================================================
#  COORDINATE HELPERS
# ==============================================================================

def _clamp_screen(sx, sy):
    return (
        max(_MARGIN, min(_SCREEN_W - _MARGIN, int(sx))),
        max(_MARGIN, min(_SCREEN_H - _MARGIN, int(sy))),
    )


def _screen_origin(driver):
    o = driver.execute_script("""
        return {
            x: window.screenX + Math.round((window.outerWidth  - window.innerWidth)  / 2),
            y: window.screenY + (window.outerHeight - window.innerHeight)
        };
    """)
    return o['x'], o['y']


def _vp_to_screen(driver, vx, vy):
    ox, oy = _screen_origin(driver)
    return ox + int(vx), oy + int(vy)


def _element_screen_center(driver, element):
    info = driver.execute_script("""
        var r = arguments[0].getBoundingClientRect();
        return {
            x: Math.round(window.screenX + Math.round((window.outerWidth-window.innerWidth)/2) + r.left + r.width/2),
            y: Math.round(window.screenY + (window.outerHeight-window.innerHeight) + r.top + r.height/2)
        };
    """, element)
    return info['x'], info['y']


# FIX: Click slightly off-center — humans never click perfectly center
def _element_screen_point(driver, element):
    """Returns a slightly randomised point within the element, not dead center."""
    info = driver.execute_script("""
        var r = arguments[0].getBoundingClientRect();
        return {
            cx: Math.round(window.screenX + Math.round((window.outerWidth-window.innerWidth)/2) + r.left + r.width/2),
            cy: Math.round(window.screenY + (window.outerHeight-window.innerHeight) + r.top + r.height/2),
            w: r.width, h: r.height
        };
    """, element)
    # Offset by up to 30% of element dimensions
    ox = random.gauss(0, info['w'] * 0.12)
    oy = random.gauss(0, info['h'] * 0.12)
    return int(info['cx'] + ox), int(info['cy'] + oy)


# ==============================================================================
#  MOUSE
# ==============================================================================

_mx, _my = VIEWPORT_W // 2, VIEWPORT_H // 2


def _cubic(t, p0, p1, p2, p3):
    mt = 1 - t
    return (
        mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
        mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1],
    )


def _bezier_segment(start, end, overshoot=False):
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    dist   = math.hypot(dx, dy) or 1
    steps  = max(20, min(110, int(dist / 6.5)))
    px, py = -dy / dist, dx / dist
    dev    = min(dist * random.uniform(0.10, 0.28), 145)
    cp1 = (sx + dx*random.uniform(0.18,0.40) + px*dev*random.uniform(-1,1),
           sy + dy*random.uniform(0.18,0.40) + py*dev*random.uniform(-1,1))
    cp2 = (sx + dx*random.uniform(0.60,0.82) + px*dev*random.uniform(-1,1),
           sy + dy*random.uniform(0.60,0.82) + py*dev*random.uniform(-1,1))
    end_curve = end
    if overshoot:
        end_curve = (ex + random.uniform(3,13)*random.choice([-1,1]),
                     ey + random.uniform(2, 7)*random.choice([-1,1]))
    points = []
    for i in range(steps + 1):
        t   = i / steps
        t_e = t*t*(3 - 2*t)
        pt  = _cubic(t_e, start, cp1, cp2, end_curve)
        points.append((pt[0] + random.gauss(0, 0.30), pt[1] + random.gauss(0, 0.30)))
    if overshoot:
        for i in range(1, 9):
            t = i / 8
            points.append((end_curve[0] + (ex-end_curve[0])*t + random.gauss(0,0.18),
                           end_curve[1] + (ey-end_curve[1])*t + random.gauss(0,0.18)))
    return points


def _build_path(start, end, overshoot=False):
    dist = math.hypot(end[0]-start[0], end[1]-start[1])
    if dist < 280:
        return _bezier_segment(start, end, overshoot=overshoot)
    n_wp = 1 if dist < 550 else 2
    waypoints = [start]
    for i in range(n_wp):
        t  = (i + 1) / (n_wp + 1)
        mx = start[0] + (end[0]-start[0])*t
        my = start[1] + (end[1]-start[1])*t
        ddx, ddy = end[0]-start[0], end[1]-start[1]
        length   = math.hypot(ddx, ddy) or 1
        ppx, ppy = -ddy/length, ddx/length
        offset   = random.uniform(-dist*0.09, dist*0.09)
        waypoints.append((mx + ppx*offset, my + ppy*offset))
    waypoints.append(end)
    all_points = []
    for i in range(len(waypoints)-1):
        ov = (i == len(waypoints)-2) and overshoot
        all_points.extend(_bezier_segment(waypoints[i], waypoints[i+1], overshoot=ov))
    return all_points


def _reset_mouse(driver):
    global _mx, _my
    # FIX: reset to a random position, not always dead center
    _mx = random.randint(VIEWPORT_W // 3, 2 * VIEWPORT_W // 3)
    _my = random.randint(VIEWPORT_H // 3, 2 * VIEWPORT_H // 3)
    sx, sy = _clamp_screen(*_vp_to_screen(driver, _mx, _my))
    pyautogui.moveTo(sx, sy)


def _move_path(driver, path):
    ox, oy = _screen_origin(driver)
    n = len(path)
    speed_bias = random.gauss(1.0, 0.18)  # FIX: wider variance = more personality
    for i, pt in enumerate(path):
        sx, sy = _clamp_screen(ox + pt[0], oy + pt[1])
        pyautogui.moveTo(sx, sy)
        progress     = i / max(n-1, 1)
        speed_factor = 1.0 - 0.55*(1 - abs(2*progress - 1))
        step_t = (0.012 + 0.018*speed_factor) * speed_bias + random.gauss(0, 0.002)
        time.sleep(max(0.007, step_t))
        if random.random() < 0.014:  # FIX: slightly more frequent micro-pauses
            time.sleep(random.uniform(0.05, 0.30))


def mouse_move(driver, tx, ty):
    global _mx, _my
    tx = max(5, min(VIEWPORT_W-5, int(tx)))
    ty = max(5, min(VIEWPORT_H-5, int(ty)))
    path = _build_path((_mx, _my), (tx, ty), overshoot=random.random() < 0.05)
    _move_path(driver, path)
    _mx, _my = tx, ty


def _is_in_viewport(driver, element) -> bool:
    try:
        return driver.execute_script("""
            var r = arguments[0].getBoundingClientRect();
            return r.top >= 0 && r.left >= 0 &&
                   r.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                   r.right  <= (window.innerWidth  || document.documentElement.clientWidth);
        """, element)
    except Exception:
        return False


def mouse_move_to_element(driver, element):
    global _mx, _my
    if not _is_in_viewport(driver, element):
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'nearest'});", element)
        ln_sleep(0.38, 0.25)
    sx, sy = _element_screen_point(driver, element)  # FIX: use off-center point
    ox, oy = _screen_origin(driver)
    tvx = sx - ox
    tvy = sy - oy
    path = _build_path((_mx, _my), (tvx, tvy), overshoot=random.random() < 0.05)
    _move_path(driver, path)
    _mx = max(5, min(VIEWPORT_W-5, tvx))
    _my = max(5, min(VIEWPORT_H-5, tvy))


def hover_jitter(driver, duration=1.0):
    ox, oy = _screen_origin(driver)
    end_t  = time.time() + duration
    drift_x = random.gauss(0, 1.4)
    drift_y = random.gauss(0, 1.0)
    elapsed = 0.0
    while time.time() < end_t:
        frac = min(elapsed / max(duration, 0.001), 1.0)
        jx = _mx + drift_x * frac + random.gauss(0, 2.8)
        jy = _my + drift_y * frac + random.gauss(0, 2.0)
        sx, sy = _clamp_screen(ox + jx, oy + jy)
        pyautogui.moveTo(sx, sy)
        dt = random.uniform(0.022, 0.090)
        time.sleep(dt)
        elapsed += dt


def human_click(driver, element):
    mouse_move_to_element(driver, element)
    hover_jitter(driver, duration=random.uniform(0.06, 0.32))
    sx, sy = _element_screen_point(driver, element)  # FIX: off-center click
    sx, sy = _clamp_screen(sx, sy)
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.08, 0.18))
    time.sleep(random.uniform(0.08, 0.14))
    _si_click(sx, sy)
    ln_sleep(0.42, 0.28)


# FIX: Occasionally double-tap accidentally (rare but human)
def human_click_maybe_double(driver, element):
    mouse_move_to_element(driver, element)
    hover_jitter(driver, duration=random.uniform(0.06, 0.32))
    sx, sy = _element_screen_point(driver, element)
    sx, sy = _clamp_screen(sx, sy)
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.08, 0.18))
    time.sleep(random.uniform(0.08, 0.14))
    if random.random() < 0.03:  # 3% accidental double click
        _si_dblclick(sx, sy)
    else:
        _si_click(sx, sy)
    ln_sleep(0.42, 0.28)


def idle_mouse_drift(driver, duration=2.0):
    end_t = time.time() + duration
    while time.time() < end_t:
        r = random.random()
        if r < 0.12:
            edge = random.choice(['bottom', 'left', 'right'])
            if edge == 'bottom':
                nx = random.randint(100, _SCREEN_W - 100)
                ny = random.randint(_SCREEN_H - 80, _SCREEN_H - _MARGIN)
            elif edge == 'left':
                nx = random.randint(_MARGIN, 80)
                ny = random.randint(100, _SCREEN_H - 100)
            else:
                nx = random.randint(_SCREEN_W - 80, _SCREEN_W - _MARGIN)
                ny = random.randint(100, _SCREEN_H - 100)
            mouse_move(driver, nx, ny)
            ln_sleep(random.uniform(0.4, 2.2), 0.30)
            mouse_move(driver, random.randint(300, VIEWPORT_W-300),
                                random.randint(200, VIEWPORT_H-200))
        else:
            dx = random.randint(-70, 70)
            dy = random.randint(-45, 45)
            nx = max(10, min(VIEWPORT_W-10, _mx+dx))
            ny = max(10, min(VIEWPORT_H-10, _my+dy))
            mouse_move(driver, nx, ny)
            hover_jitter(driver, duration=random.uniform(0.18, 0.65))


# ==============================================================================
#  SCROLL
# ==============================================================================

def wheel_scroll_smooth(driver, pixels):
    if pixels == 0:
        return

    ox, oy = _screen_origin(driver)
    sx, sy = _clamp_screen(ox + _mx, oy + _my)

    direction = -1 if pixels > 0 else 1
    total_px  = abs(pixels)

    px_per_tick = random.randint(85, 135)
    n_ticks     = max(1, min(8, round(total_px / px_per_tick)))

    base_delay = max(0.035, 0.110 - total_px * 0.00006)
    speed_bias = random.gauss(1.0, 0.12)

    next_drift_at = random.randint(2, 5)

    for i in range(n_ticks):
        _si_wheel(direction)

        progress   = i / max(n_ticks - 1, 1)
        curve      = 1.0 - 0.65 * (1 - abs(2 * progress - 1))
        tick_delay = base_delay * curve * speed_bias + random.gauss(0, 0.006)
        time.sleep(max(0.025, tick_delay))

        if i >= next_drift_at and i < n_ticks - 1:
            dx = random.randint(-8, 8)
            dy = random.randint(-6, 6)
            new_sx = max(5, min(pyautogui.size()[0] - 5, sx + dx))
            new_sy = max(5, min(pyautogui.size()[1] - 5, sy + dy))
            pyautogui.moveTo(new_sx, new_sy, duration=random.uniform(0.02, 0.07))
            sx, sy = new_sx, new_sy
            next_drift_at = i + random.randint(2, 5)

    time.sleep(random.uniform(0.10, 0.32))


def scrollbar_drag_scroll(driver, pixels):
    if pixels == 0:
        return
    try:
        info = driver.execute_script("""
            return {
                wx: window.screenX, wy: window.screenY,
                outerW: window.outerWidth, outerH: window.outerHeight,
                innerH: window.innerHeight, innerW: window.innerWidth,
                scrollTop: window.scrollY || document.documentElement.scrollTop || 0,
                pageH: Math.max(
                    document.body ? document.body.scrollHeight : 0,
                    document.documentElement.scrollHeight || 0)
            };
        """)

        page_h   = max(info['pageH'], 1)
        inner_h  = info['innerH']
        outer_w  = info['outerW']
        outer_h  = info['outerH']
        chrome_h = outer_h - inner_h
        wx, wy   = info['wx'], info['wy']
        max_scroll = max(page_h - inner_h, 1)

        if page_h <= inner_h + 10:
            return

        sb_x = max(5, min(_SCREEN_W - 5, int(wx + outer_w - 9)))
        track_top = wy + chrome_h
        track_h   = outer_h - chrome_h
        track_bot = track_top + track_h
        thumb_h = max(20, int((inner_h / page_h) * track_h))
        scroll_top = info['scrollTop']

        cur_pct    = scroll_top / max_scroll
        cur_thumb  = track_top + cur_pct * (track_h - thumb_h)
        cur_center = int(cur_thumb + thumb_h / 2)

        direction  = 1 if pixels > 0 else -1
        new_scroll = max(0, min(max_scroll, scroll_top + abs(pixels) * direction))
        new_pct    = new_scroll / max_scroll
        new_thumb  = track_top + new_pct * (track_h - thumb_h)
        new_center = int(new_thumb + thumb_h / 2)

        half_t     = thumb_h // 2
        cur_center = max(int(track_top) + half_t, min(int(track_bot) - half_t, cur_center))
        new_center = max(int(track_top) + half_t, min(int(track_bot) - half_t, new_center))

        if abs(new_center - cur_center) < 2:
            return

        pyautogui.moveTo(sb_x, cur_center, duration=random.uniform(0.22, 0.58))
        time.sleep(0.18)

        _si_ldown(sb_x, cur_center)
        ln_sleep(0.05, 0.04)

        steps     = max(12, abs(new_center - cur_center) // 4)
        drag_time = max(0.3, min(1.6,
            abs(new_center - cur_center) / 300.0 + random.uniform(0.2, 0.5)))

        last_cx, last_cy = sb_x, cur_center
        for i in range(1, steps + 1):
            t       = i / steps
            t_eased = t * t * (3 - 2 * t)
            last_cx = sb_x + random.randint(-1, 1)
            last_cy = max(int(track_top), min(int(track_bot),
                          int(cur_center + (new_center - cur_center) * t_eased)))
            _si_move(last_cx, last_cy)
            time.sleep(drag_time / steps + random.gauss(0, 0.004))

        ln_sleep(0.06, 0.04)
        _si_lup(last_cx, last_cy)
        time.sleep(0.35)

        ox, oy = _screen_origin(driver)
        away_x = random.randint(150, max(200, inner_h - 150))
        away_y = random.randint(200, max(250, inner_h - 150))
        _si_move(ox + away_x, oy + away_y)
        global _mx, _my
        _mx = away_x
        _my = away_y

    except Exception:
        pass


def scroll_page(driver, pixels):
    """
    FIX: Mix scrollbar drag and wheel scroll naturally.
    Real users use both — mostly wheel, occasionally scrollbar.
    """
    if random.random() < 0.25:
        scrollbar_drag_scroll(driver, pixels)
    else:
        wheel_scroll_smooth(driver, pixels)


# FIX: Natural multi-step scroll — humans rarely do one big scroll
def scroll_natural(driver, total_pixels, stop_event=None):
    """
    Scroll total_pixels in multiple small steps with pauses between,
    like a real person reading down a page.
    """
    direction = 1 if total_pixels > 0 else -1
    remaining = abs(total_pixels)
    while remaining > 0:
        if stop_event and stop_event.is_set():
            return
        chunk = min(remaining, random.randint(120, 380))
        scroll_page(driver, chunk * direction)
        remaining -= chunk
        # Pause between scrolls — reading the content
        if remaining > 0:
            ln_sleep(random.uniform(0.4, 2.2), 0.28)


# ==============================================================================
#  TYPING
# ==============================================================================

_ADJACENT = {
    'a':'sq','b':'vn','c':'xv','d':'sf','e':'wr','f':'dg','g':'fh','h':'gj',
    'i':'uo','j':'hk','k':'jl','l':'k', 'm':'n', 'n':'bm','o':'ip','p':'o',
    'q':'wa','r':'et','s':'ad','t':'ry','u':'yi','v':'cb','w':'qe','x':'zc',
    'y':'tu','z':'x',
}


def _type_char(char):
    try:
        if char == ' ':
            pyautogui.press('space')
        elif char == '\n':
            pyautogui.press('enter')
        elif char == '\t':
            pyautogui.press('tab')
        else:
            pyautogui.write(char, interval=0)
    except Exception:
        try:
            pyautogui.press(char)
        except Exception:
            pass


def human_type(element, text, wpm=None):
    if wpm is None:
        wpm = max(30, min(95, random.gauss(54, 10)))
    base_delay = 60 / (wpm * 5)
    words = text.split(' ')
    for wi, word in enumerate(words):
        if wi > 0:
            pyautogui.press('space')
            ln_sleep(base_delay * (2.4 + len(word)/9.0), 0.28)
        for char in word:
            # FIX: slightly higher typo rate, also fix by selecting+retyping
            if char.isalpha() and random.random() < 0.032:
                wrong = random.choice(_ADJACENT.get(char.lower(), char.lower()))
                _type_char(wrong)
                ln_sleep(0.16, 0.28)
                # FIX: occasionally type another wrong char before correcting
                if random.random() < 0.20:
                    _type_char(random.choice('asdfjkl'))
                    ln_sleep(0.12, 0.25)
                    pyautogui.press('backspace')
                    ln_sleep(0.10, 0.22)
                pyautogui.press('backspace')
                ln_sleep(0.18, 0.28)
            _type_char(char)
            extra = random.uniform(0.025, 0.075) if (char.isupper() or char in '!@#$%^&*()_+') else 0.0
            time.sleep(max(0.025, random.gauss(base_delay, base_delay*0.42)) + extra)
            if random.random() < 0.038:
                ln_sleep(0.30, 0.35)
        if random.random() < 0.07:
            ln_sleep(0.60, 0.30)


# ==============================================================================
#  HUMAN INTERACTIONS
# ==============================================================================

def select_random_text(driver):
    try:
        paras = driver.find_elements(By.CSS_SELECTOR, "p, li, h2, h3")
        paras = [p for p in paras if p.is_displayed() and len(p.text.strip()) > 40]
        if not paras:
            return
        target = random.choice(paras[:15])
        mouse_move_to_element(driver, target)
        hover_jitter(driver, 0.20)
        sx, sy = _element_screen_point(driver, target)
        sx, sy = _clamp_screen(sx, sy)
        _si_dblclick(sx, sy)
        ln_sleep(0.55, 0.28)
        if random.random() < 0.55:
            mouse_move(driver, random.randint(200, VIEWPORT_W-200),
                                random.randint(200, VIEWPORT_H-200))
            cx, cy = _clamp_screen(*_vp_to_screen(driver, _mx, _my))
            _si_click(cx, cy)
            ln_sleep(0.25, 0.22)
    except Exception:
        pass


def occasional_ctrl_f(driver, chance=0.20, context='general'):
    if random.random() > chance:
        return
    try:
        pyautogui.hotkey('ctrl', 'f')
        ln_sleep(0.55, 0.25)
        if context == 'amazon':
            terms = ["review", "price", "shipping", "return", "color", "size",
                     "warranty", "compatible", "quality", "genuine", "fast", "works"]
        else:
            terms = ["the", "and", "with", "from", "price", "best", "more",
                     "how", "review", "2025", "about", "guide"]
        term = random.choice(terms)
        for ch in term:
            _type_char(ch)
            time.sleep(random.uniform(0.07, 0.16))
        ln_sleep(0.70, 0.25)
        pyautogui.press('escape')
        ln_sleep(0.38, 0.20)
    except Exception:
        pass


def occasional_zoom(driver, chance=0.10):
    if random.random() > chance:
        return
    try:
        direction = random.choice(['in', 'out', 'reset'])
        if direction == 'in':
            pyautogui.hotkey('ctrl', '+')
            ln_sleep(0.9, 0.25)
            if random.random() < 0.5:
                pyautogui.hotkey('ctrl', '+')
        elif direction == 'out':
            pyautogui.hotkey('ctrl', '-')
            ln_sleep(0.7, 0.22)
        else:
            pyautogui.hotkey('ctrl', '0')
        ln_sleep(0.6, 0.22)
    except Exception:
        pass


# FIX: New helper — humans sometimes hover over images without clicking
def hover_image_area(driver, stop_event=None):
    """Move mouse over product images area without clicking."""
    try:
        imgs = driver.find_elements(By.CSS_SELECTOR, "img[src]")
        visible = [i for i in imgs if i.is_displayed() and i.size.get('width', 0) > 80]
        if not visible:
            return
        img = random.choice(visible[:8])
        mouse_move_to_element(driver, img)
        hover_jitter(driver, random.uniform(0.5, 2.0))
    except Exception:
        pass


# FIX: New helper — right-click context menu (real user behaviour)
def occasional_right_click(driver, chance=0.08):
    """Occasionally right-click and immediately dismiss — very human."""
    if random.random() > chance:
        return
    try:
        ox, oy = _screen_origin(driver)
        rx = random.randint(200, VIEWPORT_W - 200)
        ry = random.randint(200, VIEWPORT_H - 200)
        mouse_move(driver, rx, ry)
        sx, sy = _clamp_screen(ox + rx, oy + ry)
        pyautogui.rightClick(sx, sy)
        ln_sleep(random.uniform(0.3, 1.2), 0.25)
        pyautogui.press('escape')
        ln_sleep(0.25, 0.20)
    except Exception:
        pass


# FIX: New helper — tab switching (humans check other tabs occasionally)
def occasional_tab_switch(driver, chance=0.06):
    """Ctrl+Tab to another tab and back — simulates checking other open tabs."""
    if random.random() > chance:
        return
    try:
        pyautogui.hotkey('ctrl', 'tab')
        ln_sleep(random.uniform(1.5, 4.0), 0.30)
        pyautogui.hotkey('ctrl', 'shift', 'tab')
        ln_sleep(random.uniform(0.5, 1.2), 0.22)
        inject_stealth(driver)
    except Exception:
        pass


# ==============================================================================
#  STEALTH JS
# ==============================================================================

_STEALTH_JS = """
(function(){
    try{delete window.__fxdriver_unwrapped;}catch(e){}
    try{delete window.__webdriver_script_fn;}catch(e){}
    try{delete window._Selenium_IDE_Recorder;}catch(e){}
    try{delete window.__fxdriver_evaluate;}catch(e){}
    try{delete window.__fxdriver_async_script;}catch(e){}
})();
"""


def inject_stealth(driver):
    try:
        driver.execute_script(_STEALTH_JS)
    except Exception:
        pass


# ==============================================================================
#  CAPTCHA DETECTION & WAITING
# ==============================================================================

_captcha_notify_cb = None
_captcha_stop_ref  = None


def set_captcha_handler(notify_cb, stop_event):
    global _captcha_notify_cb, _captcha_stop_ref
    _captcha_notify_cb = notify_cb
    _captcha_stop_ref  = stop_event


def clear_captcha_handler():
    global _captcha_notify_cb, _captcha_stop_ref
    _captcha_notify_cb = None
    _captcha_stop_ref  = None


def detect_captcha(driver) -> bool:
    try:
        url = driver.current_url
        if 'google.com/sorry' in url or 'recaptcha' in url.lower():
            return True
        iframes = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha"]')
        if any(f.is_displayed() for f in iframes):
            return True
        els = driver.find_elements(By.CSS_SELECTOR,
            '#captcha-form, .g-recaptcha, #recaptcha, div[data-sitekey]')
        if any(e.is_displayed() for e in els):
            return True
    except Exception:
        pass
    return False


def check_and_wait_captcha(driver):
    if not detect_captcha(driver):
        return
    if _captcha_notify_cb:
        try:
            _captcha_notify_cb(False)
        except Exception:
            pass
    while True:
        if _captcha_stop_ref and _captcha_stop_ref.is_set():
            return
        time.sleep(2.0)
        if not detect_captcha(driver):
            time.sleep(2.5)
            try:
                inject_stealth(driver)
            except Exception:
                pass
            if _captcha_notify_cb:
                try:
                    _captcha_notify_cb(True)
                except Exception:
                    pass
            return


# ==============================================================================
#  DRIVER SETUP
# ==============================================================================

def _focus_browser_window():
    import ctypes
    try:
        user32  = ctypes.windll.user32
        found   = [None]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        def _cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            if 'Firefox' in title or 'Mozilla' in title:
                found[0] = hwnd
                return False
            return True

        user32.EnumWindows(_cb, 0)
        if found[0]:
            user32.ShowWindow(found[0], 9)
            user32.SetForegroundWindow(found[0])
            time.sleep(0.35)
    except Exception:
        pass


def navigate_addressbar(driver, url: str):
    try:
        info = driver.execute_script("""return {
            wx: window.screenX, wy: window.screenY,
            outerW: window.outerWidth, outerH: window.outerHeight,
            innerH: window.innerHeight
        };""")
        chrome_h = info['outerH'] - info['innerH']
        bar_x = info['wx'] + info['outerW'] // 2
        bar_y = info['wy'] + max(28, int(chrome_h * 0.58))
        bar_x = max(5, min(bar_x, _SCREEN_W - 5))
        bar_y = max(5, min(bar_y, _SCREEN_H - 5))

        pyautogui.moveTo(bar_x, bar_y, duration=random.uniform(0.28, 0.65))
        ln_sleep(0.12, 0.10)

        pyautogui.hotkey('ctrl', 'l')
        ln_sleep(0.30, 0.14)

        pyautogui.hotkey('ctrl', 'a')
        ln_sleep(0.10, 0.08)

        display = url.replace('https://', '').replace('http://', '').rstrip('/')

        for ch in display:
            pyautogui.typewrite(ch, interval=0)
            time.sleep(max(0.06, random.gauss(0.20, 0.06)))

        ln_sleep(0.30, 0.16)
        pyautogui.press('enter')
        ln_sleep(2.8, 0.22)
        inject_stealth(driver)

    except Exception:
        full_url = url if url.startswith('http') else f'https://{url}'
        driver.get(full_url)
        inject_stealth(driver)
        ln_sleep(2.2, 0.22)


def create_driver(firefox_binary, firefox_profile, geckodriver_path):
    options = Options()
    options.binary_location = firefox_binary
    options.add_argument("-profile")
    options.add_argument(firefox_profile)

    options.set_preference("dom.webdriver.enabled",        False)
    options.set_preference("useAutomationExtension",       False)
    options.set_preference("marionette.enabled",           True)
    options.set_preference("toolkit.telemetry.enabled",    False)
    options.set_preference("dom.push.enabled",             False)
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("privacy.resistFingerprinting", False)

    service = Service(executable_path=geckodriver_path)
    driver  = webdriver.Firefox(service=service, options=options)
    driver.execute_script(_STEALTH_JS)
    driver.maximize_window()
    _focus_browser_window()
    return driver


# ==============================================================================
#  GOOGLE HELPERS
# ==============================================================================

def dismiss_cookie_banner(driver):
    xpaths = [
        '//button[.//span[contains(text(),"Accept all")]]',
        '//button[contains(text(),"Accept all")]',
        '//button[contains(text(),"I agree")]',
        '//button[contains(text(),"Agree")]',
    ]
    for xpath in xpaths:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            human_click(driver, btn)
            ln_sleep(1.0, 0.25)
            return
        except Exception:
            continue


def google_search(driver, query):
    """
    FIX: Sometimes visit Google homepage first before searching,
    like a real user who types google.com in the address bar.
    """
    # 30% of the time go to google.com homepage first
    if random.random() < 0.30:
        navigate_addressbar(driver, "google.com")
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.NAME, "q")))
        except TimeoutException:
            pass
        dismiss_cookie_banner(driver)
        ln_sleep(random.uniform(0.8, 2.0), 0.25)

        # Type in the search box on homepage
        try:
            search_box = driver.find_element(By.NAME, "q")
            human_click(driver, search_box)
            ln_sleep(0.3, 0.20)
            human_type(search_box, query)
            ln_sleep(0.4, 0.18)
            pyautogui.press('enter')
            ln_sleep(2.5, 0.22)
            inject_stealth(driver)
        except Exception:
            # Fall back to address bar search
            navigate_addressbar(driver, query)
    else:
        # Type query directly in address bar
        navigate_addressbar(driver, query)

    driver.maximize_window()
    _reset_mouse(driver)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "search")))
    except TimeoutException:
        pass

    check_and_wait_captcha(driver)
    idle_mouse_drift(driver, random.uniform(1.2, 3.5))
    ln_sleep(0.8, 0.20)


def get_organic_results(driver, max_results=8):
    results, seen = [], set()
    for a in driver.find_elements(By.CSS_SELECTOR, "div#search a[jsname][href]"):
        href = a.get_attribute("href") or ""
        if not href.startswith("http") or "google.com" in href or href in seen:
            continue
        try:
            title = a.find_element(By.CSS_SELECTOR, "h3").text.strip()
        except Exception:
            continue
        if title:
            results.append((title, href))
            seen.add(href)
        if len(results) >= max_results:
            break
    return results


def click_result(driver, target_url):
    """
    FIX: Try harder to find and click the actual link element.
    Falls back to driver.get() only as last resort.
    """
    # Try multiple selector approaches
    selectors = [
        f"div#search a[href='{target_url}']",
        "div#search a[jsname][href]",
    ]
    for sel in selectors:
        for a in driver.find_elements(By.CSS_SELECTOR, sel):
            href = a.get_attribute("href") or ""
            if href == target_url or target_url in href:
                if a.is_displayed():
                    # FIX: scroll result into view naturally before clicking
                    if not _is_in_viewport(driver, a):
                        scroll_natural(driver, 200)
                        ln_sleep(0.4, 0.20)
                    human_click(driver, a)
                    ln_sleep(3.2, 0.22)
                    inject_stealth(driver)
                    _reset_mouse(driver)
                    return True

    # Last resort — direct navigation (not ideal but functional)
    driver.get(target_url)
    inject_stealth(driver)
    ln_sleep(3.0, 0.22)
    _reset_mouse(driver)
    return False
