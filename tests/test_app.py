import datetime
from unittest.mock import patch, MagicMock

import pytest

def ayatana_available():
    try:
        import gi
        gi.require_version('AyatanaAppIndicator3', '0.1')
        from gi.repository import AyatanaAppIndicator3
        return True
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
    (datetime.datetime(2024, 6, 1), "06.01.2024"),
])
def test_format_date(dt, expected):
    assert format_date(dt) == expected

def test_tray_app_init(use_in_memory_db, monkeypatch, tmp_path):
    import app
    monkeypatch.setattr(app, 'APP_DIR', tmp_path)
    tray_app = app.TrayApp(update_app_interval=1)
    assert isinstance(tray_app, app.TrayApp)
    assert hasattr(tray_app, "indicator")
