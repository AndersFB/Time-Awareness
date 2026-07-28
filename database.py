import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from loguru import logger
from peewee import SqliteDatabase, Model, DateTimeField, FloatField, TextField, DatabaseProxy, fn

database_proxy = DatabaseProxy()

class BaseModel(Model):
    class Meta:
        database = database_proxy

class Session(BaseModel):
    start = DateTimeField(index=True)
    end = DateTimeField(index=True)
    duration = FloatField()  # Store duration in seconds

class MetaData(BaseModel):
    key = TextField(unique=True)
    value = TextField()

def configure_database(database: Path):
    """
    Configure and initialize the SQLite database connection using the provided path.

    Args:
        database (Path): Path to the SQLite database file.

    Returns:
        SqliteDatabase: The configured database instance.
    """
    logger.info("Configuring database: {}", database)
    # WAL + busy_timeout: the GTK main thread (lock handler, menu refresh) and
    # the daemon thread both use the database; without these, concurrent access
    # sporadically fails with "database is locked".
    db = SqliteDatabase(
        database.as_posix(),
        autoconnect=False,
        pragmas={
            "journal_mode": "wal",
            "busy_timeout": 5000,
            "synchronous": "normal",
        },
    )
    database_proxy.initialize(db)
    logger.info("Database configured successfully: {}", database)
    return db

def _as_date(value: Any) -> Optional[datetime.date]:
    """
    Normalise a value returned for an SQL ``date(...)`` expression to a date.

    Depending on the field converters peewee applies, the value comes back as a
    ``datetime``, a ``date`` or the raw ``YYYY-MM-DD`` string.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def with_database(func):
    """
    Decorator to ensure database connection is open for the wrapped function.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if database is already connected
        was_closed = database_proxy.is_closed()
        if was_closed:
            database_proxy.connect()
        try:
            return func(*args, **kwargs)
        finally:
            # Only close if we opened the connection
            if was_closed and not database_proxy.is_closed():
                database_proxy.close()
    return wrapper

@with_database
def create_tables_if_not_exist():
    """
    Create Session and MetaData tables if they do not exist.
    """
    tables_to_create = []
    db = database_proxy.obj
    if not db.table_exists('session'):
        tables_to_create.append(Session)
    if not db.table_exists('metadata'):
        tables_to_create.append(MetaData)
    if tables_to_create:
        db.create_tables(tables_to_create, safe=True)
        logger.info("Tables created: {}", [t._meta.table_name for t in tables_to_create])
    else:
        logger.info("All tables already exist")

@with_database
def save_session(start: datetime.datetime, end: datetime.datetime, duration: datetime.timedelta) -> bool:
    """
    Save a session record to the database.

    Args:
        start (datetime): Session start time.
        end (datetime): Session end time.
        duration (timedelta): Duration of the session.

    Returns:
        bool: True if saved successfully, False otherwise.
    """
    try:
        Session.create(start=start, end=end, duration=duration.total_seconds())
        logger.info("Session saved: {} - {} (duration: {})", start, end, duration)
        return True
    except Exception as e:
        logger.error("Failed to save session: {}", e)
        return False

@with_database
def get_sessions(return_count: bool = False) -> Union[int, List[Tuple[datetime.datetime, datetime.datetime, datetime.timedelta]]]:
    """
    Retrieve all session records from the database.

    Args:
        return_count (bool): If True, return the number of sessions instead of the session list.

    Returns:
        int: Number of sessions if return_count is True.
        list: List of tuples (start, end, duration) if return_count is False.
    """
    if return_count:
        try:
            return Session.select().count()
        except Exception as e:
            logger.error("Failed to count sessions: {}", e)
            return 0

    try:
        history = [
            (s.start, s.end, datetime.timedelta(seconds=s.duration))
            for s in Session.select().order_by(Session.start.desc())
        ]
        logger.debug("Fetched {} sessions from history", len(history))
        return history
    except Exception as e:
        logger.error("Failed to fetch session history: {}", e)
        return []

@with_database
def set_metadata(key: str, value: Any) -> bool:
    """
    Set a metadata key-value pair.

    Args:
        key (str): Metadata key.
        value (Any): Metadata value.

    Returns:
        bool: True if set successfully, False otherwise.
    """
    try:
        MetaData.insert(key=key, value=str(value)).on_conflict_replace().execute()
        # debug level: the daemon writes last_seen_time on every poll and info
        # level would flood the log file.
        logger.debug("Metadata set: {} = {}", key, value)
        return True
    except Exception as e:
        logger.error("Failed to set metadata '{}': {}", key, e)
        return False

@with_database
def get_metadata(key: str, default: Any = None):
    """
    Get a metadata value by key.

    Args:
        key (str): Metadata key.
        default (Any): Default value if key not found.

    Returns:
        Any: Metadata value or default.
    """
    try:
        entry = MetaData.get_or_none(MetaData.key == key)
        logger.debug("Metadata fetched: {} = {}", key, entry.value if entry else default)
        return entry.value if entry else default
    except Exception as e:
        logger.error("Failed to get metadata '{}': {}", key, e)
        return default

@with_database
def set_metadata_bulk(items: Dict[str, Any]) -> bool:
    """
    Set several metadata key-value pairs in a single transaction.

    Writing related state (e.g. the whole SessionManager state) through one call
    keeps it atomic and costs one connection instead of one per key.

    Args:
        items (dict): Mapping of metadata key to value.

    Returns:
        bool: True if set successfully, False otherwise.
    """
    if not items:
        return True
    try:
        rows = [{"key": key, "value": str(value)} for key, value in items.items()]
        with database_proxy.obj.atomic():
            MetaData.insert_many(rows).on_conflict_replace().execute()
        logger.debug("Metadata set: {}", items)
        return True
    except Exception as e:
        logger.error("Failed to set metadata {}: {}", list(items), e)
        return False

@with_database
def get_metadata_bulk(keys: Iterable[str]) -> Dict[str, str]:
    """
    Get several metadata values in a single query.

    Args:
        keys (iterable): Metadata keys to fetch.

    Returns:
        dict: Mapping of key to value for the keys that exist.
    """
    keys = list(keys)
    if not keys:
        return {}
    try:
        found = {m.key: m.value for m in MetaData.select().where(MetaData.key.in_(keys))}
        logger.debug("Metadata fetched: {}", found)
        return found
    except Exception as e:
        logger.error("Failed to get metadata {}: {}", keys, e)
        return {}

@with_database
def get_sessions_since(since_dt: datetime.datetime):
    """
    Get sessions started since a given datetime.

    Args:
        since_dt (datetime): Start datetime.

    Returns:
        list: List of tuples (start, end, duration).
    """
    try:
        query = Session.select().where(Session.start >= since_dt).order_by(Session.start)
        history = [
            (s.start, s.end, datetime.timedelta(seconds=s.duration))
            for s in query
        ]
        logger.debug("Fetched {} sessions since {}", len(history), since_dt)
        return history
    except Exception as e:
        logger.error("Failed to fetch sessions since '{}': {}", since_dt, e)
        return []

@with_database
def get_sessions_by_weekday():
    """
    Get sessions grouped by weekday.

    Returns:
        dict: Mapping weekday (int) to list of durations (timedelta).
    """
    try:
        weekday_histories = {}
        for s in Session.select(Session.start, Session.duration):
            weekday = s.start.weekday()
            duration = datetime.timedelta(seconds=s.duration)
            if weekday not in weekday_histories:
                weekday_histories[weekday] = []
            weekday_histories[weekday].append(duration)
        logger.debug("Fetched sessions grouped by weekday")
        return weekday_histories
    except Exception as e:
        logger.error("Failed to fetch sessions by weekday: {}", e)
        return {}

@with_database
def get_daily_totals(since: Optional[datetime.date] = None) -> Dict[datetime.date, datetime.timedelta]:
    """
    Get the total tracked time per calendar day, aggregated in SQL.

    Sessions are stored split at midnight, so grouping by the start date yields
    exact daily totals. Aggregating in SQL keeps statistics O(days) instead of
    loading every session row into Python.

    Args:
        since (date): Only include days on or after this date. None for all days.

    Returns:
        dict: Mapping of date to total duration.
    """
    try:
        day = fn.DATE(Session.start)
        query = Session.select(day.alias("day"), fn.SUM(Session.duration).alias("total")).group_by(day)
        if since is not None:
            query = query.where(Session.start >= datetime.datetime.combine(since, datetime.time.min))
        totals = {}
        for row in query.dicts():
            day_value = _as_date(row["day"])
            if day_value is None:
                logger.warning("Skipping daily total with unparsable day: {}", row["day"])
                continue
            totals[day_value] = datetime.timedelta(seconds=float(row["total"] or 0))
        logger.debug("Fetched daily totals for {} day(s)", len(totals))
        return totals
    except Exception as e:
        logger.error("Failed to fetch daily totals: {}", e)
        return {}

@with_database
def get_total_for_day(day: datetime.date) -> datetime.timedelta:
    """
    Get the total tracked time for a single day, summed in SQL.

    Args:
        day (date): The day to total.

    Returns:
        timedelta: Total tracked time for that day (zero if none).
    """
    try:
        start_dt = datetime.datetime.combine(day, datetime.time.min)
        end_dt = datetime.datetime.combine(day, datetime.time.max)
        total = (Session
                 .select(fn.SUM(Session.duration))
                 .where((Session.start >= start_dt) & (Session.start <= end_dt))
                 .scalar())
        logger.debug("Fetched total for {}: {}", day, total)
        return datetime.timedelta(seconds=float(total or 0))
    except Exception as e:
        logger.error("Failed to fetch total for '{}': {}", day, e)
        return datetime.timedelta()

@with_database
def get_average_session_duration() -> datetime.timedelta:
    """
    Get the mean duration across all stored sessions, averaged in SQL.

    Returns:
        timedelta: Average session duration (zero if there are no sessions).
    """
    try:
        average = Session.select(fn.AVG(Session.duration)).scalar()
        logger.debug("Fetched average session duration: {}", average)
        return datetime.timedelta(seconds=float(average or 0))
    except Exception as e:
        logger.error("Failed to fetch average session duration: {}", e)
        return datetime.timedelta()

@with_database
def get_sessions_for_day(day: datetime.date):
    """
    Get all sessions for a specific day.

    Args:
        day (date): The day to fetch sessions for.

    Returns:
        list: List of tuples (start, end, duration).
    """
    try:
        start_dt = datetime.datetime.combine(day, datetime.time.min)
        end_dt = datetime.datetime.combine(day, datetime.time.max)
        query = Session.select().where(
            (Session.start >= start_dt) & (Session.start <= end_dt)
        ).order_by(Session.start)
        history = [
            (s.start, s.end, datetime.timedelta(seconds=s.duration))
            for s in query
        ]
        logger.debug("Fetched {} sessions for {}", len(history), day)
        return history
    except Exception as e:
        logger.error("Failed to fetch sessions for '{}': {}", day, e)
        return []

@with_database
def get_previous_session(verbose: bool = True):
    """
    Retrieve the most recent session from the database.

    Args:
        verbose (bool): If True, logs details about the fetched session.

    Returns:
        tuple: (start, end, duration) of the previous session, or None if no sessions exist.
    """
    try:
        session = Session.select().order_by(Session.start.desc()).first()
        if session:
            result = (
                session.start,
                session.end,
                datetime.timedelta(seconds=session.duration)
            )
            if verbose:
                logger.debug("Fetched previous session: {} - {}", session.start, session.end)
            return result
        else:
            if verbose:
                logger.debug("No previous session found")
            return None
    except Exception as e:
        logger.error("Failed to fetch previous session: {}", e)
        return None

@with_database
def get_days_tracked():
    """
    Get the number of unique days with tracked sessions.

    Returns:
        int: Number of days tracked.
    """
    try:
        # Counted in SQL: loading every session row just to count distinct dates
        # grows linearly with history size for a number that never changes shape.
        days = Session.select(fn.COUNT(fn.DISTINCT(fn.DATE(Session.start)))).scalar()
        logger.debug("Fetched days tracked: {}", days)
        return int(days or 0)
    except Exception as e:
        logger.error("Failed to fetch days tracked: {}", e)
        return 0

@with_database
def reset_database():
    """
    Delete all sessions and metadata from the database.
    """
    db = database_proxy.obj
    with db.atomic():
        Session.delete().execute()
        MetaData.delete().execute()
    logger.debug("Database reset: all sessions and metadata deleted")
