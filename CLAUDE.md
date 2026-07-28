# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

Time Awareness tracks how long you actively use your computer. It runs as a
Linux system tray applet (GTK 3 + AyatanaAppIndicator3) whose icon is a circular
progress ring for the current session, and it also has a CLI. Session data lives
in SQLite via the Peewee ORM. Idle, screen-lock and suspend detection all go
through D-Bus.

Target platform is Linux desktops with AppIndicator support (Ubuntu, Debian,
Fedora, CentOS). Some macOS code paths exist in `SystemMonitor` but the tray app
is Linux-only.

## Layout

```
app.py              Tray application (GTK UI) - GUI entry point
main.py             CLI (Typer) - start/stop/current/live/history/daemon/reset
time_awareness.py   Core: SystemMonitor, SessionManager, Daemon, TimeAwareness
database.py         Peewee models (Session, MetaData) and all query helpers
config.py           Config dataclass, config.ini loading and validation
tracker_lock.py     flock-based single-owner lock for session tracking
requirements.txt    Python dependencies (unpinned)
scripts/            install.sh, update.sh, uninstall.sh
tests/              pytest suite; conftest.py holds the shared fixtures
libs/               AppIndicator GNOME extension zip for Fedora/CentOS
```

Runtime data lives in `~/.time_awareness/`: `timeawareness.sqlite`,
`timeawareness.log`, `config.ini` and `tracker.lock`. The installer clones the
repo into `~/.time_awareness/src/` with its venv at
`~/.time_awareness/src/.venv`.

## Build, test, run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Headless/CI: pygobject and pydbus need system GTK/D-Bus libraries. The core
# suite passes without them.
pip install pytest peewee pillow loguru typer

python -m pytest tests/ -v     # must be run from the repository root
```

The suite runs in a couple of seconds. `tests/test_app.py` is skipped when the
`AyatanaAppIndicator3` namespace is missing. There is no linter configuration in
the repository.

```bash
python app.py             # tray app (needs a display and GTK)
python main.py --help     # CLI
python main.py daemon     # foreground daemon, no GUI
python main.py live       # continuously print the running session
```

## Architecture

Four classes in `time_awareness.py`, plus the tray UI:

- **`SystemMonitor`** — system uptime, idle time, and D-Bus subscriptions for
  screen lock and suspend. Idle detection tries `org.gnome.Mutter.IdleMonitor`
  first, then falls back to `org.freedesktop.ScreenSaver`. The resolved proxy is
  cached, because resolving one costs a synchronous introspection round-trip and
  this runs on every poll. D-Bus proxy objects are held on `self` on purpose:
  pydbus drops signal subscriptions when the proxy is garbage collected.
- **`SessionManager`** — owns the running session and today's total. All mutating
  methods hold an `RLock`, because the GTK main thread and the daemon thread both
  call in. State is persisted to the `MetaData` table.
- **`Daemon`** — the polling loop (default every 5 s): idle threshold handling,
  suspend detection, day rollover, and stale-session recovery at startup.
- **`TimeAwareness`** — the facade both entry points use. Sets up logging, the
  database and the config, owns the tracking lock, optionally starts the daemon
  thread, and exposes the statistics.
- **`TrayApp`** (`app.py`) — indicator, menu, and icon rendering. Refreshes on a
  `GLib.timeout_add_seconds` timer.

Entry points drive the daemon through `TimeAwareness`'s public API —
`start_daemon()`, `run_daemon()`, `request_daemon_stop()`, `stop_daemon()`,
`reload_state()`, `config` — not by reaching into `_daemon` or
`_session_manager`. `run_daemon()` runs the loop in the calling thread (CLI);
`start_daemon()` runs it in a background thread (tray). Both take the tracking
lock.

## Invariants worth knowing before changing anything

These encode fixes for bugs that already happened. Breaking one is easy and the
symptom is usually delayed and hard to attribute.

**Sessions never span midnight.** `SessionManager._split_at_midnight` splits a
session at the day boundary before saving, so `Session.start`'s date identifies
the day a row belongs to. Every daily statistic depends on that, and
`get_daily_totals` groups on it in SQL.

**Suspend is measured on `CLOCK_BOOTTIME`, not `time.monotonic()`.** See
`_monotonic_time`. `CLOCK_MONOTONIC` stops while the machine is suspended, so it
would hide exactly the gap the daemon is trying to detect. Wall-clock time is
unusable here — an NTP step or DST change would fake or mask a suspend.

**`last_seen_time` is written every poll and is how restart is told from
reboot.** `_recover_stale_session` compares boot time against `last_seen_time`:
booted after last seen means the machine was off, so the session is closed at
`last_seen_time` rather than credited with the time the machine spent powered
down. A short gap on the same boot means the app was merely restarted, so the
session resumes. Do not turn this write off.

**GLib event pumping belongs to CLI mode only.** In the tray app the GTK main
loop owns the default `MainContext` and dispatches pydbus callbacks. The CLI
daemon has no main loop, so it calls `Daemon.enable_glib_event_pump()` and pumps
the context itself. Turning it on under GTK means two things iterating the same
context.

**`TimeAwareness.end_session()` deliberately does not clear the daemon's
`_is_active` flag.** That flag means "the daemon believes the user is at the
keyboard". Leaving it set after the tray's "Disable" is what stops the daemon
from reopening a session on its very next poll. Clearing it there makes
"Disable" a no-op that undoes itself within seconds.

**`Daemon.stop()` waits for the loop to leave its current iteration.** Otherwise
it closes the session while the loop is still inside `get_idle_time()`, and the
loop opens a new one immediately afterwards — the app then quits with a session
dangling in the database. `request_stop()` is the signal-handler-safe half: it
touches no database state, so a SIGTERM cannot re-enter sqlite on a thread that
is already inside it. `tests/test_daemon.py::test_stop_from_other_thread_leaves_no_open_session`
covers this.

**Nothing raised inside a GLib callback may escape.** PyGObject prints the
traceback and treats the callback as returning false, which removes the timeout
source — a single transient error would freeze the tray icon and menu for the
rest of the session. `TrayApp.refresh` catches everything and always returns
`True`.

**`current_session_info()` logs at debug, not warning.** "No session" is the
normal idle state and the tray polls it every few seconds; at warning level it
buries the log file.

**Only one process may own tracking.** The tray app and the CLI daemon each keep
their own in-memory `SessionManager`; two of them against one database overwrite
each other's `current_session`, and whichever writes last silently wins.
`TrackerLock` (`tracker_lock.py`) enforces one owner via `flock` on
`~/.time_awareness/tracker.lock`. `flock` is tied to the open file description,
so the kernel drops it when the process exits — a killed tray app leaves no
stale lock, only a file with a dead PID in it, which `owner_pid()` correctly
reports as unlocked. Do not switch this to `fcntl.lockf` or a plain PID file:
`lockf` locks are per-process (so a second lock in the same process would
succeed) and a PID file cannot survive a `kill -9` without going stale.

**`config.ini` is advisory, never fatal.** A missing file, missing key,
unparsable value or missing section falls back to the default and logs it. The
tray applet is usually started by autostart with no terminal attached, so a
config error must never stop it from starting. `_apply_bounds` also keeps
`sleep_detection_threshold_seconds` above `poll_interval_seconds` — if it drops
below, the ordinary gap between two checks exceeds the threshold and every
single check is misread as a suspend, ending the session forever.

## Database notes

`configure_database` sets `journal_mode=wal`, `busy_timeout=5000` and
`synchronous=normal`. The GTK main thread and the daemon thread both touch the
database; without WAL and a busy timeout, concurrent access intermittently fails
with "database is locked".

`with_database` opens a connection only if the calling thread does not already
have one, and closes it only if it opened it. Peewee keeps connection state in a
thread-local, so **each thread has its own connection**. This matters in tests:
a plain `:memory:` database would give a background thread its own empty
database and every query it makes would fail silently. `tests/conftest.py`
therefore uses a uniquely named shared-cache in-memory database.

Prefer aggregating in SQL over loading rows into Python. `get_daily_totals`,
`get_total_for_day`, `get_average_session_duration` and `get_days_tracked` all
do, which keeps the statistics O(days) instead of O(sessions). Use
`set_metadata_bulk` / `get_metadata_bulk` for related keys: one connection and
one transaction instead of one per key, and `SessionManager.save_state` relies
on the atomicity.

## Statistics semantics

| Value | Meaning |
|---|---|
| Total today | Saved sessions for today **plus** the part of the running session that falls on today |
| Total yesterday | Sum of yesterday's saved sessions |
| 7-day average | Mean daily total over the last 7 *calendar* days, averaged over the days that have tracked time |
| Weekday average | Mean daily total per weekday, then macro-averaged over the weekdays that have data |
| Total average | Mean duration of a single session across all history |

"Total today" is computed on the fly and does not change stored state.
`today_total` in the database still counts only saved sessions.

## Configuration

`config.py` defines a frozen `Config` dataclass whose field names are exactly
the keys in `config.ini`. Adding a setting means adding one field with a default
and, if it needs a floor, one entry in `_MINIMUMS` — plus a commented line in
`DEFAULT_CONFIG_TEMPLATE`. `test_written_default_config_reloads_to_the_defaults`
fails if the template and the dataclass drift apart.

Settings reach the daemon through `TimeAwareness.__init__`
(`monitor_lock_and_sleep`, `idle_threshold_minutes`) and `_run_daemon_loop`
(`poll_interval_seconds`, `sleep_detection_threshold_seconds`, `verbose`). Pass
`config=Config(...)` to `TimeAwareness` in tests to avoid touching the file.

## Known limitations

- Settings are read at startup only; there is no reload-on-change.
- The lock guarantees one *tracker*, not one reader. Read-only CLI commands run
  freely alongside the tray app and simply re-read state from the database.
- Session state is exchanged through the database, not IPC, so `main.py --force`
  still fights a running tracker. It exists as an escape hatch, not a feature.

## Conventions

- Loguru brace formatting: `logger.info("message {}", value)`, not f-strings.
- Docstrings are imperative with `Args:`/`Returns:` sections.
- Comments explain *why*, especially where the non-obvious choice is the correct
  one (clock choice, threading, D-Bus lifetimes). Keep that bar.
- Log levels: `debug` for per-poll chatter, `info` for session lifecycle,
  `warning` for degraded-but-working, `error` for failures.

## Before finishing

1. `python -m pytest tests/ -v` — all tests pass.
2. `python -c "import database, time_awareness"` — no import errors.
3. `bash -n scripts/*.sh` if the shell scripts changed.
4. Behaviour changes that alter what the tray shows or how sessions are recorded
   belong in `README.md` too.
