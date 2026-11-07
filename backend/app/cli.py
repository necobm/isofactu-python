"""Management commands: ``python -m app.cli --help`` (or ``isofactu --help`` once installed).

python -m app.cli users create-super-admin --email admin@example.com   # prompts for the password
python -m app.cli fixtures load --invoices 30 --seed 42
python -m app.cli fixtures load --purge --yes
python -m app.cli fixtures purge --yes
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from pydantic import ValidationError

from app.accounts.repository import UserRepository
from app.accounts.role import Role
from app.accounts.schemas import ActivationRequest, UserCreate
from app.accounts.service import AccountService, EmailAlreadyTaken
from app.core.config import get_settings
from app.core.database import dispose_engine, get_session_factory
from app.core.mail import get_mailer
from app.fixtures import DEMO_TENANT_PASSWORD, load_fixtures, purge_fixtures

app = typer.Typer(no_args_is_help=True, help="Isofactu management commands.")
users_app = typer.Typer(no_args_is_help=True, help="Manage user accounts.")
fixtures_app = typer.Typer(no_args_is_help=True, help="Generate or remove fixture data.")
app.add_typer(users_app, name="users")
app.add_typer(fixtures_app, name="fixtures")


def _run(coro):
    try:
        return asyncio.run(coro)
    finally:
        asyncio.run(dispose_engine())


def _guard_production(force: bool) -> None:
    settings = get_settings()
    if settings.app_env == "prod" and not force:
        typer.secho(
            "Refusing to touch a production database (APP_ENV=prod). Use --force.", fg="red"
        )
        raise typer.Exit(code=2)


@users_app.command("create-super-admin")
def users_create_super_admin(
    email: Annotated[str, typer.Option(help="E-mail used to log in")],
    password: Annotated[
        str,
        typer.Option(
            prompt=True,
            confirmation_prompt=True,
            hide_input=True,
            envvar="SUPER_ADMIN_PASSWORD",
            help="Prompted for when omitted",
        ),
    ],
    name: Annotated[str, typer.Option(help="Display name")] = "",
    if_missing: Annotated[
        bool, typer.Option("--if-missing", help="Do nothing if the e-mail is already taken")
    ] = False,
) -> None:
    """Create an active SUPER_ADMIN account (the entry point of a fresh installation)."""
    try:
        UserCreate(email=email)
        ActivationRequest(password=password)
    except ValidationError as exc:
        typer.secho("; ".join(error["msg"] for error in exc.errors()), fg="red")
        raise typer.Exit(code=2) from None

    async def run() -> str:
        settings = get_settings()
        async with get_session_factory()() as session:
            if if_missing and await UserRepository(session).find_by_email(email) is not None:
                return "exists"
            service = AccountService(session, settings, get_mailer())
            await service.create_super_admin(email=email, password=password, name=name)
            await session.commit()
            return "created"

    try:
        outcome = _run(run())
    except EmailAlreadyTaken as exc:
        typer.secho(str(exc), fg="red")
        raise typer.Exit(code=1) from None
    if outcome == "exists":
        typer.secho(
            f"An account with the e-mail {email} already exists; nothing done.", fg="yellow"
        )
    else:
        typer.secho(f"{Role.SUPER_ADMIN.value} account {email} created.", fg="green")


@fixtures_app.command("load")
def fixtures_load(
    invoices: Annotated[int, typer.Option(min=0, help="Number of invoices to generate")] = 20,
    clients: Annotated[int, typer.Option(min=1, help="Number of client subjects")] = 6,
    seed: Annotated[int | None, typer.Option(help="Seed for reproducible data")] = None,
    purge: Annotated[bool, typer.Option(help="Delete existing data first")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmations")] = False,
    force: Annotated[bool, typer.Option(help="Allow running with APP_ENV=prod")] = False,
) -> None:
    """Populate the database with generated clients, invoices and lines, owned by the
    demo tenant account (created, with generated fiscal data, if missing)."""
    _guard_production(force)
    if purge and not yes:
        typer.confirm("This will DELETE all existing invoices and subjects. Continue?", abort=True)

    async def run():
        async with get_session_factory()() as session:
            report = await load_fixtures(
                session,
                clients=clients,
                invoices=invoices,
                seed=seed,
                purge=purge,
                password_hash_rounds=get_settings().password_hash_rounds,
            )
            await session.commit()
            return report

    report = _run(run())
    typer.secho(
        f"Database now holds {report.subjects} subjects, {report.invoices} invoices "
        f"and {report.lines} lines, owned by {report.owner} (password: {DEMO_TENANT_PASSWORD}).",
        fg="green",
    )


@fixtures_app.command("purge")
def fixtures_purge(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    force: Annotated[bool, typer.Option(help="Allow running with APP_ENV=prod")] = False,
) -> None:
    """Delete every invoice, line and subject (user accounts are kept)."""
    _guard_production(force)
    if not yes:
        typer.confirm("This will DELETE all invoices and subjects. Continue?", abort=True)

    async def run():
        async with get_session_factory()() as session:
            await purge_fixtures(session)
            await session.commit()

    _run(run())
    typer.secho("All invoicing data removed.", fg="green")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
