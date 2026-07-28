"""
User configuration for Time Awareness.

Settings live in ``~/.time_awareness/config.ini``. A commented file with the
defaults is written on first run. Everything is optional: a missing file, a
missing key or an unparsable value falls back to the default rather than
stopping the app, because the tray applet has nowhere useful to report a startup
error to.
"""
import configparser
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from loguru import logger

CONFIG_FILENAME = "config.ini"
SECTION = "time_awareness"


@dataclass(frozen=True)
class Config:
    """Runtime settings. Field names match the keys in config.ini."""

    # Minutes without keyboard or mouse activity before the session ends.
    idle_threshold_minutes: float = 10.0
    # How often the daemon checks idle time.
    poll_interval_seconds: float = 5.0
    # A gap larger than this between two checks means the machine was suspended.
    sleep_detection_threshold_seconds: float = 30.0
    # Subscribe to D-Bus screen lock and suspend signals.
    monitor_lock_and_sleep: bool = True
    # How often the tray icon and menu are refreshed.
    tray_refresh_seconds: int = 10
    # Sessions listed in the History dialog; 0 means no limit.
    max_history_rows: int = 500
    # Log every idle check at debug level.
    verbose: bool = False


# Lower bounds that keep a setting meaningful. A poll interval of zero would
# spin the CPU; a zero idle threshold would end the session on every check.
_MINIMUMS = {
    "idle_threshold_minutes": 0.1,
    "poll_interval_seconds": 0.5,
    "sleep_detection_threshold_seconds": 1.0,
    "tray_refresh_seconds": 1,
    "max_history_rows": 0,
}

DEFAULT_CONFIG_TEMPLATE = """\
# Time Awareness configuration.
#
# Restart the app for changes to take effect.
# Delete this file to restore the defaults.

[time_awareness]

# End the session after this many minutes without keyboard or mouse activity.
idle_threshold_minutes = 10

# How often the daemon checks idle time, in seconds. A lower value reacts faster
# but wakes the CPU more often.
poll_interval_seconds = 5

# A gap larger than this between two consecutive checks is treated as the
# machine having been suspended, and the session is closed at the last check.
# Must be larger than poll_interval_seconds, or every normal check looks like a
# suspend.
sleep_detection_threshold_seconds = 30

# End the session when the screen locks or the system suspends, and start a new
# one on unlock or resume. Requires D-Bus.
monitor_lock_and_sleep = true

# How often the tray icon and menu are refreshed, in seconds.
tray_refresh_seconds = 10

# Maximum number of sessions listed in the History dialog. 0 means no limit;
# with a long history that dialog can take a while to open.
max_history_rows = 500

# Log every idle check at debug level. Noisy - for troubleshooting only.
verbose = false
"""


def _coerce(parser: configparser.SectionProxy, key: str, default: Any) -> Any:
    """Read one key with the type of its default, falling back on bad input."""
    if key not in parser:
        return default
    try:
        if isinstance(default, bool):  # before int: bool is a subclass of int
            return parser.getboolean(key)
        if isinstance(default, int):
            return parser.getint(key)
        if isinstance(default, float):
            return parser.getfloat(key)
        return parser.get(key)
    except ValueError:
        logger.warning("Config value for '{}' is not valid ({!r}); using default {}.",
                       key, parser.get(key), default)
        return default


def _apply_bounds(config: Config) -> Config:
    """Clamp settings to their minimums and keep the two thresholds consistent."""
    corrections = {}

    for name, minimum in _MINIMUMS.items():
        value = getattr(config, name)
        if value < minimum:
            logger.warning("Config '{}' is {}, below the minimum {}; using the minimum.",
                           name, value, minimum)
            corrections[name] = minimum

    poll = corrections.get("poll_interval_seconds", config.poll_interval_seconds)
    sleep_threshold = corrections.get("sleep_detection_threshold_seconds",
                                      config.sleep_detection_threshold_seconds)
    if sleep_threshold <= poll:
        # Otherwise the gap between two ordinary checks exceeds the threshold and
        # every single check is misread as a suspend, ending the session forever.
        corrected = poll * 2
        logger.warning("Config 'sleep_detection_threshold_seconds' ({}) must exceed "
                       "'poll_interval_seconds' ({}); using {}.", sleep_threshold, poll, corrected)
        corrections["sleep_detection_threshold_seconds"] = corrected

    return replace(config, **corrections) if corrections else config


def write_default_config(path: Path) -> bool:
    """
    Write the commented default configuration file.

    Args:
        path (Path): Destination file.

    Returns:
        bool: True if written, False if it could not be created.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        logger.info("Wrote default configuration to {}", path)
        return True
    except OSError as e:
        logger.error("Failed to write default configuration to {}: {}", path, e)
        return False


def load_config(app_dir: Path, create_missing: bool = True) -> Config:
    """
    Load the configuration, falling back to defaults for anything unusable.

    Args:
        app_dir (Path): Application directory holding config.ini.
        create_missing (bool): Write the commented default file if absent.

    Returns:
        Config: The effective configuration.
    """
    path = Path(app_dir) / CONFIG_FILENAME

    if not path.exists():
        if create_missing:
            write_default_config(path)
        return Config()

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError) as e:
        logger.error("Failed to read configuration {}: {}; using defaults.", path, e)
        return Config()

    if not parser.has_section(SECTION):
        logger.warning("Configuration {} has no [{}] section; using defaults.", path, SECTION)
        return Config()

    section = parser[SECTION]
    defaults = Config()
    values = {f.name: _coerce(section, f.name, getattr(defaults, f.name)) for f in fields(Config)}

    unknown = set(section) - {f.name for f in fields(Config)}
    if unknown:
        logger.warning("Ignoring unknown configuration keys: {}", sorted(unknown))

    config = _apply_bounds(Config(**values))
    logger.info("Loaded configuration from {}: {}", path, config)
    return config
