"""Test fixtures.

Integration tests run against a real PostgreSQL database named `<db>_test` (derived from
DATABASE_URL, or set explicitly with TEST_DATABASE_URL). The database is created if
missing, migrated with Alembic, and its tables are truncated before every test.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        base = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://app:app@127.0.0.1:5433/isofactu"
        )
        parsed = make_url(base)
        # NB: str(url) masks the password as "***"; render it explicitly.
        url = parsed.set(database=f"{parsed.database}_test").render_as_string(hide_password=False)
    return url


# Must happen before `app.*` is imported so that settings pick up the test database.
os.environ["DATABASE_URL"] = _test_database_url()
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("PUBLIC_DIR", str(BACKEND_DIR / "tests" / "_no_public"))

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_session  # noqa: E402
from app.fixtures import (  # noqa: E402
    InvoiceFactory,
    InvoiceLineFactory,
    SubjectFactory,
    bind_session,
    reseed,
)
from app.invoicing.models import Invoice, Subject  # noqa: E402
from app.main import create_app  # noqa: E402

TABLES = ("invoice_line", "invoice", "subject")


def _ensure_database_exists(url: str) -> None:
    import psycopg

    parsed = make_url(url)
    admin = parsed.set(database="postgres", drivername="postgresql")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (parsed.database,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{parsed.database}"')


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Create + migrate the test database once per test session (sync, outside the loop)."""
    from alembic import command
    from alembic.config import Config

    url = get_settings().database_url
    _ensure_database_exists(url)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(scope="session")
async def engine(migrated_database: None):
    engine = create_async_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    from httpx import ASGITransport, AsyncClient

    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# -- data factories ---------------------------------------------------------------------
# factory_boy factories bound to the test session. `SubjectFactory()` adds the object to the
# session (flushed automatically before the next query); use `.build()` for transient objects.


@pytest.fixture
def factories(session: AsyncSession) -> Iterator[None]:
    """Bind the factories to the test session for the duration of the test."""
    reseed(12345)  # deterministic data per test
    with bind_session(session):
        yield


@pytest.fixture
def subject_factory(factories: None) -> type[SubjectFactory]:
    return SubjectFactory


@pytest.fixture
def invoice_factory(factories: None) -> type[InvoiceFactory]:
    return InvoiceFactory


@pytest.fixture
def invoice_line_factory(factories: None) -> type[InvoiceLineFactory]:
    return InvoiceLineFactory


@pytest_asyncio.fixture
async def subject(subject_factory: type[SubjectFactory], session: AsyncSession) -> Subject:
    """A persisted subject."""
    subject = subject_factory()
    await session.flush()
    return subject


@pytest_asyncio.fixture
async def invoice(invoice_factory: type[InvoiceFactory], session: AsyncSession) -> Invoice:
    """A persisted invoice with issuer, recipient and lines."""
    invoice = invoice_factory()
    await session.flush()
    return invoice
