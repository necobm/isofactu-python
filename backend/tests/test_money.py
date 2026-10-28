"""Unit tests for the fixed-point arithmetic (round half-up) and the domain computations."""

from decimal import Decimal

import pytest

from app.invoicing.document_type import DocumentType
from app.invoicing.models import Invoice, InvoiceLine, Subject
from app.invoicing.money import bcadd, bcdiv, bcmul, bcsub, scale
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber


@pytest.mark.parametrize(
    ("a", "b", "places", "expected"),
    [
        ("3", "33.33", 2, "99.99"),
        ("99.99", "0.21", 2, "21.00"),  # 20.9979 -> rounded half-up
        ("1.005", "1", 2, "1.01"),  # exact half rounds away from zero
        ("1.004", "1", 2, "1.00"),
        ("2", "0.5", 2, "1.00"),
        ("-3", "1.999", 2, "-6.00"),
    ],
)
def test_bcmul_rounds_half_up(a: str, b: str, places: int, expected: str) -> None:
    assert bcmul(a, b, places) == Decimal(expected)


def test_bcdiv_and_bcadd() -> None:
    assert bcdiv("21", "100", 4) == Decimal("0.2100")
    assert bcdiv("7", "3", 4) == Decimal("2.3333")
    assert bcdiv("2", "3", 4) == Decimal("0.6667")
    assert bcadd("0.1", "0.2", 2) == Decimal("0.30")
    assert bcsub("1", "0.005", 2) == Decimal("1.00")  # 0.995 rounds half-up
    assert scale(1.1, 2) == Decimal("1.10")


def test_invoice_line_amounts() -> None:
    line = InvoiceLine(quantity=Decimal("3"), unit_price=Decimal("33.33"), tax_rate=Decimal("21"))
    assert line.subtotal == Decimal("99.99")
    assert line.tax_amount == Decimal("21.00")
    assert line.total == Decimal("120.99")


def test_invoice_retention_applies_to_the_subtotal() -> None:
    invoice = Invoice(issuer=Subject(), recipient=Subject(), retention_rate=Decimal("15"))
    invoice.add_line(
        InvoiceLine(quantity=Decimal("1"), unit_price=Decimal("99.99"), tax_rate=Decimal("21"))
    )
    invoice.add_line(
        InvoiceLine(quantity=Decimal("1"), unit_price=Decimal("0.05"), tax_rate=Decimal("0"))
    )
    assert invoice.subtotal == Decimal("100.04")
    assert invoice.tax_amount == Decimal("21.00")
    assert invoice.retention_amount == Decimal("15.01")  # 15.006 -> half-up, on the whole base
    assert invoice.total == Decimal("106.03")  # 100.04 + 21.00 - 15.01


def test_invoice_line_defaults() -> None:
    line = InvoiceLine()
    assert (line.quantity, line.unit_price, line.tax_rate) == (
        Decimal("1.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    assert line.total == Decimal("0.00")


def test_invoice_totals_and_line_management() -> None:
    issuer = Subject(full_name="Issuer", document=IdentificationDocument(DocumentType.NIF, "1"))
    recipient = Subject(full_name="Recipient")
    invoice = Invoice(issuer=issuer, recipient=recipient, invoice_number=InvoiceNumber("F", "1"))

    first = InvoiceLine(
        description="a", quantity=Decimal("2"), unit_price=Decimal("10"), tax_rate=Decimal("21")
    )
    second = InvoiceLine(
        description="b", quantity=Decimal("1"), unit_price=Decimal("5.55"), tax_rate=Decimal("10")
    )
    invoice.add_line(first).add_line(second).add_line(first)  # adding twice is a no-op

    assert invoice.lines == [first, second]
    assert first.invoice is invoice
    assert invoice.subtotal == Decimal("25.55")
    assert invoice.tax_amount == Decimal("4.76")  # 4.20 + 0.56 (0.555 rounds up)
    assert invoice.retention_rate == Decimal("0.00")
    assert invoice.retention_amount == Decimal("0.00")
    assert invoice.total == Decimal("30.31")

    invoice.remove_line(first)
    assert invoice.lines == [second]
    assert first.invoice is None
    assert invoice.total == Decimal("6.11")


def test_value_objects_string_representation() -> None:
    assert str(InvoiceNumber("F-2026", "42")) == "F-2026-42"
    assert str(InvoiceNumber(None, "42")) == "42"
    assert str(InvoiceNumber("", "42")) == "42"
    assert InvoiceNumber("F-2026", "42").is_assigned
    assert not InvoiceNumber().is_assigned and str(InvoiceNumber()) == ""
    assert not InvoiceNumber("F-2026", "").is_assigned
    assert str(Invoice(issuer=Subject(), recipient=Subject())) == "(draft)"
    assert str(IdentificationDocument(DocumentType.CIF, "B123")) == "CIF: B123"
    assert (
        str(Address("Calle 1", "28001", "Madrid", "Madrid")) == "Calle 1, 28001 Madrid, Madrid (ES)"
    )
    assert (
        str(Invoice(issuer=Subject(), recipient=Subject(), invoice_number=InvoiceNumber("A", "7")))
        == "A-7"
    )
