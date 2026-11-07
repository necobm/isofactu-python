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
os.environ["PASSWORD_HASH_ROUNDS"] = "4"  # bcrypt at full strength would dominate the run time
os.environ["SMTP_HOST"] = ""  # never talk to a real mail server (the mailer is overridden anyway)
os.environ["APP_PUBLIC_URL"] = "http://test"

from app.accounts.models import User  # noqa: E402
from app.accounts.role import Role  # noqa: E402
from app.accounts.security import hash_password  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import get_session  # noqa: E402
from app.core.mail import InMemoryMailer, get_mailer  # noqa: E402
from app.fixtures import (  # noqa: E402
    InvoiceFactory,
    InvoiceLineFactory,
    SubjectFactory,
    UserFactory,
    bind_session,
    reseed,
)
from app.invoicing.models import Invoice, Subject  # noqa: E402
from app.main import create_app  # noqa: E402

TABLES = ("invoice_line", "invoice", "subject", "activation_token", "app_setting", "user_account")

# Password of every account created by the `tenant` / `super_admin` fixtures and `login()`.
PASSWORD = "correct-horse-battery"
PASSWORD_HASH = hash_password(PASSWORD, rounds=4)


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


@pytest.fixture
def mailer() -> InMemoryMailer:
    """Captures the e-mails the application sends during the test (`mailer.outbox`)."""
    return InMemoryMailer()


@pytest.fixture
def app(session: AsyncSession, mailer: InMemoryMailer):
    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_mailer] = lambda: mailer
    return app


def _make_client(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def client(app):
    """Anonymous HTTP client (no session cookie)."""
    async with _make_client(app) as client:
        yield client


async def login(client, user: User, password: str = PASSWORD) -> None:
    """Log `client` in as `user` (the session cookie is kept by the client)."""
    response = await client.post(
        "/api/auth/login", json={"email": user.email, "password": password}
    )
    assert response.status_code == 200, response.text


@pytest_asyncio.fixture
async def tenant_client(app, tenant: User):
    """HTTP client logged in as the `tenant` fixture (an ADMIN)."""
    async with _make_client(app) as client:
        await login(client, tenant)
        yield client


@pytest_asyncio.fixture
async def super_admin_client(app, super_admin: User):
    """HTTP client logged in as the `super_admin` fixture."""
    async with _make_client(app) as client:
        await login(client, super_admin)
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


@pytest.fixture
def user_factory(factories: None) -> type[UserFactory]:
    return UserFactory


@pytest_asyncio.fixture
async def tenant(user_factory: type[UserFactory], session: AsyncSession) -> User:
    """A persisted, active ADMIN able to log in with `PASSWORD`."""
    user = user_factory(email="tenant@example.com", name="Tenant", password_hash=PASSWORD_HASH)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def other_tenant(user_factory: type[UserFactory], session: AsyncSession) -> User:
    """A second ADMIN, to check that tenants cannot see each other's data."""
    user = user_factory(email="other@example.com", name="Other", password_hash=PASSWORD_HASH)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def super_admin(user_factory: type[UserFactory], session: AsyncSession) -> User:
    """A persisted, active SUPER_ADMIN able to log in with `PASSWORD`."""
    user = user_factory(
        email="root@example.com", name="Root", role=Role.SUPER_ADMIN, password_hash=PASSWORD_HASH
    )
    await session.flush()
    return user


@pytest_asyncio.fixture
async def subject(
    subject_factory: type[SubjectFactory], tenant: User, session: AsyncSession
) -> Subject:
    """A persisted subject owned by `tenant`."""
    subject = subject_factory(owner=tenant)
    await session.flush()
    return subject


@pytest_asyncio.fixture
async def invoice(
    invoice_factory: type[InvoiceFactory], tenant: User, session: AsyncSession
) -> Invoice:
    """A persisted invoice (issuer, recipient and lines included) owned by `tenant`."""
    invoice = invoice_factory(owner=tenant)
    await session.flush()
    return invoice
