import pytest
import datetime
from time_awareness import TimeAwareness


class DummyDateTime(datetime.datetime):
    """A dummy datetime class for monkeypatching now()."""
    @classmethod
    def now(cls):
        return cls(2024, 6, 1, 12, 0, 0)

@pytest.fixture
def ta(monkeypatch, tmp_path):
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    return TimeAwareness(app_dir=tmp_path)

def test_start_and_end_session(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    ta.start_session()
    assert ta.current_session == DummyDateTime.now()
    class EndDateTime(DummyDateTime):
        @classmethod
        def now(cls):
            return cls(2024, 6, 1, 13, 0, 0)
    monkeypatch.setattr(datetime, "datetime", EndDateTime)
    duration = ta.end_session()
    assert duration == datetime.timedelta(hours=1)
    assert ta.current_session is None
    assert ta.session_history[-1][2] == datetime.timedelta(hours=1)

def test_end_session_without_start(tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    with pytest.raises(ValueError):
        ta.end_session()

def test_previous_session(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    ta.start_session()
    ta.end_session()
    assert ta.previous_session()[2] == datetime.timedelta(hours=0)

def test_total_time_today(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    ta.start_session()
    ta.end_session()
    assert ta.total_time_today() == datetime.timedelta(seconds=0)

def test_total_time_yesterday(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    yesterday = DummyDateTime(2024, 5, 31, 10, 0, 0)
    end = DummyDateTime(2024, 5, 31, 11, 0, 0)
    duration = end - yesterday
    ta.session_history.append((yesterday, end, duration))
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    assert ta.total_time_yesterday() == datetime.timedelta(hours=1)

def test_seven_day_average(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    for i in range(7):
        start = DummyDateTime(2024, 5, 25 + i, 10, 0, 0)
        end = DummyDateTime(2024, 5, 25 + i, 11, 0, 0)
        duration = end - start
        ta.session_history.append((start, end, duration))
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    avg = ta.seven_day_average()
    assert avg == datetime.timedelta(hours=1)

def test_weekday_average(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    monday = DummyDateTime(2024, 5, 27, 10, 0, 0)
    monday_end = DummyDateTime(2024, 5, 27, 12, 0, 0)
    tuesday = DummyDateTime(2024, 5, 28, 10, 0, 0)
    tuesday_end = DummyDateTime(2024, 5, 28, 11, 0, 0)
    ta.session_history.append((monday, monday_end, monday_end - monday))
    ta.session_history.append((tuesday, tuesday_end, tuesday_end - tuesday))
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    avg = ta.weekday_average()
    assert avg == datetime.timedelta(hours=1, minutes=30)

def test_total_average(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    s1 = DummyDateTime(2024, 5, 30, 10, 0, 0)
    e1 = DummyDateTime(2024, 5, 30, 11, 0, 0)
    s2 = DummyDateTime(2024, 5, 31, 10, 0, 0)
    e2 = DummyDateTime(2024, 5, 31, 12, 0, 0)
    ta.session_history.append((s1, e1, e1 - s1))
    ta.session_history.append((s2, e2, e2 - s2))
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    avg = ta.total_average()
    assert avg == datetime.timedelta(hours=1, minutes=30)

def test_history(monkeypatch, tmp_path):
    ta = TimeAwareness(app_dir=tmp_path)
    monkeypatch.setattr(datetime, "datetime", DummyDateTime)
    ta.start_session()
    ta.end_session()
    hist = ta.history()
    assert hist["days"] == 1
    assert "total_today" in hist
    assert "seven_day_average" in hist
    assert "weekday_average" in hist
    assert "total_average" in hist
    assert "history" in hist
