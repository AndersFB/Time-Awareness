import datetime
from functools import wraps
from pathlib import Path
from typing import Any, List, Tuple, Union

from loguru import logger
from peewee import SqliteDatabase, Model, DateTimeField, FloatField, TextField, DatabaseProxy

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
    logger.info(f"Configuring database: {database}")
    db = SqliteDatabase(database.as_posix(), autoconnect=False)
    database_proxy.initialize(db)
    logger.info(f"Database configured successfully: {db}")
    return db

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
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            raise
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
        return Session.select().count()

    try:
        history = [
            (s.start, s.end, datetime.timedelta(seconds=s.duration))
            for s in Session.select().order_by(Session.start)
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
        logger.info("Metadata set: {} = {}", key, value)
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
        for s in Session.select():
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
def get_all_sessions():
    """
    Get all session records.

    Returns:
        list: List of tuples (start, end, duration).
    """
    try:
        history = [
            (s.start, s.end, datetime.timedelta(seconds=s.duration))
            for s in Session.select().order_by(Session.start)
        ]
        logger.debug("Fetched all sessions: {}", len(history))
        return history
    except Exception as e:
        logger.error("Failed to fetch all sessions: {}", e)
        return []

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
        days = set()
        for s in Session.select(Session.start):
            days.add(s.start.date())
        logger.debug("Fetched days tracked: {}", len(days))
        return len(days)
    except Exception as e:
        logger.error("Failed to fetch days tracked: {}", e)
        return 0
