"""PDF export of issued invoices.

The document is rendered from the API's own view of the invoice (`InvoiceRead`), so the
PDF shows exactly the data the app shows -- the issuer and recipient copies stored on the
invoice, its lines and the amounts computed by the backend -- and rendering never touches
the database (it can run in a worker thread).

Layout (A4, Spanish labels like the rest of the app): the issuer's company name and fiscal
identity on the left; on the right, the invoice number, the largest text on the page. Then
the client, the dates and payment method, the concepts (the table header repeats when it
spans several pages), the totals and the notes. Every page has a footer with the invoice
number and "Página n de m".

Text uses the standard PDF fonts (Helvetica), which every viewer has and which cover
Spanish and the other Western European languages (Windows-1252, "€" included); characters
outside that set are drawn as a placeholder box.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.geo import service as geo
from app.invoicing.document_type import DocumentType
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.schemas import AddressSchema, IdentificationDocumentSchema, InvoiceRead

PAGE_SIZE = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_SIZE[0] - 2 * MARGIN

# Font sizes: the invoice number is the largest text of the document, the company name
# comes next; everything else is body text.
INVOICE_NUMBER_SIZE = 22
COMPANY_NAME_SIZE = 15
BODY_SIZE = 9
SMALL_SIZE = 8

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

INK = colors.HexColor("#1e293b")  # slate-800
MUTED = colors.HexColor("#64748b")  # slate-500
RULE = colors.HexColor("#e2e8f0")  # slate-200
SHADE = colors.HexColor("#f8fafc")  # slate-50
ACCENT = colors.HexColor("#4f46e5")  # indigo-600

PAYMENT_METHOD_LABELS = {
    PaymentMethod.TRANSFER: "Transferencia bancaria",
    PaymentMethod.CASH: "Efectivo",
    PaymentMethod.CARD: "Tarjeta",
    PaymentMethod.DIRECT_DEBIT: "Domiciliación bancaria",
}
DOCUMENT_TYPE_LABELS = {
    DocumentType.NIF: "NIF",
    DocumentType.CIF: "CIF",
    DocumentType.OTHER: "Id. fiscal",
}


# -- formatting (Spanish conventions, as in the frontend) ------------------------------


def format_amount(value: Decimal) -> str:
    """``Decimal("1234.5")`` -> ``"1234,50"``; ``Decimal("12345.5")`` -> ``"12.345,50"``.

    Like ``Intl.NumberFormat('es-ES')`` in the frontend, four-digit amounts are not grouped.
    """
    rounded = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"{abs(rounded):.2f}"
    if abs(rounded) >= 10000:
        text = f"{abs(rounded):,.2f}"
    text = text.replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"-{text}" if rounded < 0 else text


def format_currency(value: Decimal) -> str:
    return f"{format_amount(value)} €"


def format_rate(value: Decimal) -> str:
    """``Decimal("21.00")`` -> ``"21 %"``, ``Decimal("10.50")`` -> ``"10,5 %"``."""
    text = f"{Decimal(value).normalize():f}".replace(".", ",")
    return f"{text} %"


def format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def pdf_filename(invoice: InvoiceRead) -> str:
    """A safe download name: ``Factura-F-2026-42.pdf`` (characters that are not safe in a
    file name, such as the ``/`` of ``2026/42``, become ``-``)."""
    number = invoice.invoice_number.formatted if invoice.invoice_number else ""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", number).strip("-.")
    return f"Factura-{safe}.pdf" if safe else f"Factura-{invoice.id}.pdf"


# -- building blocks -------------------------------------------------------------------


def _style(name: str, **overrides: Any) -> ParagraphStyle:
    base = {
        "fontName": FONT,
        "fontSize": BODY_SIZE,
        "leading": BODY_SIZE * 1.35,
        "textColor": INK,
    }
    return ParagraphStyle(name, **{**base, **overrides})


STYLES = {
    "company": _style(
        "company", fontName=FONT_BOLD, fontSize=COMPANY_NAME_SIZE, leading=COMPANY_NAME_SIZE * 1.2
    ),
    "number_label": _style(
        "number_label", fontName=FONT_BOLD, fontSize=SMALL_SIZE, textColor=MUTED, alignment=TA_RIGHT
    ),
    "number": _style(
        "number",
        fontName=FONT_BOLD,
        fontSize=INVOICE_NUMBER_SIZE,
        leading=INVOICE_NUMBER_SIZE * 1.2,
        textColor=ACCENT,
        alignment=TA_RIGHT,
    ),
    "label": _style("label", fontName=FONT_BOLD, fontSize=SMALL_SIZE, textColor=MUTED),
    "party": _style("party", fontName=FONT_BOLD, fontSize=10.5, leading=14),
    "text": _style("text"),
    "muted": _style("muted", textColor=MUTED),
    "fact_label": _style("fact_label", textColor=MUTED, alignment=TA_LEFT),
    "fact_value": _style("fact_value", fontName=FONT_BOLD, alignment=TA_RIGHT),
    "th": _style("th", fontName=FONT_BOLD, fontSize=SMALL_SIZE, textColor=MUTED),
    "th_right": _style(
        "th_right", fontName=FONT_BOLD, fontSize=SMALL_SIZE, textColor=MUTED, alignment=TA_RIGHT
    ),
    "td": _style("td", fontSize=SMALL_SIZE + 0.5),
    "td_right": _style("td_right", fontSize=SMALL_SIZE + 0.5, alignment=TA_RIGHT),
    "total_label": _style("total_label", textColor=MUTED),
    "total_value": _style("total_value", alignment=TA_RIGHT),
    "grand_label": _style("grand_label", fontName=FONT_BOLD, fontSize=12, leading=16),
    "grand_value": _style(
        "grand_value", fontName=FONT_BOLD, fontSize=12, leading=16, alignment=TA_RIGHT
    ),
}


def _p(text: str, style: str) -> Paragraph:
    """A paragraph of user data: escaped (it is not markup) and keeping its line breaks."""
    return Paragraph(escape(text).replace("\n", "<br/>"), STYLES[style])


def _document(document: IdentificationDocumentSchema) -> str:
    return f"{DOCUMENT_TYPE_LABELS.get(document.type, document.type.value)}: {document.number}"


def _country_name(code: str) -> str:
    country = geo.find_country(code) if code else None
    return country.name if country else code


def _address_lines(address: AddressSchema) -> list[str]:
    """The postal address as print lines, skipping the parts that are empty."""
    locality = " ".join(part for part in (address.zip_code, address.city) if part)
    region = ", ".join(
        part for part in (address.province, _country_name(address.country_iso_code)) if part
    )
    return [line for line in (address.street, locality, region) if line]


def _identity(document: IdentificationDocumentSchema, address: AddressSchema) -> list[Flowable]:
    """Fiscal identification and address of a party, one paragraph per line."""
    lines = [_document(document)] if document.number else []
    return [_p(line, "muted") for line in [*lines, *_address_lines(address)]]


def _header(invoice: InvoiceRead) -> Table:
    """Issuer (company name and identity) on the left, invoice number on the right."""
    issuer = invoice.issuer
    number = invoice.invoice_number.formatted if invoice.invoice_number else "Sin número"
    left = [
        _p(issuer.full_name, "company"),
        Spacer(0, 2),
        *_identity(issuer.document, issuer.address),
    ]
    right = [_p("FACTURA", "number_label"), Spacer(0, 2), _p(number, "number")]
    table = Table([[left, right]], colWidths=[CONTENT_WIDTH * 0.55, CONTENT_WIDTH * 0.45])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, 0), 1, ACCENT),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ]
        )
    )
    return table


def _facts(invoice: InvoiceRead) -> list[tuple[str, str]]:
    facts = [("Fecha de emisión", format_date(invoice.issue_date))]
    if invoice.due_date:
        facts.append(("Fecha de vencimiento", format_date(invoice.due_date)))
    facts.append(("Forma de pago", PAYMENT_METHOD_LABELS[invoice.payment_method]))
    return facts


def _parties_and_facts(invoice: InvoiceRead) -> Table:
    """The client on the left; dates and payment method on the right."""
    recipient = invoice.recipient
    client = [
        _p("CLIENTE", "label"),
        Spacer(0, 3),
        _p(recipient.full_name, "party"),
        *_identity(recipient.document, recipient.address),
    ]
    facts = Table(
        [[_p(label, "fact_label"), _p(value, "fact_value")] for label, value in _facts(invoice)],
        colWidths=[CONTENT_WIDTH * 0.18, CONTENT_WIDTH * 0.22],
    )
    facts.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    gap = CONTENT_WIDTH * 0.06
    table = Table(
        [[client, "", facts]], colWidths=[CONTENT_WIDTH * 0.54, gap, CONTENT_WIDTH * 0.40]
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, 0), SHADE),
                ("BOX", (0, 0), (0, 0), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
                ("TOPPADDING", (0, 0), (0, 0), 7),
                ("BOTTOMPADDING", (0, 0), (0, 0), 8),
                ("LEFTPADDING", (1, 0), (-1, 0), 0),
                ("RIGHTPADDING", (1, 0), (-1, 0), 0),
                ("TOPPADDING", (2, 0), (2, 0), 4),
            ]
        )
    )
    return table


# Concepts table: (header, relative width, right-aligned)
LINE_COLUMNS = (
    ("Concepto", 0.32, False),
    ("Cant.", 0.08, True),
    ("Precio unit.", 0.12, True),
    ("IVA", 0.08, True),
    ("Base", 0.13, True),
    ("Cuota IVA", 0.13, True),
    ("Total", 0.14, True),
)


def _lines(invoice: InvoiceRead) -> Table:
    header = [_p(title, "th_right" if right else "th") for title, _, right in LINE_COLUMNS]
    rows: list[list[Any]] = [header]
    for line in invoice.lines:
        rows.append(
            [
                _p(line.description, "td"),
                _p(format_amount(line.quantity), "td_right"),
                _p(format_currency(line.unit_price), "td_right"),
                _p(format_rate(line.tax_rate), "td_right"),
                _p(format_currency(line.subtotal), "td_right"),
                _p(format_currency(line.tax_amount), "td_right"),
                _p(format_currency(line.total), "td_right"),
            ]
        )
    if not invoice.lines:
        rows.append([_p("Sin conceptos", "muted"), "", "", "", "", "", ""])

    table = Table(
        rows,
        colWidths=[CONTENT_WIDTH * width for _, width, _ in LINE_COLUMNS],
        repeatRows=1,  # the header is repeated on every page the table spans
    )
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, MUTED),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
    ]
    if not invoice.lines:
        style.append(("SPAN", (0, 1), (-1, 1)))
    table.setStyle(TableStyle(style))
    return table


def _totals(invoice: InvoiceRead) -> Table:
    rows = [
        ("Base imponible", format_currency(invoice.subtotal)),
        ("IVA", format_currency(invoice.tax_amount)),
    ]
    if invoice.retention_rate > 0:
        rows.append(
            (
                f"Retención IRPF ({format_rate(invoice.retention_rate)})",
                f"-{format_currency(invoice.retention_amount)}",
            )
        )
    data: list[list[Any]] = [
        [_p(label, "total_label"), _p(value, "total_value")] for label, value in rows
    ]
    data.append([_p("TOTAL", "grand_label"), _p(format_currency(invoice.total), "grand_value")])

    width = CONTENT_WIDTH * 0.45
    table = Table(data, colWidths=[width * 0.55, width * 0.45], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEABOVE", (0, -1), (-1, -1), 1, INK),
                ("TOPPADDING", (0, -1), (-1, -1), 6),
                ("BACKGROUND", (0, -1), (-1, -1), SHADE),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ]
        )
    )
    return table


def _notes(invoice: InvoiceRead) -> list[Flowable]:
    if not invoice.notes.strip():
        return []
    return [Spacer(0, 14), _p("NOTAS", "label"), Spacer(0, 3), _p(invoice.notes, "text")]


def _story(invoice: InvoiceRead) -> Iterable[Flowable]:
    yield _header(invoice)
    yield Spacer(0, 14)
    yield _parties_and_facts(invoice)
    yield Spacer(0, 18)
    yield _lines(invoice)
    yield Spacer(0, 10)
    yield KeepTogether([_totals(invoice)])
    yield from _notes(invoice)


# -- page furniture --------------------------------------------------------------------


class _NumberedCanvas(Canvas):
    """Draws the footer ("Factura F-2026-42 · Página 1 de 2") on every page once the
    total number of pages is known (pages are buffered until `save`)."""

    def __init__(self, *args: Any, footer: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._footer = footer
        self._saved_pages: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802 - reportlab API
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_pages)
        for page in self._saved_pages:
            self.__dict__.update(page)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        width, _ = self._pagesize
        y = MARGIN / 2
        self.saveState()
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(MARGIN, y + 10, width - MARGIN, y + 10)
        self.setFont(FONT, SMALL_SIZE)
        self.setFillColor(MUTED)
        self.drawString(MARGIN, y, self._footer)
        self.drawRightString(width - MARGIN, y, f"Página {self._pageNumber} de {total}")
        self.restoreState()


def render_invoice_pdf(invoice: InvoiceRead) -> bytes:
    """The invoice as a PDF document (A4)."""
    number = invoice.invoice_number.formatted if invoice.invoice_number else ""
    title = f"Factura {number}".strip()
    footer = " · ".join(part for part in (title, invoice.issuer.full_name) if part)

    buffer = io.BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=title,
        author=invoice.issuer.full_name,
        subject=f"{title} - {invoice.recipient.full_name}",
        creator="Isofactu",
        lang="es-ES",
    )
    # A frame without inner padding, so that the content spans exactly CONTENT_WIDTH
    frame = Frame(
        MARGIN,
        MARGIN,
        CONTENT_WIDTH,
        PAGE_SIZE[1] - 2 * MARGIN,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    document.addPageTemplates([PageTemplate(id="invoice", frames=[frame])])
    document.build(list(_story(invoice)), canvasmaker=partial(_NumberedCanvas, footer=footer))
    return buffer.getvalue()
