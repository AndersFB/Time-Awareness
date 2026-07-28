import itertools
import pytest
from peewee import SqliteDatabase
from loguru import logger
import sys

from database import database_proxy, Session, MetaData

_db_counter = itertools.count()

@pytest.fixture
def enable_logging():
    """Automatically enable Loguru logging for all tests."""
    logger.remove()
    logger.add(sys.stdout, level="DEBUG", format="{time} {level} {message}")
    yield


@pytest.fixture
def use_in_memory_db(enable_logging):
    """
    Create an in-memory database for testing.

    Uses a named shared-cache database rather than plain ':memory:'. Peewee keeps
    connection state per thread, so with ':memory:' any background thread (the
    daemon) would silently open its own empty database and every query it makes
    would fail unnoticed. A unique name per test keeps tests isolated; the
    fixture's own connection keeps the database alive for its duration.
    """
    name = f"file:testdb{next(_db_counter)}?mode=memory&cache=shared"
    test_db = SqliteDatabase(name, autoconnect=False, uri=True, pragmas={"busy_timeout": 5000})
    database_proxy.initialize(test_db)
    test_db.connect()
    test_db.create_tables([Session, MetaData], safe=True)
    yield test_db
    test_db.close()
