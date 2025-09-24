import datetime
import pytest

import time_awareness


@pytest.fixture
def session_manager(use_in_memory_db):
    return time_awareness.SessionManager()


@pytest.fixture
def fake_monitor():
    """Fake SystemMonitor with controllable attributes."""
    class FakeMonitor:
        def __init__(self):
            self.screen_locked = False
            self._uptime = 1000
            self._idle_time = datetime.timedelta(seconds=0)
            self.subscribe_lock_called = False
            self.subscribe_sleep_called = False

        def get_system_uptime(self):
            return self._uptime

        def get_idle_time(self):
            return self._idle_time

        def subscribe_lock_events(self, handler=None):
            self.subscribe_lock_called = True
            return False

        def subscribe_sleep_events(self):
            self.subscribe_sleep_called = True
            return None

    return FakeMonitor()


@pytest.fixture
def daemon(session_manager, fake_monitor, monkeypatch):
    d = time_awareness.Daemon(session_manager, fake_monitor)
    # prevent actual sleeping
    monkeypatch.setattr(time_awareness.time, "sleep", lambda _: None)
    return d


# ------------------------------
# run startup behavior
# ------------------------------
def test_run_starts_session_on_fresh_boot(daemon, fake_monitor):
    fake_monitor._uptime = 10  # below boot_detection_limit
    fake_monitor._idle_time = datetime.timedelta(minutes=20)  # prevent restart
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert daemon._session_manager.current_session is not None


def test_run_starts_session_when_none(daemon, fake_monitor):
    fake_monitor._uptime = 200  # above boot_detection_limit
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon._session_manager.current_session = None
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert daemon._session_manager.current_session is not None


def test_run_subscribes_lock_and_sleep(daemon, fake_monitor):
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert fake_monitor.subscribe_lock_called
    assert fake_monitor.subscribe_sleep_called


# ------------------------------
# sleep detection
# ------------------------------
def test_detects_sleep_and_ends_session(daemon, fake_monitor):
    daemon._is_active = True
    daemon._session_manager.start_session()
    daemon._last_check = datetime.datetime.now() - datetime.timedelta(seconds=60)
    fake_monitor._idle_time = datetime.timedelta(minutes=20)  # ensure no restart

    def fake_is_set():
        if not hasattr(fake_is_set, "called"):
            fake_is_set.called = True
            return False
        return True

    daemon._daemon_stop_event.is_set = fake_is_set
    daemon.run(poll_interval=0.1, sleep_detection_threshold=5.0)

    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


# ------------------------------
# reboot detection
# ------------------------------
def test_detects_reboot_and_ends_session(daemon, fake_monitor):
    daemon._is_active = True
    daemon._end_session_on_restart = True
    daemon._session_manager.start_session()
    fake_monitor._idle_time = datetime.timedelta(minutes=20)

    uptimes = [200, 50]  # decreasing => reboot
    fake_monitor.get_system_uptime = lambda: uptimes.pop(0)

    def fake_is_set():
        if not hasattr(fake_is_set, "called"):
            fake_is_set.called = True
            return False
        return True

    daemon._daemon_stop_event.is_set = fake_is_set
    daemon.run(poll_interval=0.1, sleep_detection_threshold=100.0)

    assert daemon._session_manager.current_session is None


# ------------------------------
# idle detection
# ------------------------------
def test_session_ends_on_idle_threshold(daemon, fake_monitor):
    daemon._is_active = True
    daemon._session_manager.start_session()
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon._end_session_idle_threshold = datetime.timedelta(minutes=10)

    def fake_is_set():
        if not hasattr(fake_is_set, "called"):
            fake_is_set.called = True
            return False
        return True

    daemon._daemon_stop_event.is_set = fake_is_set
    daemon.run(poll_interval=0.1, sleep_detection_threshold=100.0)

    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


def test_session_starts_when_user_active(daemon, fake_monitor):
    daemon._is_active = False
    daemon._session_manager.current_session = None
    fake_monitor._idle_time = datetime.timedelta(seconds=5)
    daemon._end_session_idle_threshold = datetime.timedelta(minutes=10)

    def fake_is_set():
        if not hasattr(fake_is_set, "called"):
            fake_is_set.called = True
            return False
        return True

    daemon._daemon_stop_event.is_set = fake_is_set
    daemon.run(poll_interval=0.1, sleep_detection_threshold=100.0)

    assert daemon._session_manager.current_session is not None
    assert daemon._is_active


# ------------------------------
# stop()
# ------------------------------
def test_stop_cleans_up(daemon, fake_monitor):
    daemon._is_active = True
    daemon._session_manager.start_session()
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon.stop()
    assert not daemon._is_active or daemon._session_manager.current_session is None


# ------------------------------
# new helper methods
# ------------------------------
def test_is_fresh_boot_detects_true(monkeypatch, daemon):
    # force no last_seen_time in metadata
    monkeypatch.setattr(time_awareness, "get_metadata", lambda *a, **kw: "")
    assert daemon._is_fresh_boot(uptime=5)


def test_is_fresh_boot_detects_false_recent(monkeypatch, daemon):
    recent = (datetime.datetime.now() - datetime.timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(time_awareness, "get_metadata", lambda *a, **kw: recent)
    assert not daemon._is_fresh_boot(uptime=5)
