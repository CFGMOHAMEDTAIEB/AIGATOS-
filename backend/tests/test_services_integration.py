import os
from urllib.parse import unquote, urlsplit

import pytest
from redis import Redis
from sqlalchemy import create_engine, text


def _isolated_test_database_url() -> tuple[str, str, str]:
    """Require an explicitly named local test database before opening a socket."""
    test_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not test_url:
        pytest.fail(
            "TEST_DATABASE_URL is required for integration tests; no database connection was opened.",
            pytrace=False,
        )

    parsed = urlsplit(test_url)
    test_name = unquote(parsed.path.lstrip("/"))
    test_host = (parsed.hostname or "").lower()
    business_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://aigatos:aigatos_dev@127.0.0.1:55432/aigatos?connect_timeout=5",
    ).strip()
    business = urlsplit(business_url)
    if test_url == business_url:
        pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL; no connection was opened.", pytrace=False)
    if not parsed.scheme.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL; no connection was opened.", pytrace=False)
    if test_host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("TEST_DATABASE_URL must target a local isolated PostgreSQL host; no connection was opened.", pytrace=False)
    if not test_name or "test" not in test_name.lower() or "tmp" not in test_name.lower():
        pytest.fail("The TEST_DATABASE_URL database name must clearly contain 'test' and 'tmp'; no connection was opened.", pytrace=False)
    if parsed.port is None or parsed.port == business.port:
        pytest.fail("TEST_DATABASE_URL must use an explicit port distinct from DATABASE_URL; no connection was opened.", pytrace=False)
    same_target = (
        parsed.scheme == business.scheme
        and (parsed.hostname or "").lower() == (business.hostname or "").lower()
        and parsed.port == business.port
        and test_name == unquote(business.path.lstrip("/"))
    )
    if same_target:
        pytest.fail("TEST_DATABASE_URL resolves to the DATABASE_URL database; no connection was opened.", pytrace=False)
    return test_url, test_host, test_name


def test_integration_database_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    with pytest.raises(pytest.fail.Exception, match="no database connection was opened"):
        _isolated_test_database_url()


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://user:secret@127.0.0.1:55432/aigatos_test_tmp",
    "postgresql+psycopg://user:secret@example.invalid:55433/aigatos_test_tmp",
    "postgresql+psycopg://user:secret@127.0.0.1:55433/aigatos_tmp",
    "postgresql+psycopg://business:secret@127.0.0.1:55432/aigatos",
])
def test_integration_database_guard_rejects_unsafe_target(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://business:secret@127.0.0.1:55432/aigatos")
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    with pytest.raises(pytest.fail.Exception, match="no connection was opened"):
        _isolated_test_database_url()


def test_integration_database_guard_accepts_only_named_distinct_target(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://business:secret@127.0.0.1:55432/aigatos")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://tester:secret@127.0.0.1:55433/aigatos_test_tmp")
    _, host, name = _isolated_test_database_url()
    assert (host, name) == ("127.0.0.1", "aigatos_test_tmp")


@pytest.mark.integration
def test_postgresql_and_redis_are_reachable():
    database_url, database_host, database_name = _isolated_test_database_url()
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    print(f"Isolated integration target: database={database_name} host={database_host}")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
        assert Redis.from_url(redis_url, socket_connect_timeout=3).ping() is True
    finally:
        engine.dispose()
