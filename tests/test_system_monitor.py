import datetime
import builtins
import pytest
import sys

import time_awareness


@pytest.fixture
def monitor():
    return time_awareness.SystemMonitor()


# ------------------------------
# get_system_uptime
# ------------------------------
def test_get_system_uptime_linux(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "linux")

    class FakeFile:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def readline(self): return "1234.56 654321\n"

    def fake_open(path, *args, **kwargs):
        assert path == "/proc/uptime"
        return FakeFile()

    monkeypatch.setattr(builtins, "open", lambda path, *a, **k: fake_open(path))
    assert monitor.get_system_uptime() == 1234.56


def test_get_system_uptime_darwin(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "darwin")

    def fake_check_output(cmd):
        return b"{ sec = 1000 }"

    monkeypatch.setattr(time_awareness.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(time_awareness.time, "time", lambda: 2000)

    result = monitor.get_system_uptime()
    assert pytest.approx(result, rel=1e-3) == 1000


def test_get_system_uptime_unsupported(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "win32")
    assert monitor.get_system_uptime() == 0.0


# ------------------------------
# get_idle_time
# ------------------------------
def test_get_idle_time_linux(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "linux")

    fake_idle = datetime.timedelta(seconds=42)
    monkeypatch.setattr(monitor, "_get_idle_time_linux", lambda: fake_idle)

    assert monitor.get_idle_time() == fake_idle


def test_get_idle_time_linux_none(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(monitor, "_get_idle_time_linux", lambda: None)
    assert monitor.get_idle_time() == datetime.timedelta(seconds=0)


def test_get_idle_time_darwin(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "darwin")

    def fake_check_output(cmd):
        return b"HIDIdleTime = 2000000000;"

    monkeypatch.setattr(time_awareness.subprocess, "check_output", fake_check_output)
    result = monitor.get_idle_time()
    assert isinstance(result, datetime.timedelta)
    assert result.total_seconds() == 2


def test_get_idle_time_unsupported(monkeypatch, monitor):
    monkeypatch.setattr(sys, "platform", "win32")
    assert monitor.get_idle_time() == datetime.timedelta(seconds=0)


# ------------------------------
# _get_idle_time_linux
# ------------------------------
class FakeIface:
    def __init__(self, idle=None):
        self._idle = idle

    def GetIdletime(self):
        return self._idle


def test__get_idle_time_linux_with_mutter(monkeypatch, monitor):
    monkeypatch.setattr(time_awareness, "SessionBus", lambda: None)

    class FakeBus:
        def get(self, name, path):
            return FakeIface(1000000)  # microseconds

    monkeypatch.setattr(time_awareness, "SessionBus", lambda: FakeBus())
    result = monitor._get_idle_time_linux()
    assert isinstance(result, datetime.timedelta)
    assert result.total_seconds() > 0


def test__get_idle_time_linux_with_screensaver(monkeypatch, monitor):
    class FakeIface:
        def GetSessionIdleTime(self):
            return 5

    class FakeBus:
        def get(self, name, path):
            return FakeIface()

    monkeypatch.setattr(time_awareness, "SessionBus", lambda: FakeBus())
    result = monitor._get_idle_time_linux()
    assert result.total_seconds() == 5


def test__get_idle_time_linux_none(monkeypatch, monitor):
    monkeypatch.setattr(time_awareness, "SessionBus", lambda: (_ for _ in ()).throw(Exception("fail")))
    assert monitor._get_idle_time_linux() is None


# ------------------------------
# subscribe_lock_events
# ------------------------------
def test_subscribe_lock_events_gnome(monkeypatch, monitor):
    class FakeIface:
        def GetActive(self):
            return True

    class FakeBus:
        def get(self, name, path):
            return FakeIface()

    monkeypatch.setattr(time_awareness, "SessionBus", lambda: FakeBus())
    result = monitor.subscribe_lock_events()
    assert result is True
    assert monitor.screen_locked is True


def test_subscribe_lock_events_fallback(monkeypatch, monitor):
    class FakeIface:
        Active = True

    class FakeBus:
        def get(self, name, path):
            return FakeIface()

    monkeypatch.setattr(time_awareness, "SessionBus", lambda: FakeBus())
    result = monitor.subscribe_lock_events()
    assert result is True
    assert monitor.screen_locked is True


def test_subscribe_lock_events_failure(monkeypatch, monitor):
    monkeypatch.setattr(time_awareness, "SessionBus", lambda: (_ for _ in ()).throw(Exception("fail")))
    result = monitor.subscribe_lock_events()
    assert result is False


# ------------------------------
# subscribe_sleep_events
# ------------------------------
def test_subscribe_sleep_events_success(monkeypatch, monitor):
    class FakeIface:
        def __init__(self):
            self.onPrepareForSleep = None

    class FakeBus:
        def get(self, name, path):
            return FakeIface()

    monkeypatch.setattr(time_awareness, "SystemBus", lambda: FakeBus())
    monitor.subscribe_sleep_events()  # should not raise


def test_subscribe_sleep_events_failure(monkeypatch, monitor):
    monkeypatch.setattr(time_awareness, "SystemBus", lambda: (_ for _ in ()).throw(Exception("fail")))
    monitor.subscribe_sleep_events()  # should not raise
