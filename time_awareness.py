import datetime
import subprocess
import time
import sys
import pickle
from pathlib import Path
from typing import Tuple
from loguru import logger
import threading


class TimeAwareness:
    def __init__(self, app_dir: Path,
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
        self.current_session = None
        self.session_history = []
        self.today_total = 0
        self.end_session_idle_threshold = datetime.timedelta(minutes=end_session_idle_threshold)
        if not app_dir.exists():
            app_dir.mkdir(parents=True)
        self._setup_logging(app_dir)  # <-- moved logging setup here
        self.state_path = app_dir / "state.pkl"
        self.load_state()
        if start_daemon:
            self.daemon_thread = threading.Thread(target=self.run_daemon, args=(poll_interval,), daemon=True)
            self.daemon_thread.start()

    def _setup_logging(self, app_dir: Path):
        """
        Set up logging to a file in the application directory.

        Args:
            app_dir (Path): Directory for log file.
        """
        log_path = app_dir / "timeawareness.log"
        logger.remove()
        logger.add(str(log_path), rotation="10 MB", retention="10 days")
        logger.info("TimeAwareness initialized. Logging to {}", log_path)

    def _serialize_session(self, session):
        """
        Convert a session tuple to a serializable form.

        Args:
            session (tuple): (start, end, duration) tuple.

        Returns:
            tuple: (start_iso, end_iso, duration_seconds)
        """
        # Convert session tuple (start, end, duration) to serializable form
        start, end, duration = session
        return (
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            duration.total_seconds() if duration else None,
        )

    def _deserialize_session(self, session):
        """
        Convert a serialized session tuple back to datetime objects.

        Args:
            session (tuple): (start_iso, end_iso, duration_seconds)

        Returns:
            tuple: (start_datetime, end_datetime, duration_timedelta)
        """
        # Convert from serializable form back to (datetime, datetime, timedelta)
        start, end, duration = session
        return (
            datetime.datetime.fromisoformat(start) if start else None,
            datetime.datetime.fromisoformat(end) if end else None,
            datetime.timedelta(seconds=duration) if duration is not None else None,
        )

    def save_state(self):
        """
        Persist session state to disk.
        """
        # Serialize session_history and current_session
        state = {
            "current_session": self.current_session.isoformat() if self.current_session else None,
            "session_history": [self._serialize_session(s) for s in self.session_history],
            "today_total": self.today_total,
        }
        with open(self.state_path, "wb") as f:
            pickle.dump(state, f)

    def load_state(self):
        """
        Load session state from disk.
        """
        if self.state_path.exists():
            with open(self.state_path, "rb") as f:
                state = pickle.load(f)
                cs = state.get("current_session")
                self.current_session = datetime.datetime.fromisoformat(cs) if cs else None
                self.session_history = [self._deserialize_session(s) for s in state.get("session_history", [])]
                self.today_total = state.get("today_total", 0)

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
        self.session_history.append((self.current_session, end_time, session_duration))
        logger.info("Session ended at {} (duration: {})", end_time, session_duration)
        self.current_session = None
        self.today_total += session_duration.total_seconds()
        self.save_state()
        return session_duration

    def get_current_session(self) -> Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]:
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
        if not self.session_history:
            raise ValueError("No previous sessions.")
        return self.session_history[-1]

    def days_tracked(self) -> int:
        """
        Get the number of unique days tracked.

        Returns:
            int: Number of days with sessions.
        """
        return len({start.date() for start, end, duration in self.session_history})

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
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        total = sum((duration for start, end, duration in self.session_history if start.date() == yesterday.date()), datetime.timedelta())
        return total

    def seven_day_average(self) -> datetime.timedelta:
        """
        Get the average session duration over the last seven days.

        Returns:
            datetime.timedelta: Seven-day average duration.
        """
        seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
        total = sum((duration for start, end, duration in self.session_history if start.date() >= seven_days_ago.date()), datetime.timedelta())
        days_count = len({start.date() for start, end, duration in self.session_history if start.date() >= seven_days_ago.date()})
        if days_count == 0:
            return datetime.timedelta()
        return total / days_count

    def weekday_average(self) -> datetime.timedelta:
        """
        Get the average session duration per weekday.

        Returns:
            datetime.timedelta: Weekday average duration.
        """
        weekday_totals = {}
        for start, end, duration in self.session_history:
            weekday = start.weekday()
            if weekday not in weekday_totals:
                weekday_totals[weekday] = []
            weekday_totals[weekday].append(duration)

        averages = []
        for durations in weekday_totals.values():
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
        if not self.session_history:
            return datetime.timedelta()
        total = sum((duration for start, end, duration in self.session_history), datetime.timedelta())
        return total / len(self.session_history)

    def history(self):
        """
        Get a summary of session history and statistics.

        Returns:
            dict: Dictionary with days tracked, totals, averages, and session history.
        """
        return {
            "days": self.days_tracked(),
            "total_today": self.total_time_today(),
            "total_yesterday": self.total_time_yesterday(),
            "seven_day_average": self.seven_day_average(),
            "weekday_average": self.weekday_average(),
            "total_average": self.total_average(),
            "history": self.session_history,
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
            while True:
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
