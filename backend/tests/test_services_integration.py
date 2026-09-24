import os

import pytest
from redis import Redis
from sqlalchemy import create_engine, text


@pytest.mark.integration
def test_postgresql_and_redis_are_reachable():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://aigatos:aigatos_dev@127.0.0.1:55432/aigatos?connect_timeout=5",
    )
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
        assert Redis.from_url(redis_url, socket_connect_timeout=3).ping() is True
    finally:
        engine.dispose()
