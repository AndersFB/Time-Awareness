# Copilot Instructions for Time-Awareness

## Repository Overview

Time-Awareness is a Linux desktop productivity tool that tracks computer usage sessions. It provides a system tray icon with GTK/AyatanaAppIndicator3 integration, displaying session duration as a circular progress indicator. The app uses D-Bus for idle detection and persists data in SQLite via Peewee ORM.

**Target Platforms:** Linux desktops with AyatanaAppIndicator3 support (Ubuntu, Debian, Fedora, CentOS, GNOME)

## Project Structure

```
/
├── app.py              # Tray application with GTK UI (main entry point for GUI)
├── main.py             # CLI application using Typer
├── time_awareness.py   # Core logic: TimeAwareness, SessionManager, SystemMonitor, Daemon
├── database.py         # Peewee ORM models and database operations
├── requirements.txt    # Python dependencies
├── scripts/            # Installation/update/uninstall shell scripts
│   ├── install.sh
│   ├── update.sh
│   └── uninstall.sh
├── tests/              # pytest test suite
│   ├── conftest.py     # Fixtures: in-memory database, logging
│   ├── test_database.py
│   ├── test_session_manager.py
│   ├── test_system_monitor.py
│   ├── test_daemon.py
│   ├── test_time_awareness.py
│   └── test_app.py     # GUI tests (skip without AyatanaAppIndicator3)
└── libs/               # GNOME extension for Fedora/CentOS tray support
```

## Build and Test Commands

### Environment Setup

**Always create a virtual environment first:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

**All dependencies:**
```bash
pip install -r requirements.txt
```

**Note:** `pygobject` and `pydbus` require system-level GTK and D-Bus libraries. In CI/headless environments where these system packages are unavailable, install a minimal subset for testing:
```bash
pip install pytest peewee pillow loguru typer
```

### Running Tests

**Always run tests from the repository root:**
```bash
python -m pytest tests/ -v
```

- Tests complete in ~1 second
- Core tests pass without GTK dependencies
- Tests in `test_app.py` are skipped without AyatanaAppIndicator3
- Tests use in-memory SQLite database (no cleanup needed)

### Running the Application

**GUI Tray App (requires display and GTK):**
```bash
python app.py
```

**CLI Commands:**
```bash
python main.py start      # Start session
python main.py stop       # Stop session
python main.py current    # Show current session info
python main.py history    # Show session history
python main.py daemon     # Run background daemon
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `pytest` | Test framework |
| `peewee` | SQLite ORM for sessions and metadata |
| `pillow` | Icon rendering |
| `loguru` | Logging to file and terminal |
| `typer` | CLI framework |
| `pygobject` | GTK bindings (GUI only) |
| `pydbus` | D-Bus for idle/lock detection |

## Architecture Notes

- **TimeAwareness** (`time_awareness.py:458`): Main wrapper coordinating SessionManager, SystemMonitor, and Daemon
- **SessionManager** (`time_awareness.py:173`): Handles session start/end, state persistence, day rollover
- **SystemMonitor** (`time_awareness.py:30`): System uptime, idle time, D-Bus lock/sleep events
- **Daemon** (`time_awareness.py:318`): Background thread for idle detection and automatic session management
- **TrayApp** (`app.py:37`): GTK tray icon with menu, icon rendering, and user interactions

Database files are stored in `~/.time_awareness/`:
- `timeawareness.sqlite` - Session data
- `timeawareness.log` - Application logs

## Testing Patterns

Tests use fixtures from `tests/conftest.py`:
- `use_in_memory_db`: Creates in-memory SQLite database, initializes tables
- `enable_logging`: Configures Loguru for stdout during tests

To auto-apply the in-memory database fixture to all tests in a module:
```python
@pytest.fixture(autouse=True)
def setup_db(use_in_memory_db):
    pass  # This applies use_in_memory_db from conftest.py to all tests

def test_example():
    # Test code using database
```

## Code Style

- No explicit linting configuration (no flake8, pylint, black configs)
- Use existing import patterns and naming conventions
- Docstrings use imperative mood with Args/Returns sections
- Logger calls use `logger.info("message {}", variable)` format (Loguru syntax)

## Validation Checklist

Before completing changes:
1. Run `python -m pytest tests/ -v` - all tests should pass
2. Verify no import errors: `python -c "import database; import time_awareness"`
3. For GUI changes: test on system with GTK if possible

## Trust These Instructions

These instructions are validated and accurate. Only search the codebase if:
- Information here is incomplete for your specific task
- You encounter errors contradicting these instructions
