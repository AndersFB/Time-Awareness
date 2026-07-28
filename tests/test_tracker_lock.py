import os
import subprocess
import sys
import textwrap

import pytest

from tracker_lock import LOCK_FILENAME, TrackerAlreadyRunningError, TrackerLock, owner_pid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def logging_enabled(enable_logging):
    pass


# ------------------------------
# acquire / release
# ------------------------------
def test_acquire_creates_the_lock_file_and_records_the_pid(tmp_path):
    lock = TrackerLock(tmp_path)
    lock.acquire()
    try:
        assert lock.held
        assert (tmp_path / LOCK_FILENAME).exists()
        assert owner_pid(tmp_path) == os.getpid()
    finally:
        lock.release()


def test_release_clears_ownership(tmp_path):
    lock = TrackerLock(tmp_path)
    lock.acquire()
    lock.release()

    assert not lock.held
    assert owner_pid(tmp_path) is None


def test_release_without_acquire_is_a_noop(tmp_path):
    TrackerLock(tmp_path).release()  # must not raise


def test_acquire_twice_on_the_same_lock_is_a_noop(tmp_path):
    lock = TrackerLock(tmp_path)
    lock.acquire()
    try:
        lock.acquire()  # already ours - must not raise
        assert lock.held
    finally:
        lock.release()


def test_second_lock_is_refused_while_the_first_is_held(tmp_path):
    first = TrackerLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(TrackerAlreadyRunningError) as excinfo:
            TrackerLock(tmp_path).acquire()
        assert excinfo.value.pid == os.getpid()
    finally:
        first.release()


def test_lock_can_be_taken_again_after_release(tmp_path):
    first = TrackerLock(tmp_path)
    first.acquire()
    first.release()

    second = TrackerLock(tmp_path)
    second.acquire()  # must not raise
    try:
        assert second.held
    finally:
        second.release()


def test_context_manager_acquires_and_releases(tmp_path):
    with TrackerLock(tmp_path) as lock:
        assert lock.held
        assert owner_pid(tmp_path) == os.getpid()
    assert owner_pid(tmp_path) is None


# ------------------------------
# owner_pid
# ------------------------------
def test_owner_pid_is_none_without_a_lock_file(tmp_path):
    assert owner_pid(tmp_path) is None


def test_owner_pid_probe_does_not_steal_the_lock(tmp_path):
    """Probing must leave a held lock held, and an unheld one unheld."""
    lock = TrackerLock(tmp_path)
    lock.acquire()
    try:
        assert owner_pid(tmp_path) == os.getpid()
        assert owner_pid(tmp_path) == os.getpid()  # still held after probing
    finally:
        lock.release()

    assert owner_pid(tmp_path) is None
    # The probe released what it took, so the lock is still available.
    TrackerLock(tmp_path).acquire()


def test_stale_lock_file_from_a_dead_owner_is_not_reported(tmp_path):
    """
    flock dies with the process, so a leftover file with a PID in it must not
    look like a running tracker.
    """
    (tmp_path / LOCK_FILENAME).write_text("999999\n", encoding="utf-8")

    assert owner_pid(tmp_path) is None
    TrackerLock(tmp_path).acquire()  # must not raise


def test_lock_is_released_when_the_owning_process_dies(tmp_path):
    """A killed tray app must not block the next launch."""
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {REPO_ROOT!r})
        from tracker_lock import TrackerLock
        TrackerLock({str(tmp_path)!r}).acquire()
        print("locked", flush=True)
        time.sleep(60)
    """)
    holder = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE)
    try:
        assert holder.stdout.readline().strip() == b"locked"
        assert owner_pid(tmp_path) == holder.pid
        with pytest.raises(TrackerAlreadyRunningError):
            TrackerLock(tmp_path).acquire()
    finally:
        holder.kill()
        holder.wait(timeout=10)

    assert owner_pid(tmp_path) is None
    TrackerLock(tmp_path).acquire()  # must not raise
