import datetime
import subprocess
import time
import sys
from pathlib import Path
from typing import Tuple
from loguru import logger
import threading

from database import (
    save_session, get_session_history,
    set_metadata, get_metadata, get_sessions_since, get_sessions_by_weekday,
    get_all_sessions, get_sessions_for_day, get_previous_session, get_days_tracked, configure_database,
    create_tables_if_not_exist
)

class TimeAwareness:
    def __init__(self,
                 app_dir: Path,
                 end_session_idle_threshold: int = 10,
                 start_daemon: bool = False,
                 poll_interval: float = 5.0):
        """
        Initialize the TimeAwareness instance.

        Args:
            app_dir (Path): Directory for storing state and logs.
            end_session_idle_threshold (int): Idle threshold in minutes to end session.
            start_daemon (bool): If True, start the daemon in a background thread.
            poll_interval (float): Daemon idle check interval (seconds).
        """
        self._setup(app_dir)

        self.current_session = None
        self.end_session_idle_threshold = datetime.timedelta(minutes=end_session_idle_threshold)
        self.today_total = float(get_metadata("today_total", 0))
        self._daemon_stop_event = threading.Event()

        if start_daemon:
            self.daemon_thread = threading.Thread(target=self.run_daemon, args=(poll_interval,), daemon=True)
            self.daemon_thread.start()

    def _setup(self, app_dir: Path):
        """
        Set up logging to a file in the application directory.

        Args:
            app_dir (Path): Directory for log file.
        """
        if not app_dir.exists():
            app_dir.mkdir(parents=True)

        log_path = app_dir / "timeawareness.log"
        logger.add(str(log_path), rotation="10 MB", retention="10 days")
        logger.info("Log file created at {}", log_path)

        db_path = app_dir / "timeawareness.sqlite"
        logger.info("Database path set to {}", db_path)
        configure_database(database=db_path)
        create_tables_if_not_exist()
        logger.info("Database configured and tables checked/created.")

    def save_state(self):
        """
        Persist session state to database.
        """
        saved = set_metadata("today_total", self.today_total)
        if not saved:
            logger.error("Failed to save state to database.")
            raise RuntimeError("Failed to save state.")

    def load_state(self):
        """
        Load session state from database.
        """
        self.today_total = float(get_metadata("today_total", 0))

    def start_session(self):
        """
        Start a new session. Ends any existing session first.
        """
        if self.current_session is not None:
            self.end_session()
        self.current_session = datetime.datetime.now()
        logger.info("Session started at {}", self.current_session)
        self.save_state()

    def end_session(self) -> datetime.timedelta:
        """
        End the current session and record its duration.

        Returns:
            datetime.timedelta: Duration of the ended session.

        Raises:
            ValueError: If no session is currently started.
        """
        if self.current_session is None:
            logger.warning("Attempted to end session, but no session was started.")
            raise ValueError("No session started.")
        end_time = datetime.datetime.now()
        session_duration = end_time - self.current_session
        saved = save_session(self.current_session, end_time, session_duration)
        if not saved:
            logger.error("Failed to save session from {} to {}", self.current_session, end_time)
            raise RuntimeError("Failed to save session.")
        logger.info("Session ended at {} (duration: {})", end_time, session_duration)
        self.current_session = None
        self.today_total += session_duration.total_seconds()
        self.save_state()
        return session_duration

    def current_session_info(self) -> Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]:
        """
        Get information about the current session.

        Returns:
            tuple: (start_time, current_time, duration)

        Raises:
            ValueError: If no session is currently started.
        """
        if self.current_session is None:
            raise ValueError("No session started.")
        now = datetime.datetime.now()
        duration = now - self.current_session
        return self.current_session, now, duration

    def previous_session(self) -> Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]:
        """
        Get the previous session's information.

        Returns:
            tuple: (start_time, end_time, duration)

        Raises:
            ValueError: If no previous sessions exist.
        """
        session = get_previous_session()
        if session is None:
            raise ValueError("No previous sessions.")
        return session

    def days_tracked(self) -> int:
        """
        Get the number of unique days tracked.

        Returns:
            int: Number of days with sessions.
        """
        return get_days_tracked()

    def total_time_today(self) -> datetime.timedelta:
        """
        Get the total time tracked today.

        Returns:
            datetime.timedelta: Total time today.
        """
        return datetime.timedelta(seconds=self.today_total)

    def total_time_yesterday(self) -> datetime.timedelta:
        """
        Get the total time tracked yesterday.

        Returns:
            datetime.timedelta: Total time yesterday.
        """
        yesterday = datetime.datetime.now().date() - datetime.timedelta(days=1)
        history = get_sessions_for_day(yesterday)
        total = sum((duration for start, end, duration in history), datetime.timedelta())
        return total

    def seven_day_average(self) -> datetime.timedelta:
        """
        Get the average session duration over the last seven days.

        Returns:
            datetime.timedelta: Seven-day average duration.
        """
        seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
        history = get_sessions_since(seven_days_ago)
        total = sum((duration for start, end, duration in history), datetime.timedelta())
        days_count = len({start.date() for start, end, duration in history})
        if days_count == 0:
            return datetime.timedelta()
        return total / days_count

    def weekday_average(self) -> datetime.timedelta:
        """
        Get the average session duration per weekday.

        Returns:
            datetime.timedelta: Weekday average duration.
        """
        weekday_histories = get_sessions_by_weekday()
        averages = []
        for durations in weekday_histories.values():
            if durations:
                averages.append(sum(durations, datetime.timedelta()) / len(durations))
        if not averages:
            return datetime.timedelta()
        return sum(averages, datetime.timedelta()) / len(averages)

    def total_average(self) -> datetime.timedelta:
        """
        Get the average session duration over all sessions.

        Returns:
            datetime.timedelta: Total average duration.
        """
        history = get_all_sessions()
        if not history:
            return datetime.timedelta()
        total = sum((duration for start, end, duration in history), datetime.timedelta())
        return total / len(history)

    def history(self):
        """
        Get a summary of session history and statistics.

        Returns:
            dict: Dictionary with days tracked, totals, averages, and session history.
        """
        history = get_session_history()
        return {
            "days": self.days_tracked(),
            "total_today": self.total_time_today(),
            "total_yesterday": self.total_time_yesterday(),
            "seven_day_average": self.seven_day_average(),
            "weekday_average": self.weekday_average(),
            "total_average": self.total_average(),
            "history": history,
        }

    def get_idle_time(self) -> datetime.timedelta:
        """
        Returns the idle time (no mouse/keyboard activity).

        Returns:
            datetime.timedelta: Idle time.

        Supports Linux (xprintidle) and macOS (ioreg).
        """
        try:
            if sys.platform.startswith("linux"):
                idle_ms = int(subprocess.check_output(['xprintidle']).decode().strip())
                return datetime.timedelta(milliseconds=idle_ms)
            elif sys.platform == "darwin":
                # macOS: get idle time in seconds
                output = subprocess.check_output(
                    ["ioreg", "-c", "IOHIDSystem"]
                ).decode()
                for line in output.splitlines():
                    if "HIDIdleTime" in line:
                        # Extract the number after '=' and before ';'
                        idle_ns = int(line.split("=")[-1].strip().strip(";"))
                        idle_sec = idle_ns / 1_000_000_000
                        return datetime.timedelta(seconds=idle_sec)
                # If not found, assume not idle
                return datetime.timedelta(seconds=0)
            else:
                logger.warning("Idle time detection not supported on this platform: {}", sys.platform)
                return datetime.timedelta(seconds=0)
        except Exception as e:
            logger.error("Failed to get idle time: {}", e)
            return datetime.timedelta(seconds=0)

    def quit_daemon(self):
        """Signal the daemon thread to exit and end any active session."""
        self._daemon_stop_event.set()
        if self.current_session is not None:
            try:
                self.end_session()
            except Exception as e:
                logger.error("Error ending session during quit_daemon: {}", e)

    def run_daemon(self, poll_interval: float = 5.0):
        """
        Runs the time awareness daemon in the background.
        Starts/ends sessions based on user activity.

        Args:
            poll_interval (float): Time in seconds between idle checks.
        """
        logger.info("TimeAwareness daemon started. Press Ctrl+C to quit.")
        is_active = False
        try:
            while not self._daemon_stop_event.is_set():
                idle_time = self.get_idle_time()
                if is_active:
                    if idle_time >= self.end_session_idle_threshold:
                        self.end_session()
                        logger.info("Session ended due to inactivity ({}).", idle_time)
                        is_active = False
                else:
                    if idle_time < self.end_session_idle_threshold:
                        self.start_session()
                        logger.info("Session started due to user activity.")
                        is_active = True
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            if is_active:
                self.end_session()
                logger.info("Session ended due to daemon exit.")
            logger.info("TimeAwareness daemon stopped.")
            self.save_state()
