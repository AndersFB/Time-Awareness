import pytest

from config import CONFIG_FILENAME, Config, load_config, write_default_config


@pytest.fixture(autouse=True)
def logging_enabled(enable_logging):
    pass


def write_config(app_dir, body: str):
    (app_dir / CONFIG_FILENAME).write_text(body, encoding="utf-8")


# ------------------------------
# defaults and file creation
# ------------------------------
def test_missing_config_writes_defaults_and_returns_them(tmp_path):
    config = load_config(tmp_path)

    assert config == Config()
    assert (tmp_path / CONFIG_FILENAME).exists()


def test_missing_config_can_skip_file_creation(tmp_path):
    config = load_config(tmp_path, create_missing=False)

    assert config == Config()
    assert not (tmp_path / CONFIG_FILENAME).exists()


def test_written_default_config_reloads_to_the_defaults(tmp_path):
    """The commented template must parse back to exactly the dataclass defaults."""
    load_config(tmp_path)  # writes the template
    assert load_config(tmp_path) == Config()


def test_write_default_config_creates_missing_parents(tmp_path):
    path = tmp_path / "nested" / "dir" / CONFIG_FILENAME
    assert write_default_config(path) is True
    assert path.exists()


# ------------------------------
# parsing
# ------------------------------
def test_values_are_read_from_the_file(tmp_path):
    write_config(tmp_path, """
[time_awareness]
idle_threshold_minutes = 3.5
poll_interval_seconds = 2
sleep_detection_threshold_seconds = 45
monitor_lock_and_sleep = false
tray_refresh_seconds = 4
max_history_rows = 0
verbose = true
""")
    config = load_config(tmp_path)

    assert config.idle_threshold_minutes == 3.5
    assert config.poll_interval_seconds == 2
    assert config.sleep_detection_threshold_seconds == 45
    assert config.monitor_lock_and_sleep is False
    assert config.tray_refresh_seconds == 4
    assert config.max_history_rows == 0
    assert config.verbose is True


def test_omitted_keys_keep_their_defaults(tmp_path):
    write_config(tmp_path, "[time_awareness]\nidle_threshold_minutes = 25\n")
    config = load_config(tmp_path)

    assert config.idle_threshold_minutes == 25
    assert config.poll_interval_seconds == Config().poll_interval_seconds
    assert config.monitor_lock_and_sleep == Config().monitor_lock_and_sleep


def test_unparsable_value_falls_back_to_its_default(tmp_path):
    write_config(tmp_path, """
[time_awareness]
idle_threshold_minutes = soon
tray_refresh_seconds = 7
""")
    config = load_config(tmp_path)

    assert config.idle_threshold_minutes == Config().idle_threshold_minutes
    assert config.tray_refresh_seconds == 7  # the rest of the file still applies


def test_missing_section_falls_back_to_defaults(tmp_path):
    write_config(tmp_path, "[something_else]\nidle_threshold_minutes = 99\n")
    assert load_config(tmp_path) == Config()


def test_malformed_file_falls_back_to_defaults(tmp_path):
    write_config(tmp_path, "this is not an ini file at all")
    assert load_config(tmp_path) == Config()


def test_unknown_keys_are_ignored(tmp_path):
    write_config(tmp_path, "[time_awareness]\nnot_a_setting = 1\nverbose = true\n")
    config = load_config(tmp_path)

    assert config.verbose is True
    assert not hasattr(config, "not_a_setting")


# ------------------------------
# bounds
# ------------------------------
@pytest.mark.parametrize("key,value,attr,minimum", [
    ("idle_threshold_minutes", "0", "idle_threshold_minutes", 0.1),
    ("poll_interval_seconds", "0", "poll_interval_seconds", 0.5),
    ("tray_refresh_seconds", "0", "tray_refresh_seconds", 1),
    ("max_history_rows", "-5", "max_history_rows", 0),
])
def test_values_below_the_minimum_are_clamped(tmp_path, key, value, attr, minimum):
    write_config(tmp_path, f"[time_awareness]\n{key} = {value}\n")
    assert getattr(load_config(tmp_path), attr) == minimum


def test_sleep_threshold_is_raised_above_the_poll_interval(tmp_path):
    """
    A sleep threshold at or below the poll interval makes every ordinary check
    look like a suspend, which would end the session on every iteration.
    """
    write_config(tmp_path, """
[time_awareness]
poll_interval_seconds = 20
sleep_detection_threshold_seconds = 10
""")
    config = load_config(tmp_path)

    assert config.sleep_detection_threshold_seconds > config.poll_interval_seconds
    assert config.sleep_detection_threshold_seconds == 40


def test_sleep_threshold_equal_to_poll_interval_is_corrected(tmp_path):
    write_config(tmp_path, """
[time_awareness]
poll_interval_seconds = 5
sleep_detection_threshold_seconds = 5
""")
    assert load_config(tmp_path).sleep_detection_threshold_seconds == 10


def test_clamped_poll_interval_is_used_for_the_threshold_check(tmp_path):
    """Bounds are applied before the relationship between the two is checked."""
    write_config(tmp_path, """
[time_awareness]
poll_interval_seconds = 0
sleep_detection_threshold_seconds = 0
""")
    config = load_config(tmp_path)

    assert config.poll_interval_seconds == 0.5
    assert config.sleep_detection_threshold_seconds > config.poll_interval_seconds


def test_valid_config_is_left_alone(tmp_path):
    write_config(tmp_path, """
[time_awareness]
poll_interval_seconds = 5
sleep_detection_threshold_seconds = 30
""")
    config = load_config(tmp_path)

    assert config.poll_interval_seconds == 5
    assert config.sleep_detection_threshold_seconds == 30
