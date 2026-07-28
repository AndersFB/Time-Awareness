import datetime
import pytest
import time_awareness

from database import save_session, get_sessions


@pytest.fixture
def manager(use_in_memory_db):
    """
    Provides a SessionManager bound to the in-memory database.
    """
    return time_awareness.SessionManager()


# ------------------------------
# start_session / end_session
# ------------------------------
def test_start_and_end_session(manager):
    manager.start_session()
    assert manager.current_session is not None
    duration = manager.end_session()
    assert isinstance(duration, datetime.timedelta)
    assert manager.current_session is None
    assert manager.today_total > 0


def test_end_session_without_start(manager):
    result = manager.end_session()
    assert result is None


def test_start_session_too_close(manager):
    manager.start_session()
    # Pretend the current session was just started.
    just_started = datetime.datetime.now()
    manager.current_session = just_started

    manager.start_session()  # should not roll over into a new session

    assert manager.current_session == just_started
    assert get_sessions() == []  # nothing was closed and saved


# ------------------------------
# end_session_at
# ------------------------------
def test_end_session_at_valid(manager):
    start = datetime.datetime.now() - datetime.timedelta(hours=1)
    manager.current_session = start
    end_time = start + datetime.timedelta(minutes=30)
    duration = manager.end_session_at(end_time)
    assert duration.total_seconds() == 1800
    assert manager.current_session is None


def test_end_session_at_before_start(manager):
    start = datetime.datetime.now()
    manager.current_session = start
    earlier = start - datetime.timedelta(minutes=5)
    duration = manager.end_session_at(earlier)
    # should clamp to zero
    assert duration.total_seconds() == 0


def test_end_session_at_without_start(manager):
    duration = manager.end_session_at(datetime.datetime.now())
    assert duration is None


# ------------------------------
# midnight splitting
# ------------------------------
def test_split_at_midnight_single_day():
    start = datetime.datetime(2026, 7, 8, 9, 0)
    end = datetime.datetime(2026, 7, 8, 17, 0)
    segments = time_awareness.SessionManager._split_at_midnight(start, end)
    assert segments == [(start, end)]


def test_split_at_midnight_across_days():
    start = datetime.datetime(2026, 7, 7, 23, 0)
    end = datetime.datetime(2026, 7, 9, 1, 0)
    segments = time_awareness.SessionManager._split_at_midnight(start, end)
    assert segments == [
        (start, datetime.datetime(2026, 7, 8, 0, 0)),
        (datetime.datetime(2026, 7, 8, 0, 0), datetime.datetime(2026, 7, 9, 0, 0)),
        (datetime.datetime(2026, 7, 9, 0, 0), end),
    ]


def test_split_at_midnight_drops_zero_length_segment():
    start = datetime.datetime(2026, 7, 7, 23, 0)
    end = datetime.datetime(2026, 7, 8, 0, 0)  # ends exactly at midnight
    segments = time_awareness.SessionManager._split_at_midnight(start, end)
    assert segments == [(start, end)]


def test_end_session_crossing_midnight_saves_split_and_counts_today_only(manager):
    today = datetime.date.today()
    midnight = datetime.datetime.combine(today, datetime.time.min)
    start = midnight - datetime.timedelta(hours=1)  # yesterday 23:00
    end = midnight + datetime.timedelta(hours=1)  # today 01:00
    manager.current_session = start

    duration = manager.end_session_at(end)

    assert duration.total_seconds() == 7200
    sessions = get_sessions()
    assert len(sessions) == 2
    # Only the post-midnight hour counts towards today's total.
    assert manager.today_total == 3600


# ------------------------------
# save_state / load_state
# ------------------------------
def test_save_state_persists_immediately(manager, monkeypatch):
    """State changes must be written on every call - no throttling that could
    lose a session start/end on crash."""
    calls = []
    monkeypatch.setattr(time_awareness, "set_metadata_bulk", lambda items: calls.append(items))

    manager.today_total = 42
    manager._last_update_date = datetime.date.today()
    manager.save_state()
    assert any("today_total" in item for item in calls)

    calls.clear()
    manager.save_state()  # immediately again - must still write
    assert any("today_total" in item for item in calls)


def test_save_state_writes_all_keys_in_one_call(manager, monkeypatch):
    """The three state values must be written together, not one key at a time."""
    calls = []
    monkeypatch.setattr(time_awareness, "set_metadata_bulk", lambda items: calls.append(items))

    manager.today_total = 7
    manager._last_update_date = datetime.date.today()
    manager.current_session = datetime.datetime.now()
    manager.save_state()

    assert len(calls) == 1
    assert set(calls[0]) == {"today_total", "last_update_date", "current_session"}


def test_save_and_load_state_roundtrip(manager):
    now = datetime.datetime.now().replace(microsecond=0)
    manager.today_total = 123.0
    manager._last_update_date = datetime.date.today()
    manager.current_session = now
    manager.save_state()

    restored = time_awareness.SessionManager()
    restored.load_state()
    assert restored.today_total == 123.0
    assert restored._last_update_date == datetime.date.today()
    assert restored.current_session == now


def test_load_state_handles_empty_metadata(manager):
    manager.load_state()
    assert manager.today_total == 0
    assert manager._last_update_date is None
    assert manager.current_session is None


# ------------------------------
# check_day_rollover
# ------------------------------
def test_check_day_rollover_recomputes_from_saved_sessions(manager):
    manager.today_total = 100
    manager._last_update_date = datetime.date.today() - datetime.timedelta(days=1)

    # A session already saved for today should be picked up.
    start = datetime.datetime.combine(datetime.date.today(), datetime.time(hour=1))
    end = start + datetime.timedelta(minutes=30)
    save_session(start, end, end - start)

    manager.check_day_rollover()
    assert manager._last_update_date == datetime.date.today()
    assert manager.today_total == 1800


def test_check_day_rollover_no_previous(manager):
    manager.today_total = 50
    manager._last_update_date = datetime.date.today() - datetime.timedelta(days=1)

    manager.check_day_rollover()
    assert manager.today_total == 0
    assert manager._last_update_date == datetime.date.today()


def test_check_day_rollover_same_day_keeps_total(manager):
    manager.today_total = 50
    manager._last_update_date = datetime.date.today()

    manager.check_day_rollover()
    assert manager.today_total == 50


def test_check_day_rollover_initializes_date(manager):
    manager._last_update_date = None
    manager.check_day_rollover()
    assert manager._last_update_date == datetime.date.today()


# ------------------------------
# reset
# ------------------------------
def test_reset(manager):
    manager.today_total = 500
    manager.current_session = datetime.datetime.now()
    manager._last_update_date = datetime.date.today()

    manager.reset()
    assert manager.today_total == 0
    assert manager.current_session is None
    assert manager._last_update_date is None
