import datetime
import subprocess
import time
import sys
from pathlib import Path
from typing import Optional, Tuple
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
    get_sessions_for_day, get_previous_session, get_days_tracked, configure_database,
    create_tables_if_not_exist,
    reset_database
)


# -------------------------
# SystemMonitor
# -------------------------
class SystemMonitor:
    """
    Handles system-level monitoring such as uptime, idle time, and D-Bus events
    for lock/unlock and sleep/resume signals.
    """

    def __init__(self):
        self.screen_locked = False

    def get_system_uptime(self) -> float:
        try:
            if sys.platform.startswith("linux"):
                with open("/proc/uptime") as f:
                    return float(f.readline().split()[0])
            elif sys.platform == "darwin":
                output = subprocess.check_output(["sysctl", "-n", "kern.boottime"]).decode()
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
                logger.error("System uptime not supported on this platform: {}", sys.platform)
                return 0.0
        except Exception as e:
            logger.error("Failed to read system uptime: {}", e)
            return 0.0

    def get_idle_time(self) -> datetime.timedelta:
        try:
            if sys.platform.startswith("linux"):
                idle = self._get_idle_time_linux()
                if idle is not None:
                    return idle
                logger.warning("Idle detection unavailable, assuming active.")
                return datetime.timedelta(seconds=0)
            elif sys.platform == "darwin":
                output = subprocess.check_output(["ioreg", "-c", "IOHIDSystem"]).decode()
                for line in output.splitlines():
                    if "HIDIdleTime" in line:
                        idle_ns = int(line.split("=")[-1].strip().strip(";"))
                        idle_sec = idle_ns / 1_000_000_000
                        return datetime.timedelta(seconds=idle_sec)
                return datetime.timedelta(seconds=0)
            else:
                logger.error("Idle time detection not supported on this platform: {}", sys.platform)
                return datetime.timedelta(seconds=0)
        except Exception as e:
            logger.error("Failed to get idle time: {}", e)
            return datetime.timedelta(seconds=0)

    def _get_idle_time_linux(self) -> Optional[datetime.timedelta]:
        try:
            bus = SessionBus()
            idle_monitor = bus.get("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core")
            idle_time_ms = idle_monitor.GetIdletime()
            return datetime.timedelta(microseconds=idle_time_ms)
        except Exception:
            pass
        try:
            bus = SessionBus()
            ss = bus.get("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")
            if hasattr(ss, "GetSessionIdleTime"):
                idle_seconds = ss.GetSessionIdleTime()
                return datetime.timedelta(seconds=float(idle_seconds))
            if hasattr(ss, "IdleTime"):
                idle_seconds = ss.IdleTime
                return datetime.timedelta(seconds=float(idle_seconds))
        except Exception:
            pass
        return None

    def subscribe_lock_events(self, lock_handler_fct=None):
        try:
            bus = SessionBus()
        except Exception as e:
            logger.error("Failed to connect to SessionBus: {}", e)
            return False

        try:
            ss_iface = bus.get("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver")
            self.screen_locked = bool(ss_iface.GetActive())
            logger.info("Using org.gnome.ScreenSaver for lock detection (locked={}).", self.screen_locked)

            def on_active_changed(locked):
                self.screen_locked = bool(locked)
                logger.info("Screen lock state changed: {}", self.screen_locked)
                if lock_handler_fct is not None:
                    lock_handler_fct(bool(locked))

            ss_iface.onActiveChanged = on_active_changed
            return self.screen_locked
        except Exception:
            logger.warning("Could not connect to ActiveChanged on org.gnome.ScreenSaver.")

        try:
            ss_iface = bus.get("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")
            try:
                self.screen_locked = bool(ss_iface.GetActive())
            except Exception:
                self.screen_locked = bool(getattr(ss_iface, "Active", False))

            logger.info("Using org.freedesktop.ScreenSaver for lock detection (locked={}).", self.screen_locked)

            def on_active_changed(locked):
                self.screen_locked = bool(locked)
                logger.info("Screen lock state changed: {}", self.screen_locked)
                if lock_handler_fct is not None:
                    lock_handler_fct(bool(locked))

            try:
                ss_iface.onActiveChanged = on_active_changed
            except Exception:
                logger.warning("Could not connect to ActiveChanged on org.freedesktop.ScreenSaver.")
            return self.screen_locked
        except Exception:
            logger.warning("No ScreenSaver D-Bus interface available; lock detection disabled.")
            return False

    def subscribe_sleep_events(self):
        try:
            sysbus = SystemBus()
            login1 = sysbus.get("org.freedesktop.login1", "/org/freedesktop/login1")

            def on_prepare_for_sleep(start_sleeping):
                if start_sleeping:
                    logger.info("System preparing for sleep.")
                else:
                    logger.info("System resumed from sleep.")

            login1.onPrepareForSleep = on_prepare_for_sleep
            logger.info("Subscribed to org.freedesktop.login1 PrepareForSleep for sleep detection.")
        except Exception:
            logger.warning("Could not subscribe to logind PrepareForSleep; using elapsed-gap detection.")


# -------------------------
# SessionManager
# -------------------------
class SessionManager:
    def __init__(self):
        self.current_session = None  # datetime.datetime.now
        self.today_total = 0  # seconds
        self._last_update_date = None  # datetime.date.today
        self._lock = threading.RLock()
        self._last_save_time = 0  # seconds
        self._save_interval = 30  # seconds

    def start_session(self):
        with self._lock:
            if self.current_session is not None:
                duration = datetime.datetime.now() - self.current_session
                if duration.total_seconds() < 1:
                    logger.warning("Skipping new session, too close to last one.")
                    return
                self.end_session()

            self.current_session = datetime.datetime.now()
            self._last_update_date = datetime.date.today()
            logger.info("Session started at {}", self.current_session)

            self.save_state()

    def end_session(self) -> Optional[datetime.timedelta]:
        with self._lock:
            if self.current_session is None:
                logger.warning("Attempted to end session, but no session was started.")
                return None

            end_time = datetime.datetime.now()
            session_duration = end_time - self.current_session
            if session_duration.total_seconds() > 0:
                saved = save_session(self.current_session, end_time, session_duration)
                if not saved:
                    logger.error("Failed to save session from {} to {}", self.current_session, end_time)
                    return None

            logger.info("Session ended at {} (duration: {})", end_time, session_duration)
            self.current_session = None
            self.today_total += session_duration.total_seconds()

            self.save_state()

            return session_duration

    def end_session_at(self, end_time: datetime.datetime) -> Optional[datetime.timedelta]:
        with self._lock:
            if self.current_session is None:
                logger.warning("Attempted to end session at {}, but no session was started.", end_time)
                return None

            if end_time < self.current_session:
                logger.warning("end_session_at called with end_time before current_session; clamping.")
                end_time = self.current_session

            session_duration = end_time - self.current_session
            if session_duration.total_seconds() > 0:
                saved = save_session(self.current_session, end_time, session_duration)
                if not saved:
                    logger.error("Failed to save session from {} to {}", self.current_session, end_time)
                    return None

            logger.info("Session ended at {} (duration: {}) [end_session_at]", end_time, session_duration)
            self.current_session = None

            today = datetime.date.today()
            if end_time.date() == today:
                self.today_total += session_duration.total_seconds()

            self.save_state()

            return session_duration

    def save_state(self):
        now = time.time()
        if now - self._last_save_time < self._save_interval:
            return
        self._last_save_time = now

        with self._lock:
            set_metadata("today_total", self.today_total)

            last_update_date = self._last_update_date.isoformat() if self._last_update_date else ""
            set_metadata("last_update_date", last_update_date)

            current_session = self.current_session.isoformat() if self.current_session else ""
            set_metadata("current_session", current_session)

    def load_state(self):
        self.today_total = float(get_metadata("today_total") or 0)

        try:
            last_date_str = get_metadata("last_update_date", "")
            self._last_update_date = datetime.date.fromisoformat(last_date_str)
        except Exception as e:
            logger.error("Failed to parse last_update_date from metadata: {}", e)
            self._last_update_date = None

        try:
            session_str = get_metadata("current_session", "")
            self.current_session = datetime.datetime.fromisoformat(session_str)
        except Exception as e:
            logger.error("Failed to parse current_session from metadata: {}", e)
            self.current_session = None

    def check_day_rollover(self):
        today = datetime.date.today()
        if self._last_update_date is not None and today != self._last_update_date:
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
                    logger.info("Skipped overlap from ongoing session: {} seconds exceeds cap (likely slept)",
                                elapsed_since_midnight)

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

    def reset(self):
        self.today_total = 0
        self.current_session = None
        self._last_update_date = None


# -------------------------
# Daemon
# -------------------------
class Daemon:
    def __init__(self, session_manager: SessionManager, system_monitor: SystemMonitor,
                 monitor_lock_and_sleep: bool = True, end_session_on_restart: bool = False,
                 end_session_idle_threshold: int = 10, boot_detection_limit: int = 120):
        self._session_manager = session_manager
        self._system_monitor = system_monitor
        self._daemon_stop_event = threading.Event()
        self._is_active = False
        self._last_check = None  # datetime.datetime.now
        self._monitor_lock_and_sleep = monitor_lock_and_sleep
        self._end_session_on_restart = end_session_on_restart
        self._end_session_idle_threshold = datetime.timedelta(minutes=end_session_idle_threshold)  # minutes
        self._boot_detection_limit = boot_detection_limit  # seconds

    def _handle_lock_event(self, locked: bool):
        """
        Handle lock/unlock events: end session on lock, start session on unlock if idle threshold is met.
        """
        if locked:
            logger.info("Screen locked - ending session immediately (active: {}).", self._is_active)
            if self._session_manager.current_session:
                self._session_manager.end_session()
            self._is_active = False
        else:
            logger.info("Screen unlocked (active: {}).", self._is_active)
            if not self._is_active:
                idle_time = self._system_monitor.get_idle_time()
                if idle_time < self._end_session_idle_threshold:
                    self._session_manager.start_session()
                    logger.info("Session started after unlock (idle time: {} < {}).",
                                idle_time, self._end_session_idle_threshold)
                    self._is_active = True
                else:
                    logger.info("Screen unlock idle time: {} >= {}.",
                                idle_time, self._end_session_idle_threshold)

    def _is_fresh_boot(self, uptime: float) -> bool:
        """
        Determine if the current startup is a fresh boot (cold boot) vs. a warm reboot.
        """
        boot_time = datetime.datetime.now() - datetime.timedelta(seconds=uptime)
        last_seen_str = get_metadata("last_seen_time", "")
        last_seen_time = None
        if last_seen_str:
            try:
                last_seen_time = datetime.datetime.fromisoformat(last_seen_str)
            except Exception:
                logger.warning("Could not parse last_seen_time: {}", last_seen_str)

        if uptime < self._boot_detection_limit:
            if not last_seen_time or (boot_time - last_seen_time) > datetime.timedelta(minutes=10):
                return True
        return False

    def run(self, poll_interval: float = 5.0, sleep_detection_threshold: float = 30.0, verbose: bool = False):
        logger.info("TimeAwareness daemon started. Press Ctrl+C to quit.")
        self._is_active = True
        last_uptime = self._system_monitor.get_system_uptime()

        logger.info(f"System uptime: {datetime.timedelta(seconds=last_uptime)}")

        if self._is_fresh_boot(last_uptime):
            logger.info("Fresh boot detected (uptime {:.2f}s).", last_uptime)
            self._session_manager.current_session = None
            self._session_manager.start_session()
        elif self._is_active and self._session_manager.current_session is None:
            self._session_manager.start_session()

        if self._monitor_lock_and_sleep:
            self._system_monitor.subscribe_lock_events(self._handle_lock_event)
            self._system_monitor.subscribe_sleep_events()

        try:
            logger.debug("Entering daemon loop.")
            while not self._daemon_stop_event.is_set():
                self._session_manager.check_day_rollover()

                now = datetime.datetime.now()
                prev_check = self._last_check or datetime.datetime.now()
                elapsed = (now - prev_check).total_seconds()

                if sleep_detection_threshold < elapsed < 24 * 3600:
                    logger.info("Detected sleep via elapsed gap (elapsed {:.2f}s > {:.2f}s). Ending session (active: {}).",
                                elapsed, sleep_detection_threshold, self._is_active)
                    if self._is_active and self._session_manager.current_session:
                        self._session_manager.end_session_at(prev_check)
                    self._is_active = False
                self._last_check = now

                current_uptime = self._system_monitor.get_system_uptime()
                if current_uptime < last_uptime:
                    logger.info("System reboot detected (uptime: {}).", current_uptime)
                    if self._end_session_on_restart and self._session_manager.current_session:
                        self._session_manager.end_session()
                        logger.info("Session ended due to system restart.")
                last_uptime = current_uptime

                if self._monitor_lock_and_sleep and self._system_monitor.screen_locked:
                    time.sleep(poll_interval)
                    set_metadata("last_seen_time", datetime.datetime.now().isoformat())
                    continue

                idle_time = self._system_monitor.get_idle_time()
                if verbose:
                    logger.debug("Idle time: {} (active: {})", idle_time, self._is_active)

                if self._is_active:
                    if idle_time >= self._end_session_idle_threshold:
                        self._session_manager.end_session()
                        logger.info("Session ended due to inactivity (idle time: {} >= {}).",
                                    idle_time, self._end_session_idle_threshold)
                        self._is_active = False
                else:
                    if idle_time < self._end_session_idle_threshold:
                        self._session_manager.start_session()
                        logger.info("Session started due to user activity (idle time: {} < {}).",
                                    idle_time, self._end_session_idle_threshold)
                        self._is_active = True

                set_metadata("last_seen_time", datetime.datetime.now().isoformat())
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        logger.info("Stopping daemon...")
        self._daemon_stop_event.set()

        if self._is_active:
            self._session_manager.end_session()
            logger.info("Session ended due to daemon stop.")

        self._session_manager.save_state()
        set_metadata("last_seen_time", datetime.datetime.now().isoformat())
        logger.info("Daemon stopped.")


# -------------------------
# Main Wrapper App
# -------------------------
class TimeAwareness:
    def __init__(self, app_dir: Path, start_daemon: bool = False, log_to_terminal: bool = False):
        self._setup_logging_and_db(app_dir, log_to_terminal)

        self._session_manager = SessionManager()
        self._system_monitor = SystemMonitor()
        self._daemon = Daemon(self._session_manager, self._system_monitor)

        self._session_manager.load_state()

        self._daemon_thread = None
        if start_daemon:
            self._daemon_thread = threading.Thread(target=self._daemon.run, daemon=True)
            self._daemon_thread.start()

        logger.info("TimeAwarenessApp initialized.")

    def _setup_logging_and_db(self, app_dir: Path, log_to_terminal: bool = False):
        logging.getLogger("peewee").setLevel(logging.CRITICAL)

        if not app_dir.exists():
            app_dir.mkdir(parents=True)

        log_path = app_dir / "timeawareness.log"
        logger.add(str(log_path), rotation="10 MB", retention="10 days")
        if not log_to_terminal:
            logger.remove(0)

        db_path = app_dir / "timeawareness.sqlite"
        configure_database(database=db_path)
        create_tables_if_not_exist()

    def start_session(self):
        return self._session_manager.start_session()

    def end_session(self):
        return self._session_manager.end_session()

    def current_session_info(self, verbose: bool = True) -> Optional[
        Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]]:
        if self._session_manager.current_session is None:
            if verbose:
                logger.warning("No session started.")
            return None
        now = datetime.datetime.now()
        duration = now - self._session_manager.current_session
        return self._session_manager.current_session, now, duration

    def previous_session(self, verbose: bool = True):
        return get_previous_session(verbose)

    def days_tracked(self):
        return get_days_tracked()

    def total_time_today(self):
        return datetime.timedelta(seconds=self._session_manager.today_total)

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
        history = get_sessions()
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

    def reset(self):
        reset_database()
        self._session_manager.reset()
        logger.info("Database reset: all data cleared.")
        self.start_session()

    def stop_daemon(self):
        if self._daemon_thread and self._daemon_thread.is_alive():
            self._daemon.stop()
            self._daemon_thread.join(timeout=5)
            logger.info("Daemon thread joined successfully.")
        else:
            logger.info("No active daemon thread to stop.")
