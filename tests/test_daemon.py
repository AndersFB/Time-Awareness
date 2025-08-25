import pytest
import threading
import time
import datetime

from time_awareness import TimeAwareness

@pytest.fixture(autouse=True)
def use_in_memory_db(use_in_memory_db):
    pass

@pytest.fixture
def ta(tmp_path):
    return TimeAwareness(app_dir=tmp_path, log_to_terminal=True)

def test_run_daemon_starts_and_ends_session(monkeypatch, ta):
    # Simulate idle time: first active, then idle
    idle_times = [0, 0, 600_000, 600_000]  # ms (0 ms active, 600_000 ms idle)
    def fake_get_idle_time():
        # Return next idle time in seconds
        if idle_times:
            ms = idle_times.pop(0)
            return ta.end_session_idle_threshold if ms >= 600_000 else datetime.timedelta(seconds=0)
        return datetime.timedelta(seconds=0)
    monkeypatch.setattr(ta, "get_idle_time", fake_get_idle_time)

    # Run daemon in a thread, stop after a short time
    def run_and_stop():
        ta.run_daemon(poll_interval=0.01)
    t = threading.Thread(target=run_and_stop)
    t.start()
    time.sleep(0.05)
    ta.quit_daemon()
    t.join()

    assert ta.current_session is None

def test_daemon_does_not_start_session_if_active(monkeypatch, ta):
    ta.current_session = datetime.datetime.now()
    monkeypatch.setattr(ta, "get_idle_time", lambda: datetime.timedelta(seconds=0))
    # Should not start a new session if already active
    ta._daemon_stop_event.set()
    ta.run_daemon(poll_interval=0.01)
    # Session should remain unchanged
    assert ta.current_session is not None

def test_daemon_does_not_end_session_if_inactive(monkeypatch, ta):
    ta.current_session = None
    monkeypatch.setattr(ta, "get_idle_time", lambda: ta.end_session_idle_threshold)
    ta._daemon_stop_event.set()
    ta.run_daemon(poll_interval=0.01)
    # Session should remain None
    assert ta.current_session is None

def test_daemon_handles_get_idle_time_exception(monkeypatch, ta):
    monkeypatch.setattr(ta, "get_idle_time", lambda: (_ for _ in ()).throw(Exception("fail")))
    ta._daemon_stop_event.set()
    # Should not raise, just log error
    ta.run_daemon(poll_interval=0.01)
    assert ta.current_session is None

def test_daemon_repeated_start_stop(monkeypatch, ta):
    idle_times = [0, 600_000, 0, 600_000]
    def fake_get_idle_time():
        if idle_times:
            ms = idle_times.pop(0)
            return ta.end_session_idle_threshold if ms >= 600_000 else datetime.timedelta(seconds=0)
        return datetime.timedelta(seconds=0)
    monkeypatch.setattr(ta, "get_idle_time", fake_get_idle_time)
    def run_and_stop():
        ta.run_daemon(poll_interval=0.01)
    t = threading.Thread(target=run_and_stop)
    t.start()
    time.sleep(0.1)
    ta.quit_daemon()
    t.join()
    assert ta.current_session is None
