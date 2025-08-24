import pytest
from peewee import SqliteDatabase
from loguru import logger
import sys

from database import database_proxy, Session, MetaData

@pytest.fixture
def enable_logging():
    """Automatically enable Loguru logging for all tests."""
    logger.remove()
    logger.add(sys.stdout, level="DEBUG", format="{time} {level} {message}")
    yield


@pytest.fixture
def use_in_memory_db(enable_logging):
    """Create an in-memory database for testing."""
    test_db = SqliteDatabase(':memory:', autoconnect=False)
    database_proxy.initialize(test_db)
    test_db.connect()
    test_db.create_tables([Session, MetaData], safe=True)
    yield test_db
    test_db.close()
