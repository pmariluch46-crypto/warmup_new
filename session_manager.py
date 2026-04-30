"""
core/session_manager.py  --  Session orchestrator for WarmUpPro.

Runs browse/idle/browse in a background thread.
UI registers callbacks to receive live progress updates.
"""

import threading
import time

from core import browser_bot as bot
from core import history
from core.query_selector import select_queries
from core.warm_up_engine import run_browse_block, run_idle_pause


class SessionConfig:
    def __init__(self, firefox_binary, firefox_profile, geckodriver_path,
                 selected_categories, browse1_minutes, idle_minutes, browse2_minutes,
                 min_per_category=5, max_per_category=20, read_speed=0.7,
                 max_retries=1, auto_close=True):
        self.firefox_binary       = firefox_binary
        self.firefox_profile      = firefox_profile
        self.geckodriver_path     = geckodriver_path
        self.selected_categories  = selected_categories
        self.browse1_minutes      = browse1_minutes
        self.idle_minutes         = idle_minutes
        self.browse2_minutes      = browse2_minutes
        self.min_per_category     = min_per_category
        self.max_per_category     = max_per_category
        self.read_speed           = read_speed
        self.max_retries          = max_retries
        self.auto_close           = auto_close


class SessionStatus:
    IDLE       = "idle"
    RUNNING    = "running"
    IDLE_PAUSE = "idle_pause"
    STOPPED    = "stopped"
    COMPLETED  = "completed"
    ERROR      = "error"


class SessionManager:
    def __init__(self, settings):
        """
        Теперь SessionManager принимает settings.
        Это нужно для нового UI (main_window.py).
        """
        self.settings = settings

        self._stop_event  = threading.Event()
        self._thread      = None
        self._driver      = None
        self._lock        = threading.Lock()

        # Public state (read from UI thread)
        self.status         = SessionStatus.IDLE
        self.current_phase  = ""
        self.current_block  = ""   # "Block 1" | "Idle" | "Block 2"
        self.phase_index    = 0
        self.total_phases   = 0
        self.elapsed_s      = 0.0
        self.session_id     = None
        self._session_start = None

        # Callbacks registered by the UI
        self.on_progress  = None   # (phase_index, total, block, category, query)
        self.on_complete  = None   # (status_str, duration_m)
        self.on_error     = None   # (error_message)
        self.on_captcha   = None   # (solved: bool)

    # ------------------------------------------------------------------
    def start(self, config: SessionConfig):
        with self._lock:
            if self.status == SessionStatus.RUNNING:
                return False
            self._stop_event.clear()
            self.status = SessionStatus.RUNNING
            self._session_start = time.time()

        self._thread = threading.Thread(
            target=self._run, args=(config,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()

    def is_running(self):
        return self.status in (SessionStatus.RUNNING, SessionStatus.IDLE_PAUSE)

    def get_elapsed(self):
        if self._session_start:
            return time.time() - self._session_start
        return 0.0

    # ------------------------------------------------------------------
    def _run(self, config: SessionConfig):
        driver = None
        final_status = SessionStatus.COMPLETED

        try:
            # Select queries
            block1_phases, block2_phases = select_queries(
                config.selected_categories,
                config.browse1_minutes,
                config.browse2_minutes,
                config.min_per_category,
                config.max_per_category,
            )
            total = len(block1_phases) + len(block2_phases)
            self.total_phases = total

            # Record session start
            self.session_id = history.start_session(
                config.selected_categories, total)

            # Launch browser
            driver = bot.create_driver(
                config.firefox_binary,
                config.firefox_profile,
                config.geckodriver_path,
            )
            self._driver = driver
            bot.set_captcha_handler(self._on_captcha_event, self._stop_event)

            done_count = 0

            # ---------- BROWSE BLOCK 1 ----------
            self.current_block = "Block 1"
            done_count += run_browse_block(
                driver, block1_phases,
                config.read_speed,
                self._stop_event,
                on_phase_start=self._on_phase_start,
                on_phase_done=self._make_phase_done_cb(config),
                phase_offset=0,
            )

            # ---------- IDLE PAUSE ----------
            if not self._stop_event.is_set():
                self.status        = SessionStatus.IDLE_PAUSE
                self.current_block = "Idle Pause"
                self.current_phase = f"Idle — {config.idle_minutes} min"
                self._notify_progress(self.phase_index, total, "Idle Pause", "", "")
                run_idle_pause(driver, config.idle_minutes, self._stop_event)

            # ---------- BROWSE BLOCK 2 ----------
            if not self._stop_event.is_set():
                self.status        = SessionStatus.RUNNING
                self.current_block = "Block 2"
                done_count += run_browse_block(
                    driver, block2_phases,
                    config.read_speed,
                    self._stop_event,
                    on_phase_start=self._on_phase_start,
                    on_phase_done=self._make_phase_done_cb(config),
                    phase_offset=len(block1_phases),
                )

            if self._stop_event.is_set():
                final_status = SessionStatus.STOPPED

        except Exception as e:
            final_status = SessionStatus.ERROR
            if self.on_error:
                self.on_error(str(e))

        finally:
            bot.clear_captcha_handler()
            # Close browser
            if driver and config.auto_close:
                try:
                    driver.quit()
                except Exception:
                    pass
            self._driver = None

            # Determine DB status string
            db_status = {
                SessionStatus.COMPLETED: "completed",
                SessionStatus.STOPPED:   "stopped",
                SessionStatus.ERROR:     "partial",
            }.get(final_status, "partial")

            if self.session_id:
                history.end_session(self.session_id, self.phase_index, db_status)

            self.status = final_status
            duration_m  = round(self.get_elapsed() / 60, 1)

            if self.on_complete:
                self.on_complete(final_status, duration_m)

    # ------------------------------------------------------------------
    def _on_phase_start(self, index, total, category, query):
        self.phase_index   = index
        self.total_phases  = total
        self.current_phase = f"{category}: {query[:50]}"
        self._notify_progress(index, total, self.current_block, category, query)

    def _make_phase_done_cb(self, config):
        def _on_phase_done(index, total, category, query, status, duration_s):
            if self.session_id:
                history.log_phase(self.session_id, query, category, status, duration_s)
            # Retry once on crash
            if status == "crashed" and config.max_retries > 0:
                pass
        return _on_phase_done

    def _on_captcha_event(self, solved: bool):
        if self.on_captcha:
            try:
                self.on_captcha(solved)
            except Exception:
                pass

    def _notify_progress(self, index, total, block, category, query):
        if self.on_progress:
            try:
                self.on_progress(index, total, block, category, query)
            except Exception:
                pass
