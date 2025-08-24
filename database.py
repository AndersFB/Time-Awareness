import datetime
from functools import wraps

from peewee import (
    SqliteDatabase, Model, DateTimeField, FloatField, TextField, DatabaseProxy
)
from loguru import logger

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

def configure_database(**kwargs):
    """Configure the database. Supports 'sqlite' or 'mysql'."""
    logger.info(f"Configuring database: kwargs={kwargs}")
    db = SqliteDatabase(kwargs.get('database', 'app.db'), autoconnect=False)
    database_proxy.initialize(db)
    logger.info(f"Database configured successfully: {db}")
    return db

def with_database(func):
    """Decorator to handle database connections."""
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
    """Create tables if they don't exist."""
    database_proxy.create_tables([Session, MetaData], safe=True)
    logger.info("Tables created successfully")

@with_database
def save_session(start, end, duration) -> bool:
    try:
        Session.create(start=start, end=end, duration=duration.total_seconds())
        logger.info("Session saved: {} - {} (duration: {})", start, end, duration)
        return True
    except Exception as e:
        logger.error("Failed to save session: {}", e)
        return False

@with_database
def get_session_history():
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
def set_metadata(key, value) -> bool:
    try:
        MetaData.insert(key=key, value=str(value)).on_conflict_replace().execute()
        logger.info("Metadata set: {} = {}", key, value)
        return True
    except Exception as e:
        logger.error("Failed to set metadata '{}': {}", key, e)
        return False

@with_database
def get_metadata(key: str, default=None):
    try:
        entry = MetaData.get_or_none(MetaData.key == key)
        logger.debug("Metadata fetched: {} = {}", key, entry.value if entry else default)
        return entry.value if entry else default
    except Exception as e:
        logger.error("Failed to get metadata '{}': {}", key, e)
        return default

@with_database
def get_sessions_since(since_dt: datetime.datetime):
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
def get_previous_session():
    try:
        session = Session.select().order_by(Session.start.desc()).first()
        if session:
            result = (
                session.start,
                session.end,
                datetime.timedelta(seconds=session.duration)
            )
            logger.debug("Fetched previous session: {} - {}", session.start, session.end)
            return result
        else:
            logger.debug("No previous session found")
            return None
    except Exception as e:
        logger.error("Failed to fetch previous session: {}", e)
        return None

@with_database
def get_days_tracked():
    try:
        days = set()
        for s in Session.select(Session.start):
            days.add(s.start.date())
        logger.debug("Fetched days tracked: {}", len(days))
        return len(days)
    except Exception as e:
        logger.error("Failed to fetch days tracked: {}", e)
        return 0
