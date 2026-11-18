"""`/api/taxes`: the tax estimates of the logged-in tenant's quarter."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.accounts.deps import CurrentTenant, SessionDep
from app.taxes.calculations import (
    IRPF_ADVANCE_RATE,
    irpf_estimate,
    irpf_from_income,
    vat_estimate,
)
from app.taxes.quarters import Quarter
from app.taxes.repository import TaxRepository
from app.taxes.schemas import IrpfSummary, TaxSummaryRead, VatSummary

taxes_router = APIRouter(prefix="/taxes", tags=["Taxes"])


@taxes_router.get(
    "",
    response_model=TaxSummaryRead,
    summary="Tax estimates of a quarter",
    description=(
        "IVA and IRPF estimated from the final invoices (drafts do not count) issued in a "
        "calendar quarter: the current one unless `year` / `quarter` say otherwise.\n\n"
        "- **IVA**: VAT of the issued invoices (`collected`) minus VAT of the received ones "
        "(`paid`).\n"
        "- **IRPF**: 20 % of the taxable base invoiced to clients outside Spain, who do not "
        "withhold IRPF (`fromIncome`), minus the IRPF clients withheld on the quarter's "
        "issued invoices (`withheld`).\n\n"
        "Estimates to plan ahead, not tax returns."
    ),
)
async def get_taxes(
    tenant: CurrentTenant,
    session: SessionDep,
    year: Annotated[int | None, Query(ge=2000, le=2100, description="Default: this year")] = None,
    quarter: Annotated[
        int | None, Query(ge=1, le=4, description="1 to 4. Default: the current quarter")
    ] = None,
) -> TaxSummaryRead:
    current = Quarter.of(date.today())
    period = Quarter(year or current.year, quarter or current.number)
    figures = await TaxRepository(session, tenant.id).figures(period.start, period.end)

    from_income = irpf_from_income(figures.foreign_income)
    return TaxSummaryRead(
        year=period.year,
        quarter=period.number,
        period_start=period.start,
        period_end=period.end,
        vat=VatSummary(
            collected=figures.vat_collected,
            paid=figures.vat_paid,
            estimated=vat_estimate(figures.vat_collected, figures.vat_paid),
            issued_count=figures.issued_count,
            received_count=figures.received_count,
        ),
        irpf=IrpfSummary(
            rate=IRPF_ADVANCE_RATE,
            foreign_income=figures.foreign_income,
            from_income=from_income,
            withheld=figures.irpf_withheld,
            estimated=irpf_estimate(from_income, figures.irpf_withheld),
            foreign_invoice_count=figures.foreign_count,
        ),
    )
