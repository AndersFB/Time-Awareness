import datetime
import pytest
from unittest.mock import MagicMock, patch

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
    'gi.repository.GLib': MagicMock(),
    'PIL': MagicMock(),
    'PIL.Image': MagicMock(),
    'PIL.ImageDraw': MagicMock(),
    'PIL.ImageFont': MagicMock(),
    'loguru': MagicMock(),
}):
    from app import format_duration, format_time, format_date, TrayApp

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

@patch('app.TimeAwareness')
@patch('app.AppIndicator3')
@patch('app.Gtk')
@patch('app.Path')
def test_tray_app_init(mock_path, mock_gtk, mock_indicator, mock_ta):
    mock_path.return_value.exists.return_value = True
    mock_ta.return_value.current_session_info.return_value = None
    mock_ta.return_value.total_time_today.return_value = datetime.timedelta(minutes=10)
    mock_ta.return_value.previous_session.return_value = None
    mock_gtk.Menu.return_value = MagicMock()
    mock_indicator.Indicator.new.return_value = MagicMock()
    app = TrayApp(update_app_interval=1)
    assert isinstance(app, TrayApp)
    assert hasattr(app, "indicator")
    assert hasattr(app, "menu")
