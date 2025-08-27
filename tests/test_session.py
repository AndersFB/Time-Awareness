import pytest
import datetime

from time_awareness import TimeAwareness

@pytest.fixture(autouse=True)
def use_in_memory_db(use_in_memory_db):
    pass

@pytest.fixture
def ta(tmp_path):
    return TimeAwareness(app_dir=tmp_path, start_daemon=False, log_to_terminal=True)

def test_start_and_end_session(ta):
    ta.start_session()
    assert ta.current_session is not None
    duration = ta.end_session()
    assert isinstance(duration, datetime.timedelta)
    assert ta.current_session is None

def test_save_and_load_state(ta):
    ta.today_total = 123.45
    ta.save_state()
    ta.today_total = 0
    ta.load_state()
    assert ta.today_total == 123.45

def test_total_time_today(ta):
    ta.today_total = 3600  # 1 hour in seconds
    assert ta.total_time_today() == datetime.timedelta(seconds=3600)

def test_days_tracked_and_history(ta):
    # Should not raise error, even if no sessions
    assert isinstance(ta.days_tracked(), int)
    history = ta.history()
    assert "days" in history
    assert "total_today" in history
    assert "sessions" in history

def test_previous_session_no_sessions(ta):
    assert ta.previous_session() is None

def test_total_time_yesterday_empty(ta):
    assert ta.total_time_yesterday() == datetime.timedelta()

def test_seven_day_average_empty(ta):
    assert ta.seven_day_average() == datetime.timedelta()

def test_weekday_average_empty(ta):
    assert ta.weekday_average() == datetime.timedelta()

def test_total_average_empty(ta):
    assert ta.total_average() == datetime.timedelta()

def test_current_session_info(ta):
    ta.start_session()
    start, now, duration = ta.current_session_info()
    assert isinstance(start, datetime.datetime)
    assert isinstance(now, datetime.datetime)
    assert isinstance(duration, datetime.timedelta)
    ta.end_session()

def test_end_session_without_start(ta):
    assert ta.end_session() is None
