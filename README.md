# Isofactu

Invoice management application for freelancers and SMEs, with a Spanish tax context (VAT, retention, NIF/CIF identification).

## Stack

| Layer      | Technology                                              |
|------------|---------------------------------------------------------|
| Backend    | Python 3.12, FastAPI, Uvicorn                           |
| ORM        | SQLAlchemy 2 (async, psycopg 3) + Alembic migrations    |
| Frontend   | React 19 + TypeScript, Vite 5, Tailwind CSS 3           |
| Charts     | Recharts                                                |
| Database   | PostgreSQL 17 (Docker)                                  |
| Runtime    | Docker Compose                                          |

The backend exposes a JSON API under `/api` (OpenAPI contract at `/api/docs`) and serves the
compiled frontend from the `public/` directory as a single-page application. The frontend is a
standalone React app that only talks to the API.

## Quick start

Requirements: Docker with Compose v2. Nothing else needs to be installed on the host — Python,
Node, pytest, ruff, eslint, Alembic… all run inside the containers.

```bash
docker compose up --build          # or: make up
```

This starts three things:

1. `db` — PostgreSQL 17 (exposed on `127.0.0.1:5433`).
2. `frontend-build` — one-shot Node container that compiles the React app into `./public` and exits.
3. `backend` — FastAPI server: applies Alembic migrations, then serves the API **and** the SPA.

Open http://localhost:8000 for the app and http://localhost:8000/api/docs for the API documentation.

To populate the database with generated fixtures: `LOAD_FIXTURES=1 docker compose up --build`
(see [Fixtures](#fixtures)).

## Development workflow

Everything happens through Docker. `./backend` is bind-mounted into the `backend` container and
Uvicorn runs with `--reload`, so backend edits are live immediately and the tools inside the
container (pytest, ruff, alembic, the fixtures CLI) always see your working copy.

```bash
make dev                            # stack + Vite dev server with HMR on http://localhost:5173
make shell                          # bash inside the backend container
docker compose exec backend <cmd>   # run any command inside the backend container
docker compose run --rm --no-deps frontend-build npm run <script>   # frontend tooling (Node)
```

`make help` lists every available target. The `Makefile` is just a thin wrapper: each target
prints the underlying `docker compose` command when it runs.

<details>
<summary>Running the backend directly on the host (optional)</summary>

If you prefer a local virtualenv, the root `.env` already points `DATABASE_URL` at the Dockerised
database:

```bash
docker compose up -d db
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload       # http://localhost:8000
```

Likewise `cd frontend && npm install && npm run dev` runs the Vite dev server on the host.
</details>

## API

| Method | Path                        | Description                                    |
|--------|-----------------------------|------------------------------------------------|
| GET    | `/api/health`               | Health check (`200 {"status": "ok", ...}`)     |
| GET    | `/api/docs`                 | Swagger UI (`/api/redoc`, `/api/openapi.json`) |
| GET    | `/api/invoice`              | Collection of invoices (`?state=&limit=&offset=`) |
| GET    | `/api/invoice/{id}`         | Invoice detail                                 |
| POST   | `/api/invoice`              | Create an invoice (draft or issued) with its lines |
| PUT    | `/api/invoice/{id}`         | Replace a draft invoice, or issue it           |
| GET    | `/api/subject`              | Collection of subjects (`?q=&limit=&offset=`)  |
| GET    | `/api/subject/{id}`         | Subject detail                                 |
| POST   | `/api/subject`              | Create a subject                               |

Example — `GET /api/invoice`:

```json
{
  "items": [
    {
      "id": 1,
      "issueDate": "2026-06-08",
      "invoiceNumber": { "serial": "F-2026", "number": "42", "formatted": "F-2026-42" },
      "state": "ISSUED",
      "notes": "Pago a 30 días.",
      "dueDate": "2026-07-08",
      "paymentMethod": "TRANSFER",
      "retentionRate": 0,
      "issuer":    { "id": 1, "fullName": "Néstor Freelance",  "document": { "type": "NIF", "number": "12345678Z" },
                     "address": { "street": "Calle Luna 5", "zipCode": "35001", "city": "Las Palmas", "province": "Las Palmas", "countryIsoCode": "ES" } },
      "recipient": { "id": 2, "fullName": "Tech Solutions SL", "document": { "type": "CIF", "number": "B12345678" }, "address": { "...": "..." } },
      "lines": [
        { "id": 1, "description": "Desarrollo web", "quantity": 40, "unitPrice": 60, "taxRate": 21,
          "subtotal": 2400, "taxAmount": 504, "total": 2904 }
      ],
      "subtotal": 2400,
      "taxAmount": 504,
      "retentionAmount": 0,
      "total": 2904
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

Conventions:

- JSON keys are camelCase; the TypeScript types live in `frontend/src/api/types.ts`.
- `state` is the invoice lifecycle state: `DRAFT` (being prepared) or `ISSUED` (emitted). New
  invoices are created as `DRAFT` unless the payload says otherwise; `GET /api/invoice?state=`
  filters the collection (and its `total`) by state.
- Drafts are numberless (`invoiceNumber` is `null` and must not be sent). When creating an
  `ISSUED` invoice, send `"invoiceNumber": {"serial": "F-2026"}` to get the next sequential number
  of that serial assigned (`F-2026-43`), or include `"number"` to pick one explicitly.
- `PUT /api/invoice/{id}` replaces a draft in full (lines included); sending `"state": "ISSUED"`
  issues it and assigns its number. Issued invoices are immutable (`409 Conflict`).
- `issueDate` cannot be in the future and `dueDate` cannot be earlier than it.
- Drafts and issued invoices obey the same content rules: at least one line, a non-blank
  `description` on every line and a positive subtotal. Anything else is a `422`.
- Line amounts: `subtotal = quantity × unitPrice`, `total = subtotal + taxAmount` (VAT). The
  optional IRPF withholding applies to the whole invoice: `retentionAmount = subtotal × retentionRate`
  is deducted from the invoice `total`.
- Monetary amounts are JSON numbers with at most two decimals (`120.98`); the backend validates and
  computes them with `Decimal`, so nothing is lost in arithmetic. Inputs also accept numeric strings.
- Line amounts use scale 2 with **half-up rounding** (`99.99 × 21 % = 20.9979 → 21.00`).

## Project structure

```
isofactu/
├── compose.yaml               # Docker Compose: db, backend, frontend-build, frontend (dev profile)
├── .env                       # Shared defaults (Postgres credentials, ports, DATABASE_URL)
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app factory (/api/docs, CORS, SPA mount)
│   │   ├── api.py             # /api router (+ /api/health)
│   │   ├── spa.py             # Serves ./public with history-API fallback
│   │   ├── core/              # Settings, async engine / session, declarative base
│   │   ├── invoicing/         # Invoicing module
│   │   │   ├── models.py      #   Subject, Invoice, InvoiceLine (SQLAlchemy)
│   │   │   ├── value_objects.py  # InvoiceNumber, IdentificationDocument, Address (composites)
│   │   │   ├── document_type.py  # CIF | NIF | OTHER
│   │   │   ├── invoice_state.py  # DRAFT | ISSUED
│   │   │   ├── payment_method.py # TRANSFER | CASH | CARD | DIRECT_DEBIT
│   │   │   ├── money.py       #   bcmath-compatible decimal helpers
│   │   │   ├── schemas.py     #   Pydantic models = API contract
│   │   │   ├── repository.py  #   Data access
│   │   │   └── router.py      #   /api/invoice, /api/subject
│   │   ├── fixtures/          # factory_boy factories + loader (shared by tests and CLI)
│   │   └── cli.py             # Management commands (`python -m app.cli fixtures load`)
│   ├── alembic/               # Migrations (`alembic revision --autogenerate -m "..."`)
│   ├── tests/                 # pytest (unit + API integration against PostgreSQL)
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/               # Typed API client + contract types
│   │   ├── pages/             # Dashboard, Invoices, CreateInvoice
│   │   ├── components/        # TopNav, dashboard widgets, invoice form, invoice table
│   │   └── lib/               # Formatting helpers, useApi hook
│   └── vite.config.ts         # Builds to ../public, proxies /api in dev
└── public/                    # Built frontend assets (generated, git-ignored)
```

## Key concepts

- **Subject** — a company or person identified by NIF/CIF that acts as issuer or recipient on an invoice.
- **Invoice** — links an issuer and a recipient, has a date, an invoice number, a state (`DRAFT` → `ISSUED`) and an optional IRPF retention rate, and contains one or more lines.
- **InvoiceLine** — a concept with description, quantity, unit price and VAT rate. Amounts are computed with fixed-point decimals.
- **InvoiceNumber** — value object with an optional serial and a sequential number (`F-2026-42`); unassigned while the invoice is a draft.

## Fixtures

Test/demo data is defined **once** as [factory_boy](https://factoryboy.readthedocs.io/) factories
in `backend/app/fixtures/factories.py` (with Faker's `es_ES` locale: valid NIF/CIF numbers, Spanish
names and addresses) and consumed from two places:

**1. Manually, through the management CLI** (inside the backend container) — to fill a
development database:

```bash
make fixtures                                   # purge + 1 issuer, 6 clients, 20 invoices, seed 42
make fixtures ARGS="--invoices 50 --clients 10" # same, with options
make fixtures-purge                             # remove all invoicing data

# the underlying commands
docker compose exec backend python -m app.cli fixtures load --invoices 50 --seed 42 --purge
docker compose exec backend python -m app.cli fixtures purge
docker compose exec backend python -m app.cli --help

LOAD_FIXTURES=1 docker compose up               # or: load on container start (FIXTURES_INVOICES, FIXTURES_SEED)
```

`--seed` makes the generated data reproducible. Destructive commands ask for confirmation
(`--yes` skips it) and refuse to run when `APP_ENV=prod` unless `--force` is given.

**2. In tests, as pytest fixtures** (`backend/tests/conftest.py`):

```python
async def test_something(client, invoice_factory, subject):
    invoice_factory.create_batch(3, recipient=subject, lines=1)   # added to the test session
    response = await client.get("/api/invoice")
    assert response.json()["total"] == 3

async def test_other(invoice):            # a persisted invoice with issuer, recipient and lines
    assert invoice.total > 0

def test_pure():                          # no database needed
    invoice = InvoiceFactory.build(lines=2, issuer__document__type=DocumentType.CIF)
```

| Fixture                                                      | Provides                                   |
|--------------------------------------------------------------|--------------------------------------------|
| `subject_factory`, `invoice_factory`, `invoice_line_factory` | Factory classes bound to the test session  |
| `subject`, `invoice`                                         | One persisted instance                     |
| `session`, `client`                                          | Async SQLAlchemy session / HTTP test client|

Factories only `session.add()` — they never flush or commit on their own, so they behave the same
with the async session used by the app. Adding a new entity means adding one factory class; both
the CLI and the tests pick it up.

## Database migrations

Alembic runs inside the backend container (migrations are also applied automatically on
container start; `RUN_MIGRATIONS=0` disables that). Because `./backend` is bind-mounted, generated
migration files land in `backend/alembic/versions/` on the host, ready to commit.

```bash
make migrate                                  # apply pending migrations
make migration MSG="add due date to invoice"  # autogenerate a migration from the models
docker compose exec backend alembic check     # verify models and migrations are in sync
docker compose exec backend alembic history
```

## Tests & linting

> All commands run **inside the containers** — do not run `pytest`, `ruff` or `npm` on the host.
> The stack must be up (`make up` / `docker compose up`) so that the `backend` container and the
> database exist.

```bash
make test              # backend tests + frontend type-check
make lint              # ruff + eslint
```

Or, explicitly:

```bash
# Backend — integration tests use a `<db>_test` database, created automatically
docker compose exec backend pytest
docker compose exec backend pytest tests/test_api.py -k invoice -v   # any pytest arguments
docker compose exec backend ruff check .
docker compose exec backend ruff format --check .

# Frontend — uses the node_modules volume populated by the `frontend-build` service
docker compose run --rm --no-deps frontend-build npm run typecheck
docker compose run --rm --no-deps frontend-build npm run lint
```

The backend image installs the dev tooling (pytest, ruff, …) because `BACKEND_INSTALL_DEV=true`
in `.env`; set it to `false` to build a lean production image.
