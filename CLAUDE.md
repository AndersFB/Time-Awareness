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

## Architecture and invariants

The architecture, invariants, database notes and statistics semantics are in `.claude/rules/architecture.md`. They load when you work in the code.

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
