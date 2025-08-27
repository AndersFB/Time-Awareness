import pytest
import datetime
from unittest.mock import patch
from time_awareness import TimeAwareness

@pytest.fixture
def ta(tmp_path):
    # Create a TimeAwareness instance with a temp directory
    return TimeAwareness(app_dir=tmp_path, start_daemon=False, log_to_terminal=True)

def test_lock_event_ends_session(ta):
    with patch('time_awareness.datetime') as mock_datetime:
        # Patch now() and date.today() to real values
        real_now = datetime.datetime.now()
        real_today = datetime.date.today()
        mock_datetime.datetime.now.return_value = real_now
        mock_datetime.date.today.return_value = real_today
        ta.start_session()
        assert ta.current_session is not None
        # Simulate lock event
        ta._handle_lock_event(True)
        assert ta.current_session is None
        assert not ta._is_active
        assert ta._screen_locked

def test_unlock_event_starts_session(ta):
    ta._is_active = False
    ta._screen_locked = True
    with patch.object(ta, 'get_idle_time', return_value=datetime.timedelta(minutes=1)):
        with patch('time_awareness.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime.now()
            mock_datetime.date.today.return_value = datetime.date.today()
            ta._handle_lock_event(False)
            assert ta.current_session is not None
            assert ta._is_active
            assert not ta._screen_locked

def test_unlock_event_does_not_start_session_if_idle(ta):
    ta._is_active = False
    ta._screen_locked = True
    with patch.object(ta, 'get_idle_time', return_value=datetime.timedelta(minutes=20)):
        with patch('time_awareness.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime.now()
            mock_datetime.date.today.return_value = datetime.date.today()
            ta._handle_lock_event(False)
            assert ta.current_session is None
            assert not ta._is_active
            assert not ta._screen_locked

def test_sleep_event_ends_session(ta):
    with patch('time_awareness.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime.now()
        mock_datetime.date.today.return_value = datetime.date.today()
        ta.start_session()
        ta._is_active = True
        ta._handle_lock_event(True)  # Lock also ends session
        assert ta.current_session is None
        assert not ta._is_active

def test_end_session_when_none_active(ta):
    ta.current_session = None
    result = ta.end_session()
    assert result is None

def test_start_session_when_already_active(ta):
    ta.start_session()
    first_session = ta.current_session
    ta.start_session()
    # Should end previous and start new
    assert ta.current_session != first_session

def test_end_session_at_before_start(ta):
    ta.start_session()
    start_time = ta.current_session
    end_time = start_time - datetime.timedelta(minutes=5)
    result = ta.end_session_at(end_time)
    # Should clamp to start_time, duration zero
    assert result.total_seconds() == 0

def test_unlock_event_idle_time_at_threshold(ta):
    ta._is_active = False
    ta._screen_locked = True
    ta.end_session_idle_threshold = 10  # minutes
    with patch.object(ta, 'get_idle_time', return_value=datetime.timedelta(minutes=10)):
        ta._handle_lock_event(False)
        assert ta.current_session is None
        assert not ta._is_active
        assert not ta._screen_locked

def test_lock_event_when_already_locked(ta):
    ta._is_active = False
    ta._screen_locked = True
    ta.current_session = None
    ta._handle_lock_event(True)
    assert ta.current_session is None
    assert not ta._is_active
    assert ta._screen_locked

def test_unlock_event_when_already_unlocked(ta):
    ta._is_active = True
    ta._screen_locked = False
    ta.current_session = None
    ta._handle_lock_event(False)
    # Should not start a session if already unlocked and active
    assert ta.current_session is None
    assert ta._is_active
    assert not ta._screen_locked
