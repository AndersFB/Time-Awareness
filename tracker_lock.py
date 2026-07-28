"""
Single-owner lock for session tracking.

The tray app and the CLI daemon both track sessions, and each keeps its own
in-memory SessionManager that it writes to the database. Two of them running at
once silently overwrite each other's current session, so only one process may
own tracking at a time.

Built on ``flock``, which the kernel releases when the file descriptor closes.
A crashed or killed owner therefore leaves no stale lock behind - only a file
containing a PID that no longer holds anything.
"""
import os
from pathlib import Path
from typing import Optional

from loguru import logger

try:
    import fcntl
except ImportError:  # not available off Unix
    fcntl = None

LOCK_FILENAME = "tracker.lock"


class TrackerAlreadyRunningError(RuntimeError):
    """Raised when another process already owns session tracking."""

    def __init__(self, pid: Optional[int] = None):
        self.pid = pid
        where = f" (PID {pid})" if pid else ""
        super().__init__(f"Time Awareness is already tracking in another process{where}.")


def _read_pid(fd: int) -> Optional[int]:
    """Read the owner PID from an open lock file, tolerating a partial write."""
    try:
        raw = os.pread(fd, 32, 0).decode("utf-8", "replace").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def owner_pid(app_dir: Path) -> Optional[int]:
    """
    Return the PID of the process currently tracking, or None if nobody is.

    Does not disturb the holder: the probe takes the lock only to find out that
    it cannot, and releases it immediately when it can.

    Args:
        app_dir (Path): Application directory holding the lock file.

    Returns:
        int: PID of the tracking process, or None.
    """
    if fcntl is None:
        return None

    path = Path(app_dir) / LOCK_FILENAME
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None  # no lock file yet, or unreadable

    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return _read_pid(fd)  # held by someone
        # We got it, so nobody owns tracking. Drop it again straight away.
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


class TrackerLock:
    """Ownership of session tracking for the lifetime of this process."""

    def __init__(self, app_dir: Path):
        self._path = Path(app_dir) / LOCK_FILENAME
        self._fd = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self):
        """
        Take ownership of session tracking.

        Raises:
            TrackerAlreadyRunningError: another process owns tracking.
        """
        if self._fd is not None:
            return  # already ours
        if fcntl is None:
            logger.warning("File locking unavailable on this platform; "
                           "a second tracker cannot be detected.")
            return

        try:
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as e:
            # Better to track without the guard than not to track at all.
            logger.warning("Could not open lock file {}: {}; continuing unguarded.", self._path, e)
            return

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            pid = _read_pid(fd)
            os.close(fd)
            raise TrackerAlreadyRunningError(pid)

        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
        except OSError as e:
            logger.warning("Could not record PID in {}: {}", self._path, e)

        self._fd = fd
        logger.info("Acquired tracking lock {} (PID {}).", self._path, os.getpid())

    def release(self):
        """Give up ownership. Safe to call when the lock is not held."""
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            # Clear the PID first so the file never advertises a dead owner.
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as e:
            logger.warning("Failed to release tracking lock cleanly: {}", e)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
        logger.info("Released tracking lock {}.", self._path)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
        return False
