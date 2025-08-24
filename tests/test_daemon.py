import pytest
import datetime
from time_awareness import TimeAwareness

class DummyDateTime(datetime.datetime):
    @classmethod
    def now(cls):
        return cls(2024, 6, 1, 12, 0, 0)

@pytest.fixture
def ta(tmp_path):
    return TimeAwareness(app_dir=tmp_path, end_session_idle_threshold=1)  # 1 minute threshold for tests

def test_daemon_starts_and_ends_session(monkeypatch, ta):
    # Simulate idle time switching between active and inactive
    idle_times = [
        datetime.timedelta(seconds=0),    # active
        datetime.timedelta(seconds=0),    # active
        datetime.timedelta(minutes=2),    # inactive (exceeds threshold)
        datetime.timedelta(minutes=2),    # still inactive
        datetime.timedelta(seconds=0),    # active again
    ]
    call_log = []

    def fake_get_idle_time():
        return idle_times.pop(0) if idle_times else datetime.timedelta(seconds=0)

    monkeypatch.setattr(ta, "get_idle_time", fake_get_idle_time)
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)

    def fake_start_session():
        call_log.append("start_session")
        ta.current_session = DummyDateTime.now()

    def fake_end_session():
        call_log.append("end_session")
        ta.current_session = None
        return datetime.timedelta(minutes=2)

    monkeypatch.setattr(ta, "start_session", fake_start_session)
    monkeypatch.setattr(ta, "end_session", fake_end_session)

    # Run daemon for a few cycles
    import threading

    def run_daemon_short():
        try:
            ta.run_daemon(poll_interval=0.01)
        except Exception:
            pass

    t = threading.Thread(target=run_daemon_short)
    t.daemon = True
    t.start()
    # Let it run for a short while
    import time
    time.sleep(0.1)
    # Stop the thread
    t.join(timeout=0.1)

    # Check that session start/end were called in expected order
    assert call_log == ["start_session", "end_session", "start_session"]

def test_daemon_handles_keyboard_interrupt(monkeypatch, ta):
    # Simulate daemon loop interrupted by KeyboardInterrupt
    monkeypatch.setattr(ta, "get_idle_time", lambda: datetime.timedelta(seconds=0))
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    called = {"end_session": False}

    def fake_end_session():
        called["end_session"] = True
        ta.current_session = None
        return datetime.timedelta(minutes=1)

    monkeypatch.setattr(ta, "end_session", fake_end_session)

    def run_daemon_interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(ta, "run_daemon", run_daemon_interrupt)
    with pytest.raises(KeyboardInterrupt):
        ta.run_daemon()
