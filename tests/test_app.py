import datetime
from unittest.mock import patch, MagicMock

import pytest

def ayatana_available():
    try:
        import gi
        gi.require_version('AyatanaAppIndicator3', '0.1')
        from gi.repository import AyatanaAppIndicator3
        return AyatanaAppIndicator3 is not None
    except Exception:
        return False

pytestmark = pytest.mark.skipif(
    not ayatana_available(),
    reason="AyatanaAppIndicator3 namespace not available"
)

with patch.dict('sys.modules', {
    'gi': MagicMock(),
    'gi.repository': MagicMock(),
    'gi.repository.AyatanaAppIndicator3': MagicMock(),
    'gi.repository.Gtk': MagicMock(),
    'gi.repository.GLib': MagicMock()
}):
    from app import format_duration, format_time, format_date

@pytest.mark.parametrize("td,expected", [
    (None, "-"),
    (datetime.timedelta(hours=2, minutes=15), "2h. 15m."),
    (datetime.timedelta(minutes=45), "45m."),
    (datetime.timedelta(hours=0, minutes=0), "0m."),
])
def test_format_duration(td, expected):
    assert format_duration(td) == expected

@pytest.mark.parametrize("dt,expected", [
    (None, "-"),
    (datetime.datetime(2024, 6, 1, 14, 30), "14:30"),
])
def test_format_time(dt, expected):
    assert format_time(dt) == expected

@pytest.mark.parametrize("dt,expected", [
    (None, "-"),
    (datetime.datetime(2024, 6, 1), "01.06.2024"),
])
def test_format_date(dt, expected):
    assert format_date(dt) == expected

def test_tray_app_init(use_in_memory_db, monkeypatch, tmp_path):
    import app
    monkeypatch.setattr(app, 'APP_DIR', tmp_path)
    tray_app = app.TrayApp(update_app_interval=1)
    try:
        assert isinstance(tray_app, app.TrayApp)
        assert hasattr(tray_app, "indicator")
    finally:
        # Stops the daemon thread, releases the tracking lock and removes the
        # temporary icon directory.
        tray_app.quit()


def test_tray_app_uses_configured_refresh_interval(use_in_memory_db, monkeypatch, tmp_path):
    import app
    from config import CONFIG_FILENAME

    monkeypatch.setattr(app, 'APP_DIR', tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text(
        "[time_awareness]\ntray_refresh_seconds = 7\nmax_history_rows = 12\n", encoding="utf-8")

    tray_app = app.TrayApp()
    try:
        assert tray_app._max_history_rows == 12
        assert tray_app._ta.config.tray_refresh_seconds == 7
    finally:
        tray_app.quit()


def test_second_tray_app_is_refused(use_in_memory_db, monkeypatch, tmp_path):
    import app
    from tracker_lock import TrackerAlreadyRunningError

    monkeypatch.setattr(app, 'APP_DIR', tmp_path)
    first = app.TrayApp(update_app_interval=1)
    try:
        with pytest.raises(TrackerAlreadyRunningError):
            app.TrayApp(update_app_interval=1)
    finally:
        first.quit()
