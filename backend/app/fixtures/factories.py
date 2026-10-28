"""factory_boy factories for the Invoicing module.

Usage::

    with bind_session(session):            # any (async) SQLAlchemy session
        invoice = InvoiceFactory()         # built, added to the session, not flushed yet
        await session.flush()

    InvoiceFactory.build()                 # transient object, no session needed
    SubjectFactory(document__type=DocumentType.CIF, full_name="ACME SL")

Factories only call ``session.add`` (no implicit flush/commit) so they work identically with
``AsyncSession``; flushing and committing stay explicit and under the caller's control.
"""

from __future__ import annotations

import datetime as dt
import random
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

import factory
from factory import fuzzy
from factory.alchemy import SQLAlchemyModelFactory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, InvoiceLine, Subject
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber

LOCALE = "es_ES"
DRAFT_RATIO = 0.2  # share of generated invoices left as drafts
SPANISH_VAT_RATES = [Decimal("21.00"), Decimal("10.00"), Decimal("4.00"), Decimal("0.00")]
# IRPF withholding: most invoices carry none, some the usual 15 % (or 7 % for new freelancers).
RETENTION_RATES = [Decimal("0.00")] * 6 + [Decimal("15.00"), Decimal("7.00")]
NOTES = [
    "",
    "",
    "",
    "Pago a 30 días mediante transferencia bancaria.",
    "Gracias por confiar en nosotros.",
    "Operación sujeta a IVA. Retención de IRPF aplicada según normativa vigente.",
]
LINE_CONCEPTS = [
    "Desarrollo web",
    "Consultoría técnica",
    "Mantenimiento mensual",
    "Soporte técnico",
    "Diseño gráfico",
    "Formación",
    "Hosting anual",
    "Auditoría de seguridad",
    "Gestión de redes sociales",
    "Licencia de software",
]

_session: ContextVar[AsyncSession | Session | None] = ContextVar("fixture_session", default=None)


@contextmanager
def bind_session(session: AsyncSession | Session) -> Iterator[None]:
    """Make `session` the target of ``Factory()`` / ``Factory.create()`` inside the block."""
    token = _session.set(session)
    try:
        yield
    finally:
        _session.reset(token)


def _current_session() -> AsyncSession | Session:
    session = _session.get()
    if session is None:
        raise RuntimeError(
            "No session bound: wrap factory calls in `with bind_session(session):` "
            "or use `Factory.build()` for transient objects."
        )
    return session


def reseed(seed: int) -> None:
    """Make factories + Faker deterministic (same seed -> same data)."""
    factory.random.reseed_random(seed)
    random.seed(seed)  # some Faker providers still use the global `random` module


# -- Spanish tax identifiers ------------------------------------------------------------
# Faker's es_ES `nif()` / `cif()` draw from the *unseeded* global random module, which
# breaks reproducibility, so the (short) algorithms are implemented here on the seeded RNG.

NIF_CONTROL = "TRWAGMYFPDXBNJZSQVHLCKE"
CIF_LETTERS = "ABCDEFGHJNPQRSUVW"
CIF_LETTER_CONTROL = "JABCDEFGHI"
CIF_CONTROL_IS_LETTER = set("KPQSNW")
CIF_CONTROL_IS_DIGIT = set("ABEH")


def spanish_nif(rng: random.Random) -> str:
    body = rng.randrange(0, 100_000_000)
    return f"{body:08d}{NIF_CONTROL[body % 23]}"


def spanish_cif(rng: random.Random) -> str:
    letter = rng.choice(CIF_LETTERS)
    digits = [rng.randrange(10) for _ in range(7)]
    even_sum = sum(digits[1::2])
    odd_sum = sum(sum(divmod(d * 2, 10)) for d in digits[0::2])
    control = (10 - (even_sum + odd_sum) % 10) % 10
    if letter in CIF_CONTROL_IS_LETTER:
        control_char = CIF_LETTER_CONTROL[control]
    elif letter in CIF_CONTROL_IS_DIGIT:
        control_char = str(control)
    else:
        control_char = rng.choice([str(control), CIF_LETTER_CONTROL[control]])
    return f"{letter}{''.join(map(str, digits))}{control_char}"


class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_factory = _current_session
        sqlalchemy_session_persistence = None  # add() only; flush/commit are explicit


# -- value objects --------------------------------------------------------------------


class AddressFactory(factory.Factory):
    class Meta:
        model = Address

    street = factory.Faker("street_address", locale=LOCALE)
    zip_code = factory.Faker("postcode", locale=LOCALE)
    city = factory.Faker("city", locale=LOCALE)
    province = factory.Faker("administrative_unit", locale=LOCALE)
    country_iso_code = "ES"


class IdentificationDocumentFactory(factory.Factory):
    class Meta:
        model = IdentificationDocument

    type = fuzzy.FuzzyChoice([DocumentType.NIF, DocumentType.CIF])

    @factory.lazy_attribute
    def number(self) -> str:
        rng = factory.random.randgen
        match self.type:
            case DocumentType.CIF:
                return spanish_cif(rng)
            case DocumentType.NIF:
                return spanish_nif(rng)
            case _:
                return "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=9))


class InvoiceNumberFactory(factory.Factory):
    class Meta:
        model = InvoiceNumber

    serial = factory.LazyFunction(lambda: f"F-{dt.date.today().year}")
    number = factory.Sequence(lambda n: str(n + 1))


# -- entities -------------------------------------------------------------------------


class SubjectFactory(BaseFactory):
    class Meta:
        model = Subject

    document = factory.SubFactory(IdentificationDocumentFactory)
    address = factory.SubFactory(AddressFactory)

    @factory.lazy_attribute
    def full_name(self) -> str:
        faker = factory.Faker._get_faker(locale=LOCALE)
        return faker.company() if self.document.type == DocumentType.CIF else faker.name()


class InvoiceLineFactory(BaseFactory):
    class Meta:
        model = InvoiceLine

    invoice = factory.SubFactory("app.fixtures.factories.InvoiceFactory", lines=[])
    description = fuzzy.FuzzyChoice(LINE_CONCEPTS)
    quantity = fuzzy.FuzzyDecimal(1, 40, precision=0)
    unit_price = fuzzy.FuzzyDecimal(10, 500, precision=2)
    tax_rate = fuzzy.FuzzyChoice(SPANISH_VAT_RATES)


class InvoiceFactory(BaseFactory):
    """An invoice with an issuer, a recipient and (by default) 1-4 lines.

    ``InvoiceFactory(lines=3)`` creates exactly three; ``InvoiceFactory(lines=[line, ...])``
    uses the given ones instead. Generated lines always carry a concept and a positive
    amount, as the API requires.
    Most invoices are ISSUED; about one in five is left as a DRAFT, which carries no
    invoice number (``InvoiceFactory(state=InvoiceState.ISSUED)`` pins the state).
    """

    class Meta:
        model = Invoice

    class Params:
        is_draft = factory.LazyAttribute(lambda o: o.state is InvoiceState.DRAFT)

    issuer = factory.SubFactory(SubjectFactory)
    recipient = factory.SubFactory(SubjectFactory)
    issue_date = fuzzy.FuzzyDate(dt.date.today() - dt.timedelta(days=365), dt.date.today())
    state = factory.LazyFunction(
        lambda: (
            InvoiceState.DRAFT
            if factory.random.randgen.random() < DRAFT_RATIO
            else InvoiceState.ISSUED
        )
    )
    invoice_number = factory.Maybe(
        "is_draft",
        yes_declaration=InvoiceNumber(),
        no_declaration=factory.SubFactory(InvoiceNumberFactory),
    )
    notes = fuzzy.FuzzyChoice(NOTES)
    due_date = factory.LazyAttribute(lambda o: o.issue_date + dt.timedelta(days=30))
    payment_method = fuzzy.FuzzyChoice(list(PaymentMethod))
    retention_rate = fuzzy.FuzzyChoice(RETENTION_RATES)

    @factory.post_generation
    def lines(self: Invoice, create: bool, extracted: int | list[InvoiceLine] | None, **kwargs):
        if isinstance(extracted, list):
            for line in extracted:
                self.add_line(line)
            return
        count = extracted if isinstance(extracted, int) else fuzzy.FuzzyInteger(1, 4).fuzz()
        strategy = InvoiceLineFactory.create if create else InvoiceLineFactory.build
        for _ in range(count):
            strategy(invoice=self, **kwargs)
