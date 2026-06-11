import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from blunder.models import Base

# The queue relies on Postgres SKIP LOCKED, so these tests need a real Postgres.
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(scope="session")
def engine():
    if not TEST_DB_URL:
        pytest.skip("set TEST_DATABASE_URL or DATABASE_URL to run DB-backed tests")
    eng = create_engine(TEST_DB_URL, future=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"cannot reach test database: {exc}")
    Base.metadata.create_all(eng)  # no-op if migrations already applied
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    """A clean session with the jobs table truncated before each test."""
    SessionFactory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE jobs RESTART IDENTITY CASCADE"))
    s = SessionFactory()
    try:
        yield s
    finally:
        s.close()
