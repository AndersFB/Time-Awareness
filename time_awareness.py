

import datetime
import subprocess
import time
import sys
from pathlib import Path
from typing import Tuple, Optional
from loguru import logger
import threading
import logging

try:
    from pydbus import SessionBus, SystemBus
except Exception as e:
    SessionBus = None
    SystemBus = None
    logger.warning("pydbus not available; lock and sleep detection disabled: {}", e)

from database import (
    save_session, get_sessions,
    set_metadata, get_metadata, get_sessions_since, get_sessions_by_weekday,
    get_all_sessions, get_sessions_for_day, get_previous_session, get_days_tracked, configure_database,
    create_tables_if_not_exist
)

class TimeAwareness:
    def __init__(self,
                 app_dir: Path,
                 start_daemon: bool = False,
                 log_to_terminal: bool = False):
        self._setup(app_dir, log_to_terminal)
        logger.info("Initializing TimeAwareness.")

        self.current_session = None
        self.today_total = None

        # Runtime state for daemon
        self._daemon_stop_event = threading.Event()
        self._is_active = False
        self._last_update_date = None
        self._screen_locked = False
        self._last_check = None

        self.load_state()

        self.monitor_lock_and_sleep = True
        self.end_session_on_restart = False
        self.end_session_idle_threshold = 10  # minutes

        if start_daemon:
            poll_interval = 5.0
            sleep_detection_threshold = 30.0

            self.daemon_thread = threading.Thread(
                target=self.run_daemon,
                args=(poll_interval, sleep_detection_threshold),
                daemon=True
            )
            self.daemon_thread.start()

        logger.info("TimeAwareness initialized.")

    @property
    def end_session_on_restart(self) -> bool:
        return self._end_session_on_restart

    @end_session_on_restart.setter
    def end_session_on_restart(self, end: bool):
        self._end_session_on_restart = end
        logger.info("End session on restart set to {}", end)

    @property
    def monitor_lock_and_sleep(self) -> bool:
        return self._monitor_lock_and_sleep

    @monitor_lock_and_sleep.setter
    def monitor_lock_and_sleep(self, monitor: bool):
        self._monitor_lock_and_sleep = monitor
        logger.info("Monitor lock and sleep set to {}", monitor)

    @property
    def end_session_idle_threshold(self) -> datetime.timedelta:
        return self._end_session_idle_threshold

    @end_session_idle_threshold.setter
    def end_session_idle_threshold(self, minutes: int):
        self._end_session_idle_threshold = datetime.timedelta(minutes=minutes)
        logger.info("End session idle threshold set to {} minutes", minutes)

    def _setup(self, app_dir: Path, log_to_terminal: bool):
        logging.getLogger("peewee").setLevel(logging.CRITICAL)

        if not app_dir.exists():
            app_dir.mkdir(parents=True)

        log_path = app_dir / "timeawareness.log"
        logger.add(str(log_path), rotation="10 MB", retention="10 days")
        if not log_to_terminal:
            logger.remove(0)
        logger.info("Log file created at {}", log_path)

        db_path = app_dir / "timeawareness.sqlite"
        logger.info("Database path set to {}", db_path)
        configure_database(database=db_path)
        create_tables_if_not_exist()
        logger.info("Database configured and tables checked/created.")

    def _check_day_rollover(self):
        today = datetime.date.today()
        if today != self._last_update_date:
            logger.info("New day detected. Recalculating today_total.")
            self.today_total = 0
            midnight = datetime.datetime.combine(today, datetime.time.min)

            # If a session survived past midnight, only count a small safe overlap to avoid phantom time.
            if self.current_session and self.current_session < midnight:
                elapsed_since_midnight = (datetime.datetime.now() - midnight).total_seconds()
                if elapsed_since_midnight <= 600:  # cap at 10 minutes
                    self.today_total += elapsed_since_midnight
                    logger.info("Added overlap from ongoing session: {} seconds", elapsed_since_midnight)
                else:
                    logger.info("Skipped overlap from ongoing session: {}s exceeds cap (likely slept)", elapsed_since_midnight)

            # If the most recently SAVED session overlaps midnight, include only the portion after midnight
            previous = get_previous_session(verbose=False)
            if previous:
                prev_start, prev_end, prev_duration = previous
                if prev_end > midnight:
                    overlap = (prev_end - midnight).total_seconds()
                    self.today_total += overlap
                    logger.info("Added overlap from previous session: {} seconds", overlap)

            self._last_update_date = today
            self.save_state()

    def _get_system_uptime(self) -> float:
        try:
            if sys.platform.startswith("linux"):
                with open("/proc/uptime") as f:
                    return float(f.readline().split()[0])
            elif sys.platform == "darwin":
                output = subprocess.check_output(
                    ["sysctl", "-n", "kern.boottime"]
                ).decode()
                import re
                match = re.search(r"sec = (\d+)", output)
                if match:
                    boot_time = int(match.group(1))
                    now = int(time.time())
                    return float(now - boot_time)
                else:
                    logger.error("Failed to parse kern.boottime output: {}", output)
                    return 0.0
            else:
                logger.warning("System uptime not supported on this platform: {}", sys.platform)
                return 0.0
        except Exception as e:
            logger.error("Failed to read system uptime: {}", e)
            return 0.0

    def save_state(self):
        saved_today = set_metadata("today_total", self.today_total)
        set_metadata("last_update_date", self._last_update_date.isoformat())

        if self.current_session is not None:
            set_metadata("current_session", self.current_session.isoformat())
        else:
            set_metadata("current_session", "")
        if not saved_today:
            logger.error("Failed to save state to database.")

    def load_state(self):
        self.today_total = float(get_metadata("today_total") or 0)

        last_date_str = get_metadata("last_update_date", "")
        if last_date_str:
            try:
                self._last_update_date = datetime.date.fromisoformat(last_date_str)
            except Exception:
                self._last_update_date = datetime.date.today()
        else:
            self._last_update_date = datetime.date.today()

        session_str = get_metadata("current_session", "")
        if session_str:
            try:
                self.current_session = datetime.datetime.fromisoformat(session_str)
            except Exception as e:
                logger.error("Failed to parse current_session from metadata: {}", e)
                self.current_session = None
        else:
            self.current_session = None

    def start_session(self):
        if self.current_session is not None:
            self.end_session()
        self.current_session = datetime.datetime.now()
        logger.info("Session started at {}", self.current_session)
        self.save_state()

    def end_session(self) -> Optional[datetime.timedelta]:
        if self.current_session is None:
            logger.warning("Attempted to end session, but no session was started.")
            return None
        end_time = datetime.datetime.now()
        session_duration = end_time - self.current_session
        saved = save_session(self.current_session, end_time, session_duration)
        if not saved:
            logger.error("Failed to save session from {} to {}", self.current_session, end_time)
            return None
        logger.info("Session ended at {} (duration: {})", end_time, session_duration)
        self.current_session = None
        self.today_total += session_duration.total_seconds()
        self.save_state()
        return session_duration

    # ---------- Fix 2: allow retroactive session end at a chosen timestamp ----------
    def end_session_at(self, end_time: datetime.datetime) -> Optional[datetime.timedelta]:
        """End the current session at a specific time (e.g., just before sleep),
        so we don't count the time gap as active.
        """
        if self.current_session is None:
            logger.warning("Attempted to end session at {}, but no session was started.", end_time)
            return None
        if end_time < self.current_session:
            # Guard: do not create negative durations
            logger.warning("end_session_at called with end_time before current_session; clamping to current_session")
            end_time = self.current_session
        session_duration = end_time - self.current_session
        saved = save_session(self.current_session, end_time, session_duration)
        if not saved:
            logger.error("Failed to save session from {} to {}", self.current_session, end_time)
            return None
        logger.info("Session ended at {} (duration: {}) [end_session_at]", end_time, session_duration)
        self.current_session = None
        # Update today's total conservatively: only add if end_time is today.
        today = datetime.date.today()
        if end_time.date() == today:
            self.today_total += session_duration.total_seconds()
        # Else, rely on _check_day_rollover() to compute today's overlap.
        self.save_state()
        return session_duration

    def current_session_info(self, verbose: bool = True) -> Optional[Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]]:
        if self.current_session is None:
            if verbose:
                logger.warning("No session started.")
            return None
        now = datetime.datetime.now()
        duration = now - self.current_session
        return self.current_session, now, duration

    def previous_session(self, verbose: bool = True) -> Optional[Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]]:
        session = get_previous_session(verbose=verbose)
        if session is None and verbose:
            logger.warning("No previous sessions.")
        return session

    def days_tracked(self) -> int:
        return get_days_tracked()

    def total_time_today(self) -> datetime.timedelta:
        return datetime.timedelta(seconds=self.today_total)

    def total_time_yesterday(self) -> datetime.timedelta:
        yesterday = datetime.datetime.now().date() - datetime.timedelta(days=1)
        history = get_sessions_for_day(yesterday)
        total = sum((duration for start, end, duration in history), datetime.timedelta())
        return total

    def seven_day_average(self) -> datetime.timedelta:
        seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
        history = get_sessions_since(seven_days_ago)
        total = sum((duration for start, end, duration in history), datetime.timedelta())
        days_count = len({start.date() for start, end, duration in history})
        if days_count == 0:
            return datetime.timedelta()
        return total / days_count

    def weekday_average(self) -> datetime.timedelta:
        weekday_histories = get_sessions_by_weekday()
        averages = []
        for durations in weekday_histories.values():
            if durations:
                averages.append(sum(durations, datetime.timedelta()) / len(durations))
        if not averages:
            return datetime.timedelta()
        return sum(averages, datetime.timedelta()) / len(averages)

    def total_average(self) -> datetime.timedelta:
        history = get_all_sessions()
        if not history:
            return datetime.timedelta()
        total = sum((duration for start, end, duration in history), datetime.timedelta())
        return total / len(history)

    def history(self, count_sessions: bool = False):
        return {
            "days": self.days_tracked(),
            "total_today": self.total_time_today(),
            "total_yesterday": self.total_time_yesterday(),
            "seven_day_average": self.seven_day_average(),
            "weekday_average": self.weekday_average(),
            "total_average": self.total_average(),
            "sessions": get_sessions(count_sessions),
        }

    def _get_idle_time_linux(self) -> Optional[datetime.timedelta]:
        """Try multiple backends to get idle time on Linux. Returns None if unknown."""
        # 1) GNOME Mutter IdleMonitor (preferred)
        try:
            bus = SessionBus()
            idle_monitor = bus.get("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core")
            idle_time_ms = idle_monitor.GetIdletime()
            # GNOME returns microseconds; but on some versions it's milliseconds.
            # Treat as microseconds if it's large, else convert from ms.
            # Here we assume microseconds per GNOME docs.
            return datetime.timedelta(microseconds=idle_time_ms)
        except Exception:
            pass

        # 2) org.freedesktop.ScreenSaver (KDE/others): some implementations expose GetSessionIdleTime()
        try:
            bus = SessionBus()
            ss = bus.get("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")
            # Try as property or method
            if hasattr(ss, "GetSessionIdleTime"):
                idle_seconds = ss.GetSessionIdleTime()
                return datetime.timedelta(seconds=float(idle_seconds))
            # Some expose IdleTime property
            if hasattr(ss, "IdleTime"):
                idle_seconds = ss.IdleTime
                return datetime.timedelta(seconds=float(idle_seconds))
        except Exception:
            pass

        # Unknown DE or backend not available
        return None

    def get_idle_time(self) -> datetime.timedelta:
        try:
            if sys.platform.startswith("linux"):
                idle = self._get_idle_time_linux()
                if idle is not None:
                    return idle
                # Fallback: unknown idle → assume active (0s) and rely on lock/sleep detection
                return datetime.timedelta(seconds=0)
            elif sys.platform == "darwin":
                output = subprocess.check_output(
                    ["ioreg", "-c", "IOHIDSystem"]
                ).decode()
                for line in output.splitlines():
                    if "HIDIdleTime" in line:
                        idle_ns = int(line.split("=")[-1].strip().strip(";"))
                        idle_sec = idle_ns / 1_000_000_000
                        return datetime.timedelta(seconds=idle_sec)
                return datetime.timedelta(seconds=0)
            else:
                logger.warning("Idle time detection not supported on this platform: {}", sys.platform)
                return datetime.timedelta(seconds=0)
        except Exception as e:
            logger.error("Failed to get idle time: {}", e)
            return datetime.timedelta(seconds=0)

    def quit_daemon(self):
        self._daemon_stop_event.set()
        if self.current_session is not None:
            self.end_session()

    def run_daemon(self, poll_interval: float = 5.0, sleep_detection_threshold: float = 30.0):
        """
        Runs the TimeAwareness daemon to monitor activity and manage sessions.

        Args:
            poll_interval (float): How often to check idle time (in seconds).
            sleep_detection_threshold (float): Threshold (in seconds) for detecting system sleep via time gap.
        """
        logger.info("TimeAwareness daemon started. Press Ctrl+C to quit.")
        self._is_active = True
        self._last_check = datetime.datetime.now()
        self._screen_locked = False
        last_uptime = self._get_system_uptime()

        # --- Subscribe to lock and sleep events ---
        if self.monitor_lock_and_sleep:
            self._screen_locked = self._subscribe_lock_events()
            self._subscribe_sleep_events()

        try:
            logger.debug("Entering daemon loop.")
            while not self._daemon_stop_event.is_set():
                # Check for day rollover (safe due to cap)
                self._check_day_rollover()

                now = datetime.datetime.now()
                prev_check = self._last_check
                elapsed = (now - prev_check).total_seconds()

                # Fallback sleep detection using time gap
                if elapsed > sleep_detection_threshold:
                    logger.info("Detected sleep via elapsed gap (elapsed {:.2f}s > {:.2f}s). Ending session (active: {}).",
                                elapsed, sleep_detection_threshold, self._is_active)
                    if self._is_active and self.current_session:
                        # End the session at the last known active time so we don't count sleep
                        self.end_session_at(prev_check)
                    self._is_active = False

                self._last_check = now

                # Detect reboot
                current_uptime = self._get_system_uptime()
                if current_uptime < last_uptime:  # reboot detected
                    logger.info("System reboot detected (uptime: {}).", current_uptime)
                    if self.end_session_on_restart and self.current_session:
                        self.end_session()
                        logger.info("Session ended due to system restart.")
                last_uptime = current_uptime

                # Skip idle checks if locked
                if self.monitor_lock_and_sleep and self._screen_locked:
                    time.sleep(poll_interval)
                    continue

                # Idle-based session control
                idle_time = self.get_idle_time()
                if self._is_active:
                    if idle_time >= self.end_session_idle_threshold:
                        self.end_session()
                        logger.info("Session ended due to inactivity (idle time: {} >= {}).",
                                    idle_time, self.end_session_idle_threshold)
                        self._is_active = False
                else:
                    if idle_time < self.end_session_idle_threshold:
                        self.start_session()
                        logger.info("Session started due to user activity (idle time: {} < {}).",
                                    idle_time, self.end_session_idle_threshold)
                        self._is_active = True

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            if self._is_active:
                self.end_session()
                logger.info("Session ended due to daemon exit.")
            logger.info("TimeAwareness daemon stopped.")
            self.save_state()

    def _subscribe_lock_events(self) -> bool:
        """
        Subscribe to D-Bus signals for screen lock/unlock.
        Returns initial lock state (bool).
        """
        try:
            bus = SessionBus()
        except Exception as e:
            logger.error("Failed to connect to SessionBus: {}", e)
            return False

        # Try GNOME ScreenSaver
        try:
            ss_iface = bus.get("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver")
            self._screen_locked = bool(ss_iface.GetActive())
            logger.info("Using org.gnome.ScreenSaver for lock detection (locked={}).", self._screen_locked)

            def on_active_changed(locked):
                self._handle_lock_event(bool(locked))

            ss_iface.onActiveChanged = on_active_changed
            return self._screen_locked

        except Exception:
            logger.warning("Could not connect to ActiveChanged on org.gnome.ScreenSaver.")

        # Try freedesktop ScreenSaver
        try:
            ss_iface = bus.get("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")
            try:
                self._screen_locked = bool(ss_iface.GetActive())
            except Exception:
                self._screen_locked = bool(getattr(ss_iface, "Active", False))

            logger.info("Using org.freedesktop.ScreenSaver for lock detection (locked={}).", self._screen_locked)

            def on_active_changed(locked):
                self._handle_lock_event(bool(locked))

            try:
                ss_iface.onActiveChanged = on_active_changed
            except Exception:
                logger.warning("Could not connect to ActiveChanged on org.freedesktop.ScreenSaver.")
            return self._screen_locked

        except Exception:
            logger.warning("No ScreenSaver D-Bus interface available; lock detection disabled.")
            return False

    def _handle_lock_event(self, locked: bool):
        """
        Handle lock/unlock events: end session on lock, start session on unlock if idle threshold is met.
        """
        if locked:
            logger.info("Screen locked - ending session immediately (active: {}).", self._is_active)
            if self.current_session:
                self.end_session()
            self._is_active = False
            self._screen_locked = True
        else:
            logger.info("Screen unlocked (active: {}).", self._is_active)
            self._screen_locked = False
            if not self._is_active:
                idle_time = self.get_idle_time()
                if idle_time < self.end_session_idle_threshold:
                    self.start_session()
                    logger.info("Session started after unlock (idle time: {} < {}).",
                                idle_time, self.end_session_idle_threshold)
                    self._is_active = True
                else:
                    logger.info("Screen unlock idle time: {} >= {}.",
                                idle_time, self.end_session_idle_threshold)

    def _subscribe_sleep_events(self):
        """
        Subscribe to D-Bus signals for system sleep/wake.
        """
        try:
            sysbus = SystemBus()
            login1 = sysbus.get("org.freedesktop.login1", "/org/freedesktop/login1")

            def on_prepare_for_sleep(start_sleeping):
                if start_sleeping:
                    logger.info("System preparing for sleep - ending session (active: {}).", self._is_active)
                    if self.current_session:
                        self.end_session()
                    self._is_active = False
                else:
                    logger.info("System resumed from sleep.")

            login1.onPrepareForSleep = on_prepare_for_sleep
            logger.info("Subscribed to org.freedesktop.login1 PrepareForSleep for sleep detection.")
        except Exception:
            logger.warning("Could not subscribe to logind PrepareForSleep; using elapsed-gap detection.")

