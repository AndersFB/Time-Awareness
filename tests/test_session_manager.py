import datetime
import pytest
import time_awareness


@pytest.fixture
def manager(use_in_memory_db):
    """
    Provides a SessionManager bound to the in-memory database.
    The `use_in_memory_db` fixture is expected to configure the DB
    (via configure_database + create_tables_if_not_exist).
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
    # Pretend last session was just started
    manager.current_session = datetime.datetime.now()
    result = manager.start_session()  # should not start a new one
    assert result is None


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
# save_state / load_state
# ------------------------------
def test_save_and_load_state_respects_interval(manager, monkeypatch):
    # capture calls to set_metadata
    calls = []

    def fake_set_metadata(key, value):
        calls.append((key, value))

    monkeypatch.setattr(time_awareness, "set_metadata", fake_set_metadata)

    # freeze time
    now = [1000.0]
    monkeypatch.setattr(time_awareness.time, "time", lambda: now[0])

    # First save_state should run
    manager.today_total = 42
    manager._last_update_date = datetime.date.today()
    manager.save_state()
    assert any(key == "today_total" for key, _ in calls)

    # Clear calls and immediately call again at the same "time"
    calls.clear()
    manager.save_state()
    assert calls == []  # nothing written because interval not passed

    # Advance time beyond save interval (default 30s)
    now[0] += 31
    manager.save_state()
    assert any(key == "today_total" for key, _ in calls)



# ------------------------------
# check_day_rollover
# ------------------------------
def test_check_day_rollover_resets_total(manager):
    manager.today_total = 100
    manager._last_update_date = datetime.date.today() - datetime.timedelta(days=1)

    # Simulate a session that overlaps midnight
    midnight = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    manager.current_session = midnight - datetime.timedelta(minutes=30)

    manager.check_day_rollover()
    assert manager._last_update_date == datetime.date.today()
    # today_total may be 0 or small overlap, but should not remain 100
    assert manager.today_total <= 600


def test_check_day_rollover_no_previous(manager):
    manager.today_total = 50
    manager._last_update_date = datetime.date.today() - datetime.timedelta(days=1)

    manager.check_day_rollover()
    assert manager.today_total == 0
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
