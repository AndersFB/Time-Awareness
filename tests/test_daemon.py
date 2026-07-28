import datetime
import threading
import time

import pytest

import time_awareness
from database import get_previous_session, set_metadata, get_sessions


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
            # Simulates a slow D-Bus round-trip, so a test can reliably call
            # stop() while the daemon loop is stuck mid-iteration.
            self._idle_delay = 0.0
            self.subscribe_lock_called = False
            self.subscribe_sleep_called = False

        def get_system_uptime(self):
            return self._uptime

        def get_idle_time(self):
            if self._idle_delay:
                time.sleep(self._idle_delay)
            return self._idle_time

        def subscribe_lock_events(self, handler=None):
            self.subscribe_lock_called = True
            return self.screen_locked

        def subscribe_sleep_events(self, handler=None):
            self.subscribe_sleep_called = True
            return None

    return FakeMonitor()


@pytest.fixture
def daemon(session_manager, fake_monitor, monkeypatch):
    d = time_awareness.Daemon(session_manager, fake_monitor)
    # prevent actual sleeping between iterations
    monkeypatch.setattr(d._daemon_stop_event, "wait", lambda *_: None)
    return d


def run_one_iteration(daemon):
    """Make the daemon loop run exactly one iteration, then stop."""
    def fake_is_set():
        if not hasattr(fake_is_set, "called"):
            fake_is_set.called = True
            return False
        return True

    daemon._daemon_stop_event.is_set = fake_is_set


# ------------------------------
# run startup behavior
# ------------------------------
def test_run_starts_session_when_none(daemon, fake_monitor):
    fake_monitor._idle_time = datetime.timedelta(seconds=5)
    daemon._session_manager.current_session = None
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert daemon._session_manager.current_session is not None
    assert daemon._is_active


def test_run_does_not_start_session_when_idle_at_startup(daemon, fake_monitor):
    """Starting while the user is away must not record a phantom session."""
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon._session_manager.current_session = None
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert daemon._session_manager.current_session is None
    assert not daemon._is_active
    assert get_sessions() == []


def test_run_resumes_recovered_session_even_when_idle(daemon, fake_monitor):
    """A session recovered from a previous run survives the idle startup check."""
    now = datetime.datetime.now()
    resumed = now - datetime.timedelta(minutes=30)
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon._session_manager.current_session = resumed
    # Same boot, app gone only briefly -> _recover_stale_session resumes it.
    set_metadata("last_seen_time", (now - datetime.timedelta(seconds=5)).isoformat())
    fake_monitor._uptime = 100000
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert daemon._session_manager.current_session == resumed
    assert daemon._is_active


def test_run_does_not_start_session_when_locked(daemon, fake_monitor):
    fake_monitor.screen_locked = True
    daemon._session_manager.current_session = None
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


def test_run_subscribes_lock_and_sleep(daemon, fake_monitor):
    fake_monitor._idle_time = datetime.timedelta(seconds=5)
    daemon._daemon_stop_event.set()
    daemon.run(poll_interval=0.1, sleep_detection_threshold=1.0)
    assert fake_monitor.subscribe_lock_called
    assert fake_monitor.subscribe_sleep_called


# ------------------------------
# stale session recovery (restart vs shutdown/reboot)
# ------------------------------
def test_recover_closes_session_after_reboot(daemon, fake_monitor):
    now = datetime.datetime.now()
    stale_start = now - datetime.timedelta(hours=3)
    last_seen = now - datetime.timedelta(hours=2)
    daemon._session_manager.current_session = stale_start
    set_metadata("last_seen_time", last_seen.isoformat())

    # Booted 60s ago, i.e. after last_seen -> machine was shut down/rebooted.
    daemon._recover_stale_session(uptime=60)

    assert daemon._session_manager.current_session is None
    prev = get_previous_session(verbose=False)
    assert prev is not None
    assert prev[0] == stale_start
    assert prev[1] == last_seen  # closed at last seen time, not at boot/now


def test_recover_resumes_session_after_quick_app_restart(daemon, fake_monitor):
    now = datetime.datetime.now()
    stale_start = now - datetime.timedelta(hours=1)
    last_seen = now - datetime.timedelta(seconds=10)
    daemon._session_manager.current_session = stale_start
    set_metadata("last_seen_time", last_seen.isoformat())

    # Same boot (booted long before last_seen), app gone only 10s -> resume.
    daemon._recover_stale_session(uptime=100000)

    assert daemon._session_manager.current_session == stale_start
    assert get_previous_session(verbose=False) is None


def test_recover_closes_session_when_app_was_dead_long(daemon, fake_monitor):
    now = datetime.datetime.now()
    stale_start = now - datetime.timedelta(hours=3)
    last_seen = now - datetime.timedelta(hours=2)
    daemon._session_manager.current_session = stale_start
    set_metadata("last_seen_time", last_seen.isoformat())

    # Same boot but the app was gone for 2 hours -> close at last_seen.
    daemon._recover_stale_session(uptime=100000)

    assert daemon._session_manager.current_session is None
    prev = get_previous_session(verbose=False)
    assert prev is not None
    assert prev[1] == last_seen


def test_recover_discards_session_without_last_seen(daemon, fake_monitor):
    stale_start = datetime.datetime.now() - datetime.timedelta(hours=1)
    daemon._session_manager.current_session = stale_start

    daemon._recover_stale_session(uptime=60)

    assert daemon._session_manager.current_session is None
    # Nothing usable to close it with -> no phantom session saved.
    assert get_sessions() == []


def test_recover_noop_without_stale_session(daemon, fake_monitor):
    daemon._session_manager.current_session = None
    daemon._recover_stale_session(uptime=60)
    assert daemon._session_manager.current_session is None


# ------------------------------
# sleep detection
# ------------------------------
def test_detects_sleep_and_ends_session(daemon, fake_monitor):
    daemon._is_active = True
    daemon._session_manager.start_session()
    daemon._last_check = datetime.datetime.now() - datetime.timedelta(seconds=60)
    daemon._last_check_monotonic = time_awareness._monotonic_time() - 60
    fake_monitor._idle_time = datetime.timedelta(minutes=20)  # ensure no restart

    run_one_iteration(daemon)
    daemon.run(poll_interval=0.1, sleep_detection_threshold=5.0)

    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


# ------------------------------
# sleep/lock event handlers
# ------------------------------
def test_sleep_event_ends_session(daemon, fake_monitor):
    daemon._is_active = True
    daemon._session_manager.start_session()

    daemon._handle_sleep_event(True)

    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


def test_resume_event_starts_session_when_unlocked_and_active(daemon, fake_monitor):
    daemon._is_active = False
    fake_monitor._idle_time = datetime.timedelta(seconds=1)

    daemon._handle_sleep_event(False)

    assert daemon._session_manager.current_session is not None
    assert daemon._is_active


def test_resume_event_waits_for_unlock(daemon, fake_monitor):
    daemon._is_active = False
    fake_monitor.screen_locked = True
    fake_monitor._idle_time = datetime.timedelta(seconds=1)

    daemon._handle_sleep_event(False)

    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


# ------------------------------
# idle detection
# ------------------------------
def test_session_ends_on_idle_threshold(daemon, fake_monitor):
    daemon._is_active = True
    daemon._session_manager.start_session()
    fake_monitor._idle_time = datetime.timedelta(minutes=20)
    daemon._end_session_idle_threshold = datetime.timedelta(minutes=10)

    run_one_iteration(daemon)
    daemon.run(poll_interval=0.1, sleep_detection_threshold=100.0)

    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


def test_session_starts_when_user_active(daemon, fake_monitor):
    daemon._is_active = False
    daemon._session_manager.current_session = None
    fake_monitor._idle_time = datetime.timedelta(seconds=5)
    daemon._end_session_idle_threshold = datetime.timedelta(minutes=10)

    run_one_iteration(daemon)
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
    assert daemon._session_manager.current_session is None
    assert not daemon._is_active


def test_stop_is_idempotent(daemon, fake_monitor):
    daemon._session_manager.start_session()
    daemon.stop()
    sessions_after_first_stop = get_sessions()
    daemon.stop()
    # The second stop must not save the session again.
    assert get_sessions() == sessions_after_first_stop


def test_stop_from_other_thread_leaves_no_open_session(session_manager, fake_monitor):
    """
    stop() must not close the session while the loop is still free to open a
    new one: that would leave a dangling session behind on quit.
    """
    d = time_awareness.Daemon(session_manager, fake_monitor)
    fake_monitor._idle_time = datetime.timedelta(seconds=1)  # loop always wants a session
    # Every iteration spends 0.2s inside the idle check, so stop() below lands
    # while the loop is mid-iteration and still able to open a new session.
    fake_monitor._idle_delay = 0.2

    loop = threading.Thread(target=d.run, kwargs={"poll_interval": 0.01})
    loop.start()
    try:
        # Let the loop get going, then stop it from this thread.
        for _ in range(200):
            if session_manager.current_session is not None:
                break
            time.sleep(0.01)
        assert session_manager.current_session is not None, "daemon never started a session"

        d.stop()
    finally:
        loop.join(timeout=5)

    assert not loop.is_alive()
    assert session_manager.current_session is None
    assert not d._is_active
