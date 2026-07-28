import pytest
import datetime

from database import (
    save_session, get_sessions, set_metadata, get_metadata,
    set_metadata_bulk, get_metadata_bulk,
    get_sessions_since, get_sessions_by_weekday, get_sessions_for_day,
    get_previous_session, get_days_tracked,
    get_daily_totals, get_total_for_day, get_average_session_duration
)

@pytest.fixture(autouse=True)
def use_in_memory_db(use_in_memory_db):
    pass

def test_save_and_get_session():
    start = datetime.datetime(2024, 6, 1, 10, 0, 0)
    end = datetime.datetime(2024, 6, 1, 11, 0, 0)
    duration = end - start
    save_session(start, end, duration)
    sessions = get_sessions()
    assert len(sessions) == 1
    assert sessions[0][0] == start
    assert sessions[0][1] == end
    assert sessions[0][2] == duration

def test_metadata():
    set_metadata("foo", "bar")
    assert get_metadata("foo") == "bar"
    assert get_metadata("missing", "default") == "default"

def test_get_sessions_since():
    now = datetime.datetime(2024, 6, 1, 10, 0, 0)
    save_session(now, now + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(now - datetime.timedelta(days=1), now - datetime.timedelta(days=1, hours=-1), datetime.timedelta(hours=1))
    sessions = get_sessions_since(now)
    assert len(sessions) == 1

def test_get_sessions_by_weekday():
    monday = datetime.datetime(2024, 6, 3, 10, 0, 0)
    tuesday = datetime.datetime(2024, 6, 4, 10, 0, 0)
    save_session(monday, monday + datetime.timedelta(hours=2), datetime.timedelta(hours=2))
    save_session(tuesday, tuesday + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    weekday_histories = get_sessions_by_weekday()
    assert monday.weekday() in weekday_histories
    assert tuesday.weekday() in weekday_histories

def test_get_sessions():
    start = datetime.datetime(2024, 6, 1, 10, 0, 0)
    end = datetime.datetime(2024, 6, 1, 11, 0, 0)
    save_session(start, end, end - start)
    sessions = get_sessions()
    assert len(sessions) == 1

def test_get_sessions_for_day():
    day = datetime.date(2024, 6, 1)
    start = datetime.datetime(2024, 6, 1, 10, 0, 0)
    end = datetime.datetime(2024, 6, 1, 11, 0, 0)
    save_session(start, end, end - start)
    sessions = get_sessions_for_day(day)
    assert len(sessions) == 1

def test_get_previous_session():
    start = datetime.datetime(2024, 6, 1, 10, 0, 0)
    end = datetime.datetime(2024, 6, 1, 11, 0, 0)
    save_session(start, end, end - start)
    prev = get_previous_session()
    assert prev[0] == start
    assert prev[1] == end

def test_get_days_tracked():
    day1 = datetime.datetime(2024, 6, 1, 10, 0, 0)
    day2 = datetime.datetime(2024, 6, 2, 10, 0, 0)
    save_session(day1, day1 + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(day2, day2 + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    assert get_days_tracked() == 2

def test_get_days_tracked_counts_each_day_once():
    day = datetime.datetime(2024, 6, 1, 10, 0, 0)
    save_session(day, day + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(day + datetime.timedelta(hours=4), day + datetime.timedelta(hours=5),
                 datetime.timedelta(hours=1))
    assert get_days_tracked() == 1

def test_get_days_tracked_empty():
    assert get_days_tracked() == 0

# ------------------------------
# bulk metadata
# ------------------------------
def test_set_and_get_metadata_bulk():
    assert set_metadata_bulk({"a": 1, "b": "two"}) is True
    assert get_metadata_bulk(["a", "b"]) == {"a": "1", "b": "two"}

def test_get_metadata_bulk_omits_missing_keys():
    set_metadata("present", "yes")
    assert get_metadata_bulk(["present", "absent"]) == {"present": "yes"}

def test_metadata_bulk_handles_empty_input():
    assert set_metadata_bulk({}) is True
    assert get_metadata_bulk([]) == {}

def test_set_metadata_bulk_overwrites_existing_keys():
    set_metadata("k", "old")
    set_metadata_bulk({"k": "new"})
    assert get_metadata("k") == "new"

# ------------------------------
# aggregates
# ------------------------------
def test_get_daily_totals_groups_by_day():
    day1 = datetime.datetime(2024, 6, 1, 10, 0, 0)
    day2 = datetime.datetime(2024, 6, 2, 10, 0, 0)
    save_session(day1, day1 + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(day1 + datetime.timedelta(hours=3), day1 + datetime.timedelta(hours=5),
                 datetime.timedelta(hours=2))
    save_session(day2, day2 + datetime.timedelta(minutes=30), datetime.timedelta(minutes=30))

    assert get_daily_totals() == {
        datetime.date(2024, 6, 1): datetime.timedelta(hours=3),
        datetime.date(2024, 6, 2): datetime.timedelta(minutes=30),
    }

def test_get_daily_totals_respects_since():
    day1 = datetime.datetime(2024, 6, 1, 10, 0, 0)
    day2 = datetime.datetime(2024, 6, 2, 10, 0, 0)
    save_session(day1, day1 + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(day2, day2 + datetime.timedelta(hours=1), datetime.timedelta(hours=1))

    totals = get_daily_totals(since=datetime.date(2024, 6, 2))
    assert list(totals) == [datetime.date(2024, 6, 2)]

def test_get_daily_totals_empty():
    assert get_daily_totals() == {}

def test_get_total_for_day():
    day = datetime.datetime(2024, 6, 1, 10, 0, 0)
    save_session(day, day + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(day + datetime.timedelta(hours=2), day + datetime.timedelta(hours=4),
                 datetime.timedelta(hours=2))
    save_session(day + datetime.timedelta(days=1), day + datetime.timedelta(days=1, hours=1),
                 datetime.timedelta(hours=1))

    assert get_total_for_day(datetime.date(2024, 6, 1)) == datetime.timedelta(hours=3)
    assert get_total_for_day(datetime.date(2024, 6, 3)) == datetime.timedelta()

def test_get_average_session_duration():
    day = datetime.datetime(2024, 6, 1, 10, 0, 0)
    save_session(day, day + datetime.timedelta(hours=1), datetime.timedelta(hours=1))
    save_session(day + datetime.timedelta(hours=2), day + datetime.timedelta(hours=5),
                 datetime.timedelta(hours=3))

    assert get_average_session_duration() == datetime.timedelta(hours=2)

def test_get_average_session_duration_empty():
    assert get_average_session_duration() == datetime.timedelta()
