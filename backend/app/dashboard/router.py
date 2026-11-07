"""`/api/dashboard`: the figures of the logged-in tenant's activity."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.accounts.deps import CurrentTenant, SessionDep
from app.dashboard.repository import DashboardRepository
from app.dashboard.schemas import (
    BookTotals,
    DashboardRead,
    MonthlyBalance,
    PendingCollection,
)
from app.invoicing.invoice_kind import InvoiceKind

MAX_MONTHS = 240  # 20 years: bounds the monthly series

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _months(start: date, end: date) -> list[str]:
    year, month = start.year, start.month
    months = []
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["query", "from"], "msg": message, "type": "value_error"}],
    )


@dashboard_router.get(
    "",
    response_model=DashboardRead,
    summary="Dashboard figures",
    description=(
        "Income (issued invoices) and expenses (received invoices) of the period "
        "`[from, to]` -- both inclusive; `from` defaults to the date of the oldest invoice "
        "and `to` to today -- with their month-by-month taxable bases, plus the issued "
        "invoices still pending collection (whatever their date). Drafts do not count."
    ),
)
async def get_dashboard(
    tenant: CurrentTenant,
    session: SessionDep,
    date_from: Annotated[
        date | None, Query(alias="from", description="First day of the period")
    ] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Last day of the period")] = None,
) -> DashboardRead:
    repo = DashboardRepository(session, tenant.id)
    today = date.today()
    end = date_to or today
    start = date_from or await repo.first_issue_date() or end
    if start > end:
        raise _invalid("`from` cannot be later than `to`")
    months = _months(start, end)
    if len(months) > MAX_MONTHS:
        raise _invalid(f"The period cannot span more than {MAX_MONTHS} months")

    income = await repo.totals(InvoiceKind.ISSUED, start, end)
    expenses = await repo.totals(InvoiceKind.RECEIVED, start, end)
    bases = await repo.monthly_bases(start, end)
    pending = await repo.pending_collection(today)
    return DashboardRead(
        period_start=start,
        period_end=end,
        income=BookTotals.model_validate(income, from_attributes=True),
        expenses=BookTotals.model_validate(expenses, from_attributes=True),
        pending_collection=PendingCollection.model_validate(pending, from_attributes=True),
        monthly=[
            MonthlyBalance(
                month=month,
                income=bases.get((month, InvoiceKind.ISSUED), 0),
                expenses=bases.get((month, InvoiceKind.RECEIVED), 0),
            )
            for month in months
        ],
    )
