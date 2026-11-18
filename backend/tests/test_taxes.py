"""Tax estimates of a quarter (`GET /api/taxes`): IVA and IRPF."""

import random
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.fixtures import InvoiceFactory, ReceivedInvoiceFactory, SubjectFactory
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, InvoiceLine
from app.taxes.calculations import irpf_estimate, irpf_from_income, vat_estimate
from app.taxes.quarters import Quarter

D = Decimal
Q3 = {"year": 2026, "quarter": 3}  # 1 July - 30 September 2026


def line(quantity: str, unit_price: str, tax_rate: str = "21") -> InvoiceLine:
    return InvoiceLine(
        description="Concepto", quantity=D(quantity), unit_price=D(unit_price), tax_rate=D(tax_rate)
    )


@pytest.fixture
def issued(
    invoice_factory: type[InvoiceFactory], subject_factory: type[SubjectFactory], tenant: User
):
    """A final issued invoice of `tenant` to a client in `country` (Spain by default)."""

    def make(day: date, *lines: InvoiceLine, country: str = "ES", **fields) -> Invoice:
        fields.setdefault("state", InvoiceState.ISSUED)
        fields.setdefault("retention_rate", D(0))
        recipient = subject_factory(owner=tenant, address__country_iso_code=country)
        return invoice_factory(
            owner=tenant, recipient=recipient, issue_date=day, lines=list(lines), **fields
        )

    return make


@pytest.fixture
def received(received_invoice_factory: type[ReceivedInvoiceFactory], tenant: User):
    def make(day: date, *lines: InvoiceLine, **fields) -> Invoice:
        fields.setdefault("retention_rate", D(0))
        return received_invoice_factory(owner=tenant, issue_date=day, lines=list(lines), **fields)

    return make


async def _taxes(client: AsyncClient, **params) -> dict:
    response = await client.get("/api/taxes", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_example_of_the_specification(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    # A Spanish client: 1129,81 € + 21 % VAT
    issued(date(2026, 7, 6), line("1", "1129.81"))
    # A Spanish client that withholds 15 % IRPF (VAT-exempt service): 527,20 €
    issued(date(2026, 8, 3), line("1", "527.20", "0"), retention_rate=D(15))
    # A client abroad, no Spanish VAT and no withholding: 14.751,65 €
    issued(date(2026, 9, 30), line("1", "14751.65", "0"), country="DE")
    # An expense: 159,24 € + 21 % VAT
    received(date(2026, 7, 1), line("1", "159.24"))
    await session.flush()

    body = await _taxes(tenant_client, **Q3)

    assert (body["year"], body["quarter"]) == (2026, 3)
    assert (body["periodStart"], body["periodEnd"]) == ("2026-07-01", "2026-09-30")
    assert body["vat"] == {
        "collected": 237.26,
        "paid": 33.44,
        "estimated": 203.82,
        "issuedCount": 3,
        "receivedCount": 1,
    }
    assert body["irpf"] == {
        "rate": 20.0,
        "foreignIncome": 14751.65,
        "fromIncome": 2950.33,
        "withheld": 79.08,
        "estimated": 2871.25,
        "foreignInvoiceCount": 1,
    }


async def test_only_the_final_invoices_of_the_quarter_count(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    issued(date(2026, 7, 1), line("1", "100"))  # first day
    issued(date(2026, 9, 30), line("1", "100"), country="FR")  # last day
    received(date(2026, 9, 30), line("1", "10"))
    # Not counted: drafts, and the days just before and after the quarter
    issued(date(2026, 8, 1), line("1", "5000"), state=InvoiceState.DRAFT)
    issued(date(2026, 8, 1), line("1", "5000"), country="US", state=InvoiceState.DRAFT)
    issued(date(2026, 6, 30), line("1", "1000"), country="FR")
    issued(date(2026, 10, 1), line("1", "1000"), country="FR")
    received(date(2026, 6, 30), line("1", "1000"))
    received(date(2026, 10, 1), line("1", "1000"))
    await session.flush()

    body = await _taxes(tenant_client, **Q3)

    assert body["vat"] == {
        "collected": 42.0,
        "paid": 2.1,
        "estimated": 39.9,
        "issuedCount": 2,
        "receivedCount": 1,
    }
    assert (body["irpf"]["foreignIncome"], body["irpf"]["foreignInvoiceCount"]) == (100.0, 1)
    assert body["irpf"]["fromIncome"] == 20.0


async def test_only_issued_invoices_to_clients_abroad_are_irpf_income(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    day = date(2026, 8, 10)
    issued(day, line("1", "1000"), country="ES")  # Spain (Canary Islands included)
    issued(day, line("1", "300", "0"), country="PT")
    issued(day, line("2", "100", "0"), country="us")  # legacy lower-case code
    # Expenses never count, wherever the supplier is (the recipient is the account)
    received(day, line("1", "999", "0"))
    await session.flush()

    irpf = (await _taxes(tenant_client, **Q3))["irpf"]

    assert (irpf["foreignIncome"], irpf["foreignInvoiceCount"]) == (500.0, 2)
    assert irpf["fromIncome"] == 100.0


async def test_irpf_withheld_comes_from_issued_invoices_only(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    day = date(2026, 7, 15)
    issued(day, line("1", "1000"), retention_rate=D(15))  # 150 withheld
    issued(day, line("1", "99.99"), retention_rate=D(7))  # 6.9993 -> 7.00
    # The IRPF the tenant withholds from a supplier is not withheld from the tenant
    received(day, line("1", "500"), retention_rate=D(15))
    await session.flush()

    irpf = (await _taxes(tenant_client, **Q3))["irpf"]

    assert irpf["withheld"] == 157.0
    # Nothing invoiced abroad: clients withheld more than is due, nothing to pay
    assert (irpf["fromIncome"], irpf["estimated"]) == (0.0, -157.0)


async def test_more_vat_paid_than_collected(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    issued(date(2026, 7, 2), line("1", "100", "10"))
    received(date(2026, 7, 3), line("1", "1000"))
    await session.flush()

    vat = (await _taxes(tenant_client, **Q3))["vat"]

    assert (vat["collected"], vat["paid"], vat["estimated"]) == (10.0, 210.0, -200.0)


async def test_amounts_match_the_invoices_to_the_cent(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    rng = random.Random(7)
    invoices = []
    for _ in range(25):
        lines = [
            line(
                str(rng.choice([1, 2, 3, "1.5", "0.33"])),
                f"{rng.uniform(-20, 900):.2f}",
                str(rng.choice([0, 4, 10, 21])),
            )
            for _ in range(rng.randint(1, 4))
        ]
        lines.append(line("1", "1000"))  # keep every invoice positive
        day = date(2026, rng.randint(7, 9), rng.randint(1, 28))
        retention = D(rng.choice([0, 7, 15]))
        if rng.random() < 0.5:
            country = rng.choice(["ES", "FR", "GB"])
            invoices.append(issued(day, *lines, country=country, retention_rate=retention))
        else:
            invoices.append(received(day, *lines, retention_rate=retention))
    await session.flush()

    body = await _taxes(tenant_client, **Q3)

    def is_issued(i: Invoice) -> bool:
        return i.kind.value == "ISSUED"

    collected = sum(i.tax_amount for i in invoices if is_issued(i))
    paid = sum(i.tax_amount for i in invoices if not is_issued(i))
    abroad = sum(
        i.subtotal
        for i in invoices
        if is_issued(i) and i.recipient.address.country_iso_code != "ES"
    )
    withheld = sum(i.retention_amount for i in invoices if is_issued(i))
    assert D(str(body["vat"]["collected"])) == collected
    assert D(str(body["vat"]["paid"])) == paid
    assert D(str(body["irpf"]["foreignIncome"])) == abroad
    assert D(str(body["irpf"]["withheld"])) == withheld
    assert D(str(body["irpf"]["estimated"])) == irpf_from_income(abroad) - withheld


async def test_the_current_quarter_by_default(tenant_client: AsyncClient) -> None:
    today = date.today()
    current = Quarter.of(today)

    body = await _taxes(tenant_client)

    assert (body["year"], body["quarter"]) == (today.year, current.number)
    assert body["periodStart"] <= today.isoformat() <= body["periodEnd"]
    assert body["vat"]["estimated"] == body["irpf"]["estimated"] == 0.0
    # Another quarter of this year
    other = 1 if current.number != 1 else 2
    assert (await _taxes(tenant_client, quarter=other))["quarter"] == other


async def test_invalid_quarters(tenant_client: AsyncClient) -> None:
    for params in ({"quarter": 0}, {"quarter": 5}, {"year": 1999}, {"quarter": "Q1"}):
        response = await tenant_client.get("/api/taxes", params=params)
        assert response.status_code == 422, params


async def test_tenants_only_see_their_own_taxes(
    tenant_client: AsyncClient,
    session: AsyncSession,
    issued,
    invoice_factory: type[InvoiceFactory],
    subject_factory: type[SubjectFactory],
    other_tenant: User,
) -> None:
    issued(date(2026, 8, 1), line("1", "100"))
    theirs = subject_factory(owner=other_tenant, address__country_iso_code="FR")
    invoice_factory(
        owner=other_tenant,
        recipient=theirs,
        issue_date=date(2026, 8, 1),
        state=InvoiceState.ISSUED,
        retention_rate=D(15),
        lines=[line("1", "5000")],
    )
    await session.flush()

    body = await _taxes(tenant_client, **Q3)

    assert (body["vat"]["collected"], body["vat"]["issuedCount"]) == (21.0, 1)
    assert (body["irpf"]["foreignIncome"], body["irpf"]["withheld"]) == (0.0, 0.0)


async def test_only_tenants_have_taxes(
    client: AsyncClient, super_admin_client: AsyncClient
) -> None:
    assert (await client.get("/api/taxes")).status_code == 401
    assert (await super_admin_client.get("/api/taxes")).status_code == 403


# -- quarters and formulas ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "number", "start", "end"),
    [
        (date(2026, 1, 1), 1, date(2026, 1, 1), date(2026, 3, 31)),
        (date(2026, 3, 31), 1, date(2026, 1, 1), date(2026, 3, 31)),
        (date(2026, 4, 1), 2, date(2026, 4, 1), date(2026, 6, 30)),
        (date(2026, 8, 15), 3, date(2026, 7, 1), date(2026, 9, 30)),
        (date(2026, 12, 31), 4, date(2026, 10, 1), date(2026, 12, 31)),
        (date(2028, 2, 29), 1, date(2028, 1, 1), date(2028, 3, 31)),
    ],
)
def test_quarters(day: date, number: int, start: date, end: date) -> None:
    quarter = Quarter.of(day)
    assert (quarter.year, quarter.number, quarter.start, quarter.end) == (
        day.year,
        number,
        start,
        end,
    )


def test_a_quarter_is_numbered_1_to_4() -> None:
    with pytest.raises(ValueError):
        Quarter(2026, 5)


def test_formulas() -> None:
    assert vat_estimate(D("237.26"), D("33.44")) == D("203.82")
    assert irpf_from_income(D("14751.65")) == D("2950.33")
    assert irpf_from_income(D("0.03")) == D("0.01")  # 0.006: half-up to cents
    assert irpf_from_income(D("0.02")) == D("0.00")  # 0.004
    assert irpf_estimate(D("2950.33"), D("79.08")) == D("2871.25")
