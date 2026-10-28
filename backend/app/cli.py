"""Management commands: ``python -m app.cli --help`` (or ``isofactu --help`` once installed).

python -m app.cli fixtures load --invoices 30 --seed 42
python -m app.cli fixtures load --purge --yes
python -m app.cli fixtures purge --yes
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from app.core.config import get_settings
from app.core.database import dispose_engine, get_session_factory
from app.fixtures import load_fixtures, purge_fixtures

app = typer.Typer(no_args_is_help=True, help="Isofactu management commands.")
fixtures_app = typer.Typer(no_args_is_help=True, help="Generate or remove fixture data.")
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


@fixtures_app.command("load")
def fixtures_load(
    invoices: Annotated[int, typer.Option(min=0, help="Number of invoices to generate")] = 20,
    clients: Annotated[int, typer.Option(min=1, help="Number of client subjects")] = 6,
    issuers: Annotated[int, typer.Option(min=1, help="Number of issuer subjects")] = 1,
    seed: Annotated[int | None, typer.Option(help="Seed for reproducible data")] = None,
    purge: Annotated[bool, typer.Option(help="Delete existing data first")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmations")] = False,
    force: Annotated[bool, typer.Option(help="Allow running with APP_ENV=prod")] = False,
) -> None:
    """Populate the database with generated subjects, invoices and lines."""
    _guard_production(force)
    if purge and not yes:
        typer.confirm("This will DELETE all existing invoices and subjects. Continue?", abort=True)

    async def run():
        async with get_session_factory()() as session:
            report = await load_fixtures(
                session,
                issuers=issuers,
                clients=clients,
                invoices=invoices,
                seed=seed,
                purge=purge,
            )
            await session.commit()
            return report

    report = _run(run())
    typer.secho(
        f"Database now holds {report.subjects} subjects, {report.invoices} invoices "
        f"and {report.lines} lines.",
        fg="green",
    )


@fixtures_app.command("purge")
def fixtures_purge(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    force: Annotated[bool, typer.Option(help="Allow running with APP_ENV=prod")] = False,
) -> None:
    """Delete every invoice, line and subject."""
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
