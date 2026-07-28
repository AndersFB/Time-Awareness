import datetime
import pytest

import time_awareness
from config import CONFIG_FILENAME, Config
from database import save_session, set_metadata_bulk
from tracker_lock import TrackerAlreadyRunningError, owner_pid


@pytest.fixture
def app(tmp_path, use_in_memory_db):
    """Create a TimeAwareness app pointing to a temp directory + in-memory DB."""
    return time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=False, log_to_terminal=True)


def _save_day(day: datetime.date, hours: float, hour_of_day: int = 9):
    """Save a single session of the given length on the given day."""
    start = datetime.datetime.combine(day, datetime.time(hour=hour_of_day))
    end = start + datetime.timedelta(hours=hours)
    save_session(start, end, end - start)


# ------------------------------
# Session handling
# ------------------------------
def test_start_and_end_session(app):
    app.start_session()
    assert app._session_manager.current_session is not None
    duration = app.end_session()
    assert isinstance(duration, datetime.timedelta)
    assert app._session_manager.current_session is None


def test_current_session_info(app):
    # no session yet
    assert app.current_session_info(verbose=False) is None
    app.start_session()
    info = app.current_session_info()
    assert isinstance(info, tuple)
    assert isinstance(info[0], datetime.datetime)  # start
    assert isinstance(info[1], datetime.datetime)  # now
    assert isinstance(info[2], datetime.timedelta)  # duration


def test_previous_session_and_days_tracked(app):
    app.start_session()
    started = app._session_manager.current_session
    app.end_session()

    prev = app.previous_session(verbose=False)
    assert prev is not None
    prev_start, prev_end, prev_duration = prev
    assert prev_start == started
    assert prev_end >= prev_start
    assert app.days_tracked() == 1


# ------------------------------
# Totals & averages
# ------------------------------
def test_total_time_today_and_yesterday(app):
    today = app.total_time_today()
    assert isinstance(today, datetime.timedelta)

    yesterday = app.total_time_yesterday()
    assert isinstance(yesterday, datetime.timedelta)


def test_total_time_today_includes_running_session(app):
    """The session in progress counts towards today's total, not just saved ones."""
    _save_day(datetime.date.today(), hours=1)
    app._session_manager.check_day_rollover()
    saved_only = datetime.timedelta(seconds=app._session_manager.today_total)
    assert saved_only == datetime.timedelta(hours=1)

    app._session_manager.current_session = datetime.datetime.now() - datetime.timedelta(minutes=30)
    total = app.total_time_today()
    assert datetime.timedelta(hours=1, minutes=30) <= total < datetime.timedelta(hours=1, minutes=31)


def test_total_time_today_only_counts_todays_part_of_running_session(app):
    """A session started yesterday only contributes the part after midnight."""
    midnight = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    app._session_manager.current_session = midnight - datetime.timedelta(hours=5)

    total = app.total_time_today()
    since_midnight = datetime.datetime.now() - midnight
    assert total <= since_midnight


def test_total_time_yesterday_sums_yesterdays_sessions(app):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    _save_day(yesterday, hours=2, hour_of_day=9)
    _save_day(yesterday, hours=1, hour_of_day=13)
    _save_day(datetime.date.today(), hours=4)

    assert app.total_time_yesterday() == datetime.timedelta(hours=3)


def test_seven_day_average_and_weekday_average(app):
    avg7 = app.seven_day_average()
    avgw = app.weekday_average()
    assert isinstance(avg7, datetime.timedelta)
    assert isinstance(avgw, datetime.timedelta)


def test_seven_day_average_uses_daily_totals(app):
    """Averages daily totals over tracked days, not individual session lengths."""
    today = datetime.date.today()
    # 4h today, split over two sessions; 2h yesterday. Average = 3h/day.
    _save_day(today, hours=3, hour_of_day=9)
    _save_day(today, hours=1, hour_of_day=14)
    _save_day(today - datetime.timedelta(days=1), hours=2)

    assert app.seven_day_average() == datetime.timedelta(hours=3)


def test_seven_day_average_ignores_days_outside_the_window(app):
    today = datetime.date.today()
    _save_day(today, hours=2)
    _save_day(today - datetime.timedelta(days=30), hours=10)

    assert app.seven_day_average() == datetime.timedelta(hours=2)


def test_seven_day_average_includes_the_whole_seventh_day(app):
    """The window is 7 calendar days, so the oldest day counts in full."""
    today = datetime.date.today()
    _save_day(today - datetime.timedelta(days=6), hours=5, hour_of_day=0)

    assert app.seven_day_average() == datetime.timedelta(hours=5)


def test_weekday_average_uses_daily_totals_not_session_lengths(app):
    """
    Two sessions of 1h on one day must count as a 2h day, not as two 1h samples.
    """
    day = datetime.date(2026, 7, 6)  # a Monday
    _save_day(day, hours=1, hour_of_day=9)
    _save_day(day, hours=1, hour_of_day=14)

    assert app.weekday_average() == datetime.timedelta(hours=2)


def test_weekday_average_macro_averages_over_weekdays(app):
    monday_a = datetime.date(2026, 7, 6)
    monday_b = datetime.date(2026, 7, 13)
    tuesday = datetime.date(2026, 7, 7)
    _save_day(monday_a, hours=1)
    _save_day(monday_b, hours=3)   # Monday average = 2h
    _save_day(tuesday, hours=4)    # Tuesday average = 4h

    assert app.weekday_average() == datetime.timedelta(hours=3)


def test_total_average(app):
    avg = app.total_average()
    assert isinstance(avg, datetime.timedelta)


def test_total_average_is_mean_session_length(app):
    _save_day(datetime.date(2026, 7, 6), hours=1, hour_of_day=9)
    _save_day(datetime.date(2026, 7, 6), hours=3, hour_of_day=14)

    assert app.total_average() == datetime.timedelta(hours=2)


def test_statistics_are_zero_on_empty_database(app):
    assert app.total_time_today() == datetime.timedelta()
    assert app.total_time_yesterday() == datetime.timedelta()
    assert app.seven_day_average() == datetime.timedelta()
    assert app.weekday_average() == datetime.timedelta()
    assert app.total_average() == datetime.timedelta()
    assert app.days_tracked() == 0


# ------------------------------
# History
# ------------------------------
def test_history_returns_dict(app):
    hist = app.history(count_sessions=True)
    assert isinstance(hist, dict)
    assert "days" in hist
    assert "sessions" in hist


# ------------------------------
# Reset
# ------------------------------
def test_reset_resets_database_and_session(app):
    app.start_session()
    app.reset()
    # after reset, session should be restarted
    assert app._session_manager.current_session is not None
    assert app.total_time_today() >= datetime.timedelta(0)


# ------------------------------
# Daemon control
# ------------------------------
def test_stop_daemon_no_thread(app):
    # Should not crash when no thread is running
    app.stop_daemon()

def test_daemon_thread_start_and_stop(tmp_path, use_in_memory_db):
    app = time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=True, log_to_terminal=True)
    try:
        assert app._daemon_thread.is_alive()
    finally:
        app.stop_daemon()


def test_start_daemon_twice_is_a_noop(tmp_path, use_in_memory_db):
    app = time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=True, log_to_terminal=True)
    try:
        thread = app._daemon_thread
        app.start_daemon()
        assert app._daemon_thread is thread
    finally:
        app.stop_daemon()


# ------------------------------
# Configuration
# ------------------------------
def test_config_is_read_from_the_app_dir(tmp_path, use_in_memory_db):
    (tmp_path / CONFIG_FILENAME).write_text(
        "[time_awareness]\nidle_threshold_minutes = 3\nverbose = true\n", encoding="utf-8")

    app = time_awareness.TimeAwareness(app_dir=tmp_path, log_to_terminal=True)

    assert app.config.idle_threshold_minutes == 3
    assert app.config.verbose is True


def test_config_reaches_the_daemon(tmp_path, use_in_memory_db):
    config = Config(idle_threshold_minutes=3, monitor_lock_and_sleep=False)

    app = time_awareness.TimeAwareness(app_dir=tmp_path, log_to_terminal=True, config=config)

    assert app._daemon._end_session_idle_threshold == datetime.timedelta(minutes=3)
    assert app._daemon._monitor_lock_and_sleep is False


def test_daemon_loop_runs_with_the_configured_intervals(tmp_path, use_in_memory_db, monkeypatch):
    config = Config(poll_interval_seconds=1.5, sleep_detection_threshold_seconds=12, verbose=True)
    app = time_awareness.TimeAwareness(app_dir=tmp_path, log_to_terminal=True, config=config)

    captured = {}
    monkeypatch.setattr(app._daemon, "run", lambda **kwargs: captured.update(kwargs))
    app._run_daemon_loop()

    assert captured == {
        "poll_interval": 1.5,
        "sleep_detection_threshold": 12,
        "verbose": True,
    }


# ------------------------------
# Tracking lock
# ------------------------------
def test_read_only_instance_does_not_take_the_lock(tmp_path, use_in_memory_db):
    time_awareness.TimeAwareness(app_dir=tmp_path, log_to_terminal=True)
    assert owner_pid(tmp_path) is None


def test_start_daemon_takes_the_lock_and_stop_releases_it(tmp_path, use_in_memory_db):
    import os

    app = time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=True, log_to_terminal=True)
    try:
        assert owner_pid(tmp_path) == os.getpid()
    finally:
        app.stop_daemon()

    assert owner_pid(tmp_path) is None


def test_second_tracker_in_the_same_app_dir_is_refused(tmp_path, use_in_memory_db):
    first = time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=True, log_to_terminal=True)
    try:
        with pytest.raises(TrackerAlreadyRunningError):
            time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=True, log_to_terminal=True)
    finally:
        first.stop_daemon()


def test_run_daemon_releases_the_lock_when_it_returns(tmp_path, use_in_memory_db):
    app = time_awareness.TimeAwareness(app_dir=tmp_path, log_to_terminal=True)
    app.request_daemon_stop()  # make run() exit at the first loop check

    app.run_daemon()

    assert owner_pid(tmp_path) is None


def test_run_daemon_releases_the_lock_on_failure(tmp_path, use_in_memory_db, monkeypatch):
    app = time_awareness.TimeAwareness(app_dir=tmp_path, log_to_terminal=True)

    def boom(**kwargs):
        raise RuntimeError("daemon blew up")

    monkeypatch.setattr(app._daemon, "run", boom)
    with pytest.raises(RuntimeError):
        app.run_daemon()

    assert owner_pid(tmp_path) is None


# ------------------------------
# reload_state
# ------------------------------
def test_reload_state_picks_up_another_process_changes(app):
    assert app.current_session_info(verbose=False) is None

    started = datetime.datetime.now().replace(microsecond=0)
    set_metadata_bulk({"current_session": started.isoformat()})

    app.reload_state()

    info = app.current_session_info(verbose=False)
    assert info is not None
    assert info[0] == started
