import datetime
import subprocess
import time
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from loguru import logger
import threading
import logging

try:
    from pydbus import SessionBus, SystemBus
except Exception as e:
    SessionBus = None
    SystemBus = None
    logger.warning("pydbus not available; lock and sleep detection disabled: {}", e)

try:
    from gi.repository import GLib
except Exception:
    GLib = None

from database import (
    save_session, get_sessions,
    set_metadata, get_metadata, get_sessions_since, get_sessions_by_weekday,
    get_sessions_for_day, get_previous_session, get_days_tracked, configure_database,
    create_tables_if_not_exist,
    reset_database
)


def _monotonic_time() -> float:
    """
    Monotonic clock for measuring gaps between daemon iterations.

    CLOCK_BOOTTIME keeps counting while the system is suspended, so a suspend
    shows up as a gap; time.monotonic() (CLOCK_MONOTONIC) stops during suspend
    and would hide it. Falls back to time.monotonic() where unavailable.
    """
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError):
        return time.monotonic()


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
        self._session_bus = None
        self._idle_reader = None
        # References to D-Bus proxies must be kept alive: pydbus signal
        # subscriptions are dropped when the proxy object is garbage collected.
        self._lock_iface = None
        self._login1 = None

    def _get_session_bus(self):
        if SessionBus is None:
            raise RuntimeError("pydbus not available")
        if self._session_bus is None:
            self._session_bus = SessionBus()
        return self._session_bus

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
        # Reuse the resolved D-Bus proxy; creating one involves a synchronous
        # introspection round-trip and this runs on every poll.
        if self._idle_reader is not None:
            try:
                return self._idle_reader()
            except Exception:
                logger.warning("Idle-time D-Bus proxy failed; re-resolving.")
                self._idle_reader = None

        self._idle_reader = self._resolve_idle_reader()
        if self._idle_reader is None:
            return None
        try:
            return self._idle_reader()
        except Exception as e:
            logger.warning("Idle-time D-Bus call failed: {}", e)
            self._idle_reader = None
            return None

    def _resolve_idle_reader(self) -> Optional[Callable[[], datetime.timedelta]]:
        try:
            bus = self._get_session_bus()
            idle_monitor = bus.get("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core")
            # GetIdletime returns milliseconds.
            reader = lambda: datetime.timedelta(milliseconds=idle_monitor.GetIdletime())
            reader()  # probe
            logger.info("Using org.gnome.Mutter.IdleMonitor for idle detection.")
            return reader
        except Exception:
            pass
        try:
            bus = self._get_session_bus()
            ss = bus.get("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")
            if hasattr(ss, "GetSessionIdleTime"):
                reader = lambda: datetime.timedelta(seconds=float(ss.GetSessionIdleTime()))
                reader()  # probe
                logger.info("Using org.freedesktop.ScreenSaver.GetSessionIdleTime for idle detection.")
                return reader
            if hasattr(ss, "IdleTime"):
                reader = lambda: datetime.timedelta(seconds=float(ss.IdleTime))
                reader()  # probe
                logger.info("Using org.freedesktop.ScreenSaver.IdleTime for idle detection.")
                return reader
        except Exception:
            pass
        return None

    def subscribe_lock_events(self, lock_handler_fct=None):
        try:
            bus = self._get_session_bus()
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
            self._lock_iface = ss_iface
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
                self._lock_iface = ss_iface
            except Exception:
                logger.warning("Could not connect to ActiveChanged on org.freedesktop.ScreenSaver.")
            return self.screen_locked
        except Exception:
            logger.warning("No ScreenSaver D-Bus interface available; lock detection disabled.")
            return False

    def subscribe_sleep_events(self, sleep_handler_fct=None):
        try:
            sysbus = SystemBus()
            login1 = sysbus.get("org.freedesktop.login1", "/org/freedesktop/login1")

            def on_prepare_for_sleep(start_sleeping):
                if start_sleeping:
                    logger.info("System preparing for sleep.")
                else:
                    logger.info("System resumed from sleep.")
                if sleep_handler_fct is not None:
                    sleep_handler_fct(bool(start_sleeping))

            login1.onPrepareForSleep = on_prepare_for_sleep
            self._login1 = login1
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

    @staticmethod
    def _split_at_midnight(start: datetime.datetime,
                           end: datetime.datetime) -> List[Tuple[datetime.datetime, datetime.datetime]]:
        """
        Split a (start, end) interval into per-day segments at midnight so that
        no saved session ever spans a day boundary. Zero-length segments are dropped.
        """
        segments = []
        cursor = start
        while cursor.date() < end.date():
            next_midnight = datetime.datetime.combine(
                cursor.date() + datetime.timedelta(days=1), datetime.time.min)
            segments.append((cursor, next_midnight))
            cursor = next_midnight
        segments.append((cursor, end))
        return [(s, e) for s, e in segments if (e - s).total_seconds() > 0]

    def start_session(self):
        with self._lock:
            if self.current_session is not None:
                duration = datetime.datetime.now() - self.current_session
                if duration.total_seconds() < 1:
                    logger.warning("Skipping new session, too close to last one.")
                    return
                self.end_session()

            self.current_session = datetime.datetime.now()
            logger.info("Session started at {}", self.current_session)

            self.save_state()

    def end_session(self) -> Optional[datetime.timedelta]:
        return self.end_session_at(datetime.datetime.now())

    def end_session_at(self, end_time: datetime.datetime) -> Optional[datetime.timedelta]:
        with self._lock:
            if self.current_session is None:
                logger.warning("Attempted to end session at {}, but no session was started.", end_time)
                return None

            if end_time < self.current_session:
                logger.warning("end_session_at called with end_time before current_session; clamping.")
                end_time = self.current_session

            self.check_day_rollover()

            session_duration = end_time - self.current_session
            segments = self._split_at_midnight(self.current_session, end_time)
            for seg_start, seg_end in segments:
                if not save_session(seg_start, seg_end, seg_end - seg_start):
                    logger.error("Failed to save session from {} to {}", seg_start, seg_end)
                    return None

            logger.info("Session ended at {} (duration: {})", end_time, session_duration)
            self.current_session = None

            # Only the portion of the session that falls on today counts towards
            # today's total; earlier segments belong to previous days.
            today = datetime.date.today()
            for seg_start, seg_end in segments:
                if seg_start.date() == today:
                    self.today_total += (seg_end - seg_start).total_seconds()

            self.save_state()

            return session_duration

    def save_state(self):
        with self._lock:
            set_metadata("today_total", self.today_total)

            last_update_date = self._last_update_date.isoformat() if self._last_update_date else ""
            set_metadata("last_update_date", last_update_date)

            current_session = self.current_session.isoformat() if self.current_session else ""
            set_metadata("current_session", current_session)

    def load_state(self):
        try:
            self.today_total = float(get_metadata("today_total") or 0)
        except (TypeError, ValueError) as e:
            logger.error("Failed to parse today_total from metadata: {}", e)
            self.today_total = 0

        self._last_update_date = None
        last_date_str = get_metadata("last_update_date", "") or ""
        if last_date_str:
            try:
                self._last_update_date = datetime.date.fromisoformat(last_date_str)
            except ValueError as e:
                logger.error("Failed to parse last_update_date from metadata: {}", e)

        self.current_session = None
        session_str = get_metadata("current_session", "") or ""
        if session_str:
            try:
                self.current_session = datetime.datetime.fromisoformat(session_str)
            except ValueError as e:
                logger.error("Failed to parse current_session from metadata: {}", e)

    def check_day_rollover(self):
        with self._lock:
            today = datetime.date.today()
            if self._last_update_date == today:
                return

            if self._last_update_date is not None:
                logger.info("New day detected. Recalculating today's total from saved sessions.")

            # Sessions are saved split at midnight, so summing today's saved
            # sessions gives the exact total for the new day (usually zero).
            history = get_sessions_for_day(today)
            self.today_total = sum((duration.total_seconds() for _, _, duration in history), 0.0)

            self._last_update_date = today
            self.save_state()

    def reset(self):
        with self._lock:
            self.today_total = 0
            self.current_session = None
            self._last_update_date = None


# -------------------------
# Daemon
# -------------------------
class Daemon:
    def __init__(self, session_manager: SessionManager, system_monitor: SystemMonitor,
                 monitor_lock_and_sleep: bool = True, end_session_idle_threshold: int = 10,
                 pump_glib_events: bool = False):
        self._session_manager = session_manager
        self._system_monitor = system_monitor
        self._daemon_stop_event = threading.Event()
        self._is_active = False
        self._last_check = None  # datetime.datetime.now
        self._last_check_monotonic = None  # _monotonic_time()
        self._monitor_lock_and_sleep = monitor_lock_and_sleep
        self._end_session_idle_threshold = datetime.timedelta(minutes=end_session_idle_threshold)  # minutes
        # Only for standalone (CLI) mode, where no GLib main loop runs to
        # dispatch D-Bus signals. Must stay off in the tray app: the GTK main
        # loop owns the default context there.
        self._pump_glib_events_enabled = pump_glib_events

    def set_active(self, active: bool):
        """Sync the daemon's activity flag with externally triggered session changes."""
        self._is_active = active

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

    def _handle_sleep_event(self, start_sleeping: bool):
        """
        Handle logind PrepareForSleep: end the session when suspending, and start
        a new one on resume if the screen is unlocked and the user is active.
        """
        if start_sleeping:
            logger.info("System preparing for sleep - ending session (active: {}).", self._is_active)
            if self._session_manager.current_session:
                self._session_manager.end_session()
            self._is_active = False
        else:
            logger.info("System resumed from sleep (active: {}).", self._is_active)
            if not self._is_active and not self._system_monitor.screen_locked:
                idle_time = self._system_monitor.get_idle_time()
                if idle_time < self._end_session_idle_threshold:
                    self._session_manager.start_session()
                    logger.info("Session started after resume (idle time: {} < {}).",
                                idle_time, self._end_session_idle_threshold)
                    self._is_active = True

    def _recover_stale_session(self, uptime: float):
        """
        Handle a session left open by a previous run (crash, shutdown, reboot).

        Uses last_seen_time (written every poll) to distinguish the cases:
        - Machine rebooted since we last ran (boot time is after last_seen_time):
          the machine was off, so close the stale session at last_seen_time.
        - Same boot, app was gone only briefly (e.g. update/restart): resume the session.
        - Same boot, app was gone for a long time: close the session at last_seen_time.
        """
        stale_start = self._session_manager.current_session
        if stale_start is None:
            return

        now = datetime.datetime.now()
        boot_time = now - datetime.timedelta(seconds=uptime)

        last_seen_time = None
        last_seen_str = get_metadata("last_seen_time", "") or ""
        if last_seen_str:
            try:
                last_seen_time = datetime.datetime.fromisoformat(last_seen_str)
            except ValueError:
                logger.warning("Could not parse last_seen_time: {}", last_seen_str)

        if last_seen_time is None or last_seen_time < stale_start:
            # No usable record of when the previous run stopped; closing at the
            # session's own start discards it without inventing phantom time.
            logger.warning("Stale session from {} has no usable last_seen_time; discarding it.", stale_start)
            self._session_manager.end_session_at(stale_start)
            return

        gap = now - last_seen_time
        if boot_time > last_seen_time:
            logger.info("Reboot/shutdown detected (booted {} after last seen {}). "
                        "Closing previous session at last seen time.", boot_time, last_seen_time)
            self._session_manager.end_session_at(last_seen_time)
        elif gap > self._end_session_idle_threshold:
            logger.info("App was not running for {}; closing previous session at last seen time.", gap)
            self._session_manager.end_session_at(last_seen_time)
        else:
            logger.info("Resuming session started at {} (app restarted after {}).", stale_start, gap)

    def _pump_glib_events(self):
        """
        Dispatch pending GLib events so pydbus signal callbacks (lock/sleep) fire
        even when no GLib main loop is running (CLI daemon mode).
        """
        if not self._pump_glib_events_enabled or GLib is None:
            return
        try:
            context = GLib.MainContext.default()
            if context.acquire():
                try:
                    while context.pending():
                        context.iteration(False)
                finally:
                    context.release()
        except Exception as e:
            logger.debug("Failed to pump GLib events: {}", e)

    def run(self, poll_interval: float = 5.0, sleep_detection_threshold: float = 30.0, verbose: bool = False):
        logger.info("TimeAwareness daemon started. Press Ctrl+C to quit.")
        uptime = self._system_monitor.get_system_uptime()
        logger.info(f"System uptime: {datetime.timedelta(seconds=uptime)}")

        self._recover_stale_session(uptime)
        self._session_manager.check_day_rollover()

        locked = False
        if self._monitor_lock_and_sleep:
            locked = bool(self._system_monitor.subscribe_lock_events(self._handle_lock_event))
            self._system_monitor.subscribe_sleep_events(self._handle_sleep_event)

        if locked:
            logger.info("Screen is locked at startup; session will start on unlock.")
            self._is_active = False
            if self._session_manager.current_session:
                self._session_manager.end_session()
        else:
            self._is_active = True
            if self._session_manager.current_session is None:
                self._session_manager.start_session()

        try:
            logger.debug("Entering daemon loop.")
            while not self._daemon_stop_event.is_set():
                now = datetime.datetime.now()
                now_monotonic = _monotonic_time()

                # Suspend/freeze detection via the gap between loop iterations.
                # Measured on a suspend-aware monotonic clock so wall-clock
                # adjustments (NTP, DST) cannot fake or hide a sleep.
                if self._last_check_monotonic is not None:
                    elapsed = now_monotonic - self._last_check_monotonic
                    if elapsed > sleep_detection_threshold:
                        logger.info("Detected sleep via elapsed gap (elapsed {:.2f}s > {:.2f}s). "
                                    "Ending session (active: {}).",
                                    elapsed, sleep_detection_threshold, self._is_active)
                        if self._session_manager.current_session:
                            self._session_manager.end_session_at(self._last_check)
                        self._is_active = False
                self._last_check = now
                self._last_check_monotonic = now_monotonic

                self._session_manager.check_day_rollover()

                self._pump_glib_events()

                if not (self._monitor_lock_and_sleep and self._system_monitor.screen_locked):
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
                self._daemon_stop_event.wait(poll_interval)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        logger.info("Stopping daemon...")
        self._daemon_stop_event.set()

        if self._session_manager.current_session:
            self._session_manager.end_session()
            logger.info("Session ended due to daemon stop.")
        self._is_active = False

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
            try:
                logger.remove(0)
            except ValueError:
                pass

        db_path = app_dir / "timeawareness.sqlite"
        configure_database(database=db_path)
        create_tables_if_not_exist()

    def start_session(self):
        result = self._session_manager.start_session()
        self._daemon.set_active(True)
        return result

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
        self._session_manager.check_day_rollover()
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
