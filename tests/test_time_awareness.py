import datetime
import pytest

import time_awareness


@pytest.fixture
def app(tmp_path, use_in_memory_db):
    """Create a TimeAwareness app pointing to a temp directory + in-memory DB."""
    return time_awareness.TimeAwareness(app_dir=tmp_path, start_daemon=False, log_to_terminal=True)


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
    app.end_session()
    prev = app.previous_session(verbose=False)
    days = app.days_tracked()
    # prev may be None if DB not persisting, but days_tracked should be int
    assert isinstance(days, int)


# ------------------------------
# Totals & averages
# ------------------------------
def test_total_time_today_and_yesterday(app):
    today = app.total_time_today()
    assert isinstance(today, datetime.timedelta)

    yesterday = app.total_time_yesterday()
    assert isinstance(yesterday, datetime.timedelta)


def test_seven_day_average_and_weekday_average(app):
    avg7 = app.seven_day_average()
    avgw = app.weekday_average()
    assert isinstance(avg7, datetime.timedelta)
    assert isinstance(avgw, datetime.timedelta)


def test_total_average(app):
    avg = app.total_average()
    assert isinstance(avg, datetime.timedelta)


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
    assert app._daemon_thread.is_alive()
    app.stop_daemon()
