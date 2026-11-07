"""factory_boy factories for the Invoicing module.

Usage::

    with bind_session(session):            # any (async) SQLAlchemy session
        invoice = InvoiceFactory()         # built, added to the session, not flushed yet
        await session.flush()

    InvoiceFactory.build()                 # transient object, no session needed
    SubjectFactory(document__type=DocumentType.CIF, full_name="ACME SL")
    InvoiceFactory(owner=tenant)           # the invoice and its parties belong to `tenant`

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

from app.accounts.account_status import AccountStatus
from app.accounts.models import User
from app.accounts.role import Role
from app.clients.models import Client
from app.geo import service as geo
from app.invoicing import spanish_ids
from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Serial, Subject
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber, Issuer

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

# What a freelancer typically pays suppliers for (concepts of received invoices).
EXPENSE_CONCEPTS = [
    "Alquiler de oficina",
    "Suministro eléctrico",
    "Conexión a internet",
    "Telefonía móvil",
    "Material de oficina",
    "Licencia de software",
    "Asesoría fiscal y contable",
    "Equipo informático",
    "Hosting y dominio",
    "Seguro de responsabilidad civil",
]
# How suppliers start their invoice numbers (the rest is generated).
SUPPLIER_SERIES = ["", "A", "FV-", "2026/", "F"]

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
# breaks reproducibility, so the (short) algorithms are run here on the seeded RNG.


def spanish_nif(rng: random.Random) -> str:
    body = rng.randrange(0, 100_000_000)
    return f"{body:08d}{spanish_ids.nif_control(body)}"


def spanish_cif(rng: random.Random) -> str:
    letter = rng.choice(spanish_ids.CIF_LETTERS)
    digits = "".join(str(rng.randrange(10)) for _ in range(7))
    control = spanish_ids.cif_control(digits)
    if letter in spanish_ids.CIF_CONTROL_IS_LETTER:
        control_char = spanish_ids.CIF_LETTER_CONTROL[control]
    elif letter in spanish_ids.CIF_CONTROL_IS_DIGIT:
        control_char = str(control)
    else:
        control_char = rng.choice([str(control), spanish_ids.CIF_LETTER_CONTROL[control]])
    return f"{letter}{digits}{control_char}"


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
    # A real province name, as the client forms require
    province = fuzzy.FuzzyChoice([p.name for p in geo.provinces("ES")])
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
    """A number in the default ``F-<year>-`` series (sequence shared by every factory call;
    the fixtures loader renumbers per serial)."""

    class Meta:
        model = InvoiceNumber

    prefix = factory.LazyFunction(lambda: f"F-{dt.date.today().year}-")
    number = factory.Sequence(lambda n: str(n + 1))
    suffix = ""


class SupplierNumberFactory(factory.Factory):
    """The number printed on a supplier's invoice: whole, in any style ("FV-0042", "2026/0042")."""

    class Meta:
        model = InvoiceNumber

    prefix = ""
    number = factory.LazyFunction(
        lambda: (
            f"{factory.random.randgen.choice(SUPPLIER_SERIES)}"
            f"{factory.random.randgen.randrange(1, 10_000):04d}"
        )
    )
    suffix = ""


class IssuerFactory(factory.Factory):
    """The issuer snapshot of an invoice: a company with a CIF and a Spanish address."""

    class Meta:
        model = Issuer

    class Params:
        document = factory.SubFactory(IdentificationDocumentFactory, type=DocumentType.CIF)
        address = factory.SubFactory(AddressFactory)

    full_name = factory.Faker("company", locale=LOCALE)
    document_type = factory.LazyAttribute(lambda o: o.document.type)
    document_number = factory.LazyAttribute(lambda o: o.document.number)
    street = factory.LazyAttribute(lambda o: o.address.street)
    zip_code = factory.LazyAttribute(lambda o: o.address.zip_code)
    city = factory.LazyAttribute(lambda o: o.address.city)
    province = factory.LazyAttribute(lambda o: o.address.province)
    country_iso_code = factory.LazyAttribute(lambda o: o.address.country_iso_code)


# -- entities -------------------------------------------------------------------------


class UserFactory(BaseFactory):
    """An active ADMIN (tenant) without a password; pass ``password_hash`` to allow
    logging in (see ``hash_password``)."""

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n + 1}@example.com")
    name = factory.Faker("name", locale=LOCALE)
    role = Role.ADMIN
    status = AccountStatus.ACTIVE


class FiscalDataFactory(BaseFactory):
    """The fiscal data (issuer identity) of a tenant: a company with a CIF."""

    class Meta:
        model = FiscalData

    owner = factory.SubFactory(UserFactory)
    company_name = factory.Faker("company", locale=LOCALE)
    document = factory.SubFactory(IdentificationDocumentFactory, type=DocumentType.CIF)
    address = factory.SubFactory(AddressFactory)


class SerialFactory(BaseFactory):
    """A numbering series ``F-<year>-`` without time limits."""

    class Meta:
        model = Serial

    owner = factory.SubFactory(UserFactory)
    prefix = factory.LazyFunction(lambda: f"F-{dt.date.today().year}-")
    suffix = ""
    initial_number = 1


class ClientFactory(BaseFactory):
    """An entry of the tenant's client directory."""

    class Meta:
        model = Client

    owner = factory.SubFactory(UserFactory)
    document = factory.SubFactory(IdentificationDocumentFactory)
    address = factory.SubFactory(AddressFactory)

    @factory.lazy_attribute
    def full_name(self) -> str:
        faker = factory.Faker._get_faker(locale=LOCALE)
        return faker.company() if self.document.type == DocumentType.CIF else faker.name()


class SubjectFactory(BaseFactory):
    """An invoice's own copy of its recipient; ``SubjectFactory.copy_of(client)`` makes one
    from a client, as the API does."""

    class Meta:
        model = Subject

    @classmethod
    def copy_of(cls, client: Client) -> Subject:
        return cls(
            owner=client.owner,
            full_name=client.full_name,
            document=client.document,
            address=client.address,
        )

    @classmethod
    def copy_of_account(cls, data: FiscalData) -> Subject:
        """The recipient of a received invoice: a copy of the tenant's fiscal data."""
        return cls(
            owner=data.owner,
            full_name=data.company_name,
            document=data.document,
            address=data.address,
        )

    owner = factory.SubFactory(UserFactory)
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
    """An invoice with a generated issuer snapshot, a recipient and (by default) 1-4 lines.

    ``InvoiceFactory(lines=3)`` creates exactly three; ``InvoiceFactory(lines=[line, ...])``
    uses the given ones instead. Generated lines always carry a concept and a positive
    amount, as the API requires.
    Most invoices are ISSUED; about one in five is left as a DRAFT, which carries no
    invoice number (``InvoiceFactory(state=InvoiceState.ISSUED)`` pins the state).
    The invoice and its generated recipient share the same ``owner`` (tenant); pass
    ``owner=user`` to pin it (an explicit ``recipient`` keeps its own owner). The issuer is
    a value object: pass ``issuer=fiscal_data.as_issuer()`` to stamp a tenant's real one.
    """

    class Meta:
        model = Invoice

    class Params:
        is_draft = factory.LazyAttribute(lambda o: o.state is InvoiceState.DRAFT)

    owner = factory.SubFactory(UserFactory)
    issuer = factory.SubFactory(IssuerFactory)
    recipient = factory.SubFactory(SubjectFactory, owner=factory.SelfAttribute("..owner"))
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
        _generate_lines(self, create, extracted, **kwargs)


def _generate_lines(
    invoice: Invoice, create: bool, extracted: int | list[InvoiceLine] | None, **kwargs
) -> None:
    """``lines=[...]`` attaches the given lines, ``lines=n`` generates n, nothing 1-4."""
    if isinstance(extracted, list):
        for line in extracted:
            invoice.add_line(line)
        return
    count = extracted if isinstance(extracted, int) else fuzzy.FuzzyInteger(1, 4).fuzz()
    strategy = InvoiceLineFactory.create if create else InvoiceLineFactory.build
    for _ in range(count):
        strategy(invoice=invoice, **kwargs)


class ReceivedInvoiceFactory(InvoiceFactory):
    """A supplier's invoice (an expense): a generated supplier as issuer, the supplier's own
    number, no serial, and 1-4 lines with typical expense concepts. Always ISSUED: received
    invoices have no drafts.

    The recipient is a generated subject; pass ``recipient=SubjectFactory.copy_of_account(
    fiscal_data)`` to make it the tenant, as the API does.
    """

    kind = InvoiceKind.RECEIVED
    state = InvoiceState.ISSUED
    invoice_number = factory.SubFactory(SupplierNumberFactory)
    serial_id = None

    @factory.post_generation
    def lines(self: Invoice, create: bool, extracted: int | list[InvoiceLine] | None, **kwargs):
        kwargs.setdefault("description", fuzzy.FuzzyChoice(EXPENSE_CONCEPTS))
        kwargs.setdefault("quantity", fuzzy.FuzzyDecimal(1, 3, precision=0))  # bills, not hours
        _generate_lines(self, create, extracted, **kwargs)
