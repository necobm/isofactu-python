# Isofactu

Invoice management application for freelancers and SMEs, with a Spanish tax context (VAT, retention, NIF/CIF identification).

The goal is a B2B SaaS that gives Spanish *autónomos* a single place to manage their invoices —
both issued (income) and received (expenses) — plus tools to keep track of and forecast their
expenses and taxes (VAT, IRPF).

## Important Notice

> All data regarding invoices, clients, companies in this project, are not real. They are dynamically
> generate using sample data.

## Roadmap

### Where we are today

The core of **issued invoices** works end to end (API + UI):

- [x] Create, edit and list invoices with a `DRAFT` → `ISSUED` lifecycle. Drafts are editable and
      numberless; issued invoices are immutable and get the next sequential number of their serial.
- [x] Concepts with description, quantity, unit price and per-line VAT rate; invoice-level IRPF
      retention; subtotal / tax / retention / total computed server-side with exact decimals.
- [x] Issue date, due date (validated), payment method and free-text notes.
- [x] Pick the invoice's client from the client directory (search by name or NIF/CIF); the
      invoice keeps its own copy of the client's data.
- [x] Invoice list filtered by state, with detail view.
- [x] Docker-based dev workflow, migrations, fixtures and API test suite.
- [x] **Accounts and authentication** — e-mail + password login (no self-registration), two
      roles (`SUPER_ADMIN` manages accounts, `ADMIN` is a tenant with its own data), account
      activation by e-mail link, pause / activate / delete accounts, per-tenant data isolation.
      See [Accounts & authentication](#accounts--authentication).
- [x] **Fiscal data** — each tenant sets its company name, CIF/NIF and address in *Ajustes*;
      the server stamps it as issuer on every invoice it saves (a copy lives on the invoice, so
      issued invoices keep the data they were issued with).
- [x] **Serials** — numbering series managed per tenant in *Ajustes* (prefix, initial number,
      suffix, optional validity period); issued invoices take the next correlative number of the
      chosen serial. See [Invoice numbering](#invoice-numbering).
- [x] **Clients** — a client directory (*Clientes*: searchable list, create / edit forms, delete
      with confirmation), independent from invoicing: an invoice gets a *copy* of the chosen
      client as its recipient (`Subject`), never a reference. See [Clients](#clients).
- [x] **Received invoices (expenses)** — *Facturas* is split into *Emitidas* and *Recibidas*.
      Received invoices have the same concepts, VAT, IRPF, dates, payment method and notes as
      issued ones; the supplier and its invoice number are typed in, the account's fiscal data
      is the recipient, and there are no drafts: they can always be edited. See
      [Received invoices](#received-invoices-expenses).
- [x] **Import received invoices from PDF** — upload the supplier's PDF (any layout, scans
      included) and the form is filled in from it, to review before saving. Read by an LLM of
      any vendor (LiteLLM); off unless `LLM_PROVIDER` / `LLM_MODEL` are set. See
      [Importing from PDF](#importing-from-pdf).
- [x] **Dashboard** — income, expenses and what is pending collection, plus an income vs
      expenses chart, all computed from the account's invoices for a chosen period; issued
      invoices can be marked as collected. See [Dashboard](#dashboard).

Partially there, with known gaps:

- [ ] **Fiscal data** — cannot be overridden for a single invoice yet.
- [ ] **Clients** — cannot be created inline from the invoice form yet; suppliers are not
      modelled either: the supplier of a received invoice is typed in every time.
- [ ] **Drafts** — must already satisfy the same content rules as issued invoices (the spec allows
      incomplete drafts) and cannot be deleted.

### Next: complete the MVP

1. **Per-invoice issuer** — allow editing the fiscal data for a single invoice only.
2. **Suppliers** — a supplier directory to pick the issuer of received invoices from; create a
   client inline from the invoice form.
3. **Draft rules** — let drafts be saved incomplete, enforce required fields only when issuing,
   and allow deleting drafts.
4. **Taxes**
   - VAT to pay for a date range, with presets (*this month*, *current quarter*, *current year*).
   - Pending IRPF from income and IRPF already withheld/advanced, by quarter or fiscal year.
5. **Tax figures on the dashboard** — VAT to pay and IRPF, once the taxes above are computed.

### Later: beyond the MVP

- Expense control and forecasting (expense trends, upcoming tax payments).
- Account hardening: login rate limiting, self-service password reset, audit log of the
  SUPER_ADMIN actions.

## Stack

| Layer      | Technology                                              |
|------------|---------------------------------------------------------|
| Backend    | Python 3.12, FastAPI, Uvicorn                           |
| ORM        | SQLAlchemy 2 (async, psycopg 3) + Alembic migrations    |
| Frontend   | React 19 + TypeScript, Vite 5, Tailwind CSS 3, react-select |
| Charts     | Recharts                                                |
| Database   | PostgreSQL 17 (Docker)                                  |
| Auth       | bcrypt password hashes, signed HttpOnly session cookie (PyJWT) |
| Geo data   | ISO 3166 countries / provinces (pycountry, Spanish names), GeoNames postal codes and localities |
| E-mail     | SMTP (stdlib) — Mailpit in development                  |
| Invoice reading | Any LLM vendor through LiteLLM (+ pypdf): PDF import of received invoices |
| Runtime    | Docker Compose                                          |

The backend exposes a JSON API under `/api` (OpenAPI contract at `/api/docs`) and serves the
compiled frontend from the `public/` directory as a single-page application. The frontend is a
standalone React app that only talks to the API.

## Quick start

Requirements: Docker with Compose v2. Nothing else needs to be installed on the host — Python,
Node, pytest, ruff, eslint, Alembic… all run inside the containers.

```bash
cp .env.example .env               # then fill in the values (see below)
docker compose up --build          # or: make up
```

`.env.example` is a template: `.env` itself is git-ignored and must never be committed, as it
holds the passwords and secrets. At least set `POSTGRES_USER` / `POSTGRES_PASSWORD` (compose
has no default database password), a random `SECRET_KEY`, and the first `SUPER_ADMIN_EMAIL` /
`SUPER_ADMIN_PASSWORD`. Real environment variables take precedence over `.env`.

This starts four things:

1. `db` — PostgreSQL 17 (exposed on `127.0.0.1:5433`).
2. `mailpit` — catches every e-mail the app sends (activation links). Web UI on http://localhost:8025.
3. `frontend-build` — one-shot Node container that compiles the React app into `./public` and exits.
4. `backend` — FastAPI server: applies Alembic migrations, creates the first `SUPER_ADMIN`
   account, then serves the API **and** the SPA.

Open http://localhost:8000 for the app and http://localhost:8000/api/docs for the API documentation.

Log in with the `SUPER_ADMIN` account set in your `.env`
to reach the account management panel, create an `ADMIN` account (a tenant) and pick up its
activation link in Mailpit. Or populate the database with generated fixtures —
`LOAD_FIXTURES=1 docker compose up --build` — which also creates a demo tenant you can log in as
(`demo@isofactu.local` / `demo1234`, see [Fixtures](#fixtures)).

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

If you prefer a local virtualenv, point `DATABASE_URL` in your `.env` at the Dockerised
database (`postgresql+psycopg://<user>:<password>@127.0.0.1:5433/isofactu`):

```bash
docker compose up -d db mailpit
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.cli users create-super-admin --email admin@isofactu.local   # prompts for a password
uvicorn app.main:app --reload       # http://localhost:8000
```

`.env.example` points `SMTP_HOST` at the Mailpit container's published port. With `SMTP_HOST`
empty, outgoing e-mails are written to the backend log instead (activation links included).

Likewise `cd frontend && npm install && npm run dev` runs the Vite dev server on the host.
</details>

## API

Everything except the health check, the docs, the login and the activation endpoints requires a
session (see [Accounts & authentication](#accounts--authentication)). Invoicing endpoints need an
`ADMIN` (tenant) session and only ever return that tenant's data; `/api/admin/*` needs a
`SUPER_ADMIN` session.

| Method | Path                                    | Who          | Description                                    |
|--------|-----------------------------------------|--------------|------------------------------------------------|
| GET    | `/api/health`                           | public       | Health check (`200 {"status": "ok", ...}`)     |
| GET    | `/api/docs`                             | public       | Swagger UI (`/api/redoc`, `/api/openapi.json`) |
| POST   | `/api/auth/login`                       | public       | `{email, password}` → user + session cookie (`401` bad credentials, `403` paused) |
| POST   | `/api/auth/logout`                      | session      | Clears the session cookie                      |
| GET    | `/api/auth/me`                          | session      | The logged-in user                             |
| POST   | `/api/auth/password`                    | session      | `{currentPassword, newPassword}` → change own password (`400` if the current one is wrong) |
| GET    | `/api/auth/activate/{token}`            | public       | Who an activation link is for (`404` if unknown, used or expired) |
| POST   | `/api/auth/activate/{token}`            | public       | `{password}` → sets the password, activates the account, consumes the link |
| GET    | `/api/admin/user`                       | SUPER_ADMIN  | Collection of accounts (`?limit=&offset=`)     |
| POST   | `/api/admin/user`                       | SUPER_ADMIN  | Create a (paused) account and e-mail its activation link |
| GET    | `/api/admin/user/{id}`                  | SUPER_ADMIN  | Account detail                                 |
| PUT    | `/api/admin/user/{id}`                  | SUPER_ADMIN  | Update e-mail, name, role                      |
| DELETE | `/api/admin/user/{id}`                  | SUPER_ADMIN  | Delete the account **and everything it owns**  |
| POST   | `/api/admin/user/{id}/pause`            | SUPER_ADMIN  | Pause (cannot log in; pending link revoked)    |
| POST   | `/api/admin/user/{id}/activate`         | SUPER_ADMIN  | Activate manually                              |
| POST   | `/api/admin/user/{id}/send-activation`  | SUPER_ADMIN  | (Re)send the activation link                   |
| GET    | `/api/admin/settings`                   | SUPER_ADMIN  | System settings (`{"activationLinkTtlHours": 24}`) |
| PUT    | `/api/admin/settings`                   | SUPER_ADMIN  | Update system settings                         |
| GET    | `/api/fiscal-data`                      | ADMIN        | The account's fiscal data (issuer of its invoices), `null` until set up |
| PUT    | `/api/fiscal-data`                      | ADMIN        | Create / replace the fiscal data                |
| GET    | `/api/serial`                           | ADMIN        | The account's numbering serials, with usage and next number |
| POST   | `/api/serial`                           | ADMIN        | Create a serial (`409` if prefix + suffix already exist) |
| GET    | `/api/serial/{id}`                      | ADMIN        | Serial detail                                  |
| PUT    | `/api/serial/{id}`                      | ADMIN        | Update a serial (`409` when changing prefix / suffix / initial number of one in use) |
| DELETE | `/api/serial/{id}`                      | ADMIN        | Delete a serial (`409` when issued invoices use it) |
| GET    | `/api/geo/countries`                    | session      | ISO countries named in Spanish, with postal code patterns |
| GET    | `/api/geo/countries/{cc}/provinces`     | session      | Lowest-level ISO 3166-2 divisions of a country (Spain: provinces) |
| GET    | `/api/geo/countries/{cc}/provinces/{p}/cities` | session | Known localities of a province (suggestions)  |
| GET    | `/api/client`                           | ADMIN        | Collection of clients (`?q=&limit=&offset=`)   |
| GET    | `/api/client/{id}`                      | ADMIN        | Client detail                                  |
| POST   | `/api/client`                           | ADMIN        | Create a client                                |
| PUT    | `/api/client/{id}`                      | ADMIN        | Replace a client (invoices are not affected)   |
| DELETE | `/api/client/{id}`                      | ADMIN        | Delete a client (invoices keep their copy)     |
| GET    | `/api/invoice`                          | ADMIN        | Collection of issued invoices (`?state=&limit=&offset=`) |
| GET    | `/api/invoice/{id}`                     | ADMIN        | Issued invoice detail                          |
| POST   | `/api/invoice`                          | ADMIN        | Create an invoice (draft or issued) for `clientId` with its lines (`409` until the fiscal data is set) |
| PUT    | `/api/invoice/{id}`                     | ADMIN        | Replace a draft invoice (optionally re-pointing it at a `clientId`), or issue it |
| PUT    | `/api/invoice/{id}/collection`          | ADMIN        | `{collectedOn}`: the day the client paid an issued invoice, or `null` for pending (`409` for drafts) |
| GET    | `/api/dashboard`                        | ADMIN        | Income, expenses and their monthly series for `?from=&to=`, plus what is pending collection |
| GET    | `/api/received-invoice`                 | ADMIN        | Collection of received invoices (`?limit=&offset=`) |
| GET    | `/api/received-invoice/{id}`            | ADMIN        | Received invoice detail                        |
| POST   | `/api/received-invoice`                 | ADMIN        | Record a supplier's invoice: supplier, number (required) and lines as entered (`409` until the fiscal data is set) |
| PUT    | `/api/received-invoice/{id}`            | ADMIN        | Replace a received invoice (always allowed)    |
| POST   | `/api/received-invoice/extract`         | ADMIN        | Read a supplier's invoice from a PDF (multipart `file`) → a draft to pre-fill the form; nothing is stored |

Example — `GET /api/invoice`:

```json
{
  "items": [
    {
      "id": 1,
      "kind": "ISSUED",
      "issueDate": "2026-06-08",
      "invoiceNumber": { "prefix": "F-2026-", "number": "42", "suffix": "", "formatted": "F-2026-42" },
      "serialId": 1,
      "state": "ISSUED",
      "notes": "Pago a 30 días.",
      "dueDate": "2026-07-08",
      "paymentMethod": "TRANSFER",
      "retentionRate": 0,
      "issuer":    { "fullName": "Néstor Freelance",  "document": { "type": "NIF", "number": "12345678Z" },
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
- The `issuer` of an invoice is never sent by the client: the server copies the account's
  **fiscal data** (`PUT /api/fiscal-data`) onto the invoice when it is created or a draft is
  saved. Issued invoices keep that copy for good, even if the fiscal data changes later.
- Likewise the `recipient` is the invoice's own copy of the client sent as `clientId`
  (required on `POST`). On a draft `PUT`, sending `clientId` refreshes the copy from that
  client; omitting it keeps the recipient as it is. There is no `subject` API: subjects only
  exist as part of an invoice.
- `state` is the invoice lifecycle state: `DRAFT` (being prepared) or `ISSUED` (emitted). New
  invoices are created as `DRAFT` unless the payload says otherwise; `GET /api/invoice?state=`
  filters the collection (and its `total`) by state.
- Drafts are numberless (`invoiceNumber` is `null`); they may carry a `serialId` to remember the
  serial they will be issued with. Issuing (`"state": "ISSUED"`) requires a `serialId` whose serial
  is available on the `issueDate`: the next correlative number of that serial is assigned and its
  prefix / suffix are copied onto the invoice. Numbers cannot be chosen by hand.
- `PUT /api/invoice/{id}` replaces a draft in full (lines included); sending `"state": "ISSUED"`
  issues it and assigns its number. Issued invoices are immutable (`409 Conflict`).
- `issueDate` cannot be in the future and `dueDate` cannot be earlier than it.
- `/api/invoice` only ever sees **issued** invoices and `/api/received-invoice` only **received**
  ones (`kind` in the payload says which): an invoice of the other kind is a `404`, like another
  tenant's. Both share the read model and the content rules below; see
  [Received invoices](#received-invoices-expenses) for what differs.
- Drafts and issued invoices obey the same content rules: at least one line, a non-blank
  `description` on every line and a positive subtotal. Anything else is a `422`.
- Line amounts: `subtotal = quantity × unitPrice`, `total = subtotal + taxAmount` (VAT). The
  optional IRPF withholding applies to the whole invoice: `retentionAmount = subtotal × retentionRate`
  is deducted from the invoice `total`.
- Monetary amounts are JSON numbers with at most two decimals (`120.98`); the backend validates and
  computes them with `Decimal`, so nothing is lost in arithmetic. Inputs also accept numeric strings.
- Line amounts use scale 2 with **half-up rounding** (`99.99 × 21 % = 20.9979 → 21.00`).

## Dashboard

*Panel* shows the account's activity, computed from its invoices, for the period chosen at the
top (*Este mes*, *Este trimestre*, *Este año* — the default —, *Últimos 12 meses*, *Año
anterior*, *Todo*):

- **Ingresos** — the taxable base (without VAT) of the invoices issued in the period, and how
  many there are.
- **Gastos** — the same for the invoices received from suppliers.
- **Pendiente de cobro** — what clients still owe: the total (VAT included, IRPF withheld) of
  the issued invoices not collected yet, **whatever their date**, and how much of it is
  overdue (past its due date). Links to the issued invoices.
- **Ingresos vs Gastos** — the month-by-month taxable base of both, for the months of the
  period (the tooltip adds the month's result).

Drafts are never counted. Amounts are computed in the database from the invoice lines with the
same per-line rounding as the invoices themselves (`app/dashboard/repository.py`), so they match
the invoices to the cent.

**Collecting invoices.** Issued invoices show whether they are collected (*Cobrada*, *Pendiente*,
*Vencida*); the details of one let you mark it as collected on a given date (not before its
issue date nor in the future) or back as pending. This is recorded on the invoice
(`collectedOn`) but is not part of its content, so it can change after issuing. Migration `0012`
adds it; existing invoices start as pending.

## Received invoices (expenses)

*Facturas* in the top bar opens a menu with two sections: **Emitidas** (income, invoices to
clients: drafts and issued invoices) and **Recibidas** (expenses, invoices from suppliers: a
single list). A received invoice is recorded with *Registrar Factura Recibida*; clicking one in
the list opens it for editing.

A received invoice has what an issued one has — concepts with VAT, invoice-level IRPF
retention, issue / due date, payment method and notes — except:

| | Issued invoice (`/api/invoice`) | Received invoice (`/api/received-invoice`) |
|---|---|---|
| `issuer` | The account's fiscal data, stamped by the server | **The supplier, typed in** (`issuer` in the payload) |
| `recipient` | A copy of the client `clientId` | The account's fiscal data, stamped by the server when the invoice is recorded |
| `invoiceNumber` | Next number of the serial `serialId`, assigned when issuing | **The supplier's number, whole and as printed (`{"number": "FV-2026/0042"}`), required** — which part of it is a series is not the user's concern, so `prefix` / `suffix` stay empty |
| `serialId` | The serial used | Always `null`: received invoices never take a number from, or lock, a serial |
| `state` | `DRAFT` → `ISSUED`; immutable once issued | Not in the payload; always `ISSUED` (the supplier issued it), and **always editable** |

- The supplier is validated like a client: name, a NIF / CIF with a valid check character (or
  `OTHER` for foreign identifiers) and a full address checked against the Geo module. The form
  reuses the client form's fields.
- The recipient is the fiscal data as it was when the invoice was recorded: later edits of the
  invoice keep it, even if the fiscal data has changed since.
- There is no supplier directory yet (see the roadmap): the supplier is entered on each invoice.
- Nothing checks for duplicates: recording the same supplier invoice twice counts it twice.

Both kinds live in the `invoice` table, told apart by its `kind` column (`ISSUED` | `RECEIVED`);
check constraints keep received invoices without a serial and in the `ISSUED` state. Migration
`0009` adds the column and marks every existing invoice as issued (its downgrade deletes the
received invoices); `0010` turns received drafts recorded with the first version of the feature
into plain received invoices (one without a number shows none until it is edited, which
requires it); `0011` folds the series some received numbers were stored with into the number
itself (they render the same).

### Importing from PDF

When recording a received invoice, *Importar desde PDF* (right column) takes the supplier's
PDF and fills in the form with what it reads: supplier (name, NIF / CIF, address), invoice
number, dates, payment method, concepts with their VAT rate, and IRPF. While the PDF is read
(a few seconds) the form is locked and the button shows a spinner. **Nothing is saved**: the
user reviews the data and saves as usual. The panel also warns when the invoice is addressed
to someone other than the account, and when the concepts do not add up to the total printed
on the invoice (live, until they match).

How it works (`app/invoicing/extraction.py`, `POST /api/received-invoice/extract`):

- Supplier invoices come in every layout, and some are scans, so they are not parsed with
  rules: they are read by an **LLM**, reached through [LiteLLM](https://docs.litellm.ai/) so
  that the vendor and model are just configuration (Anthropic, OpenAI, Gemini, Mistral, Azure,
  Bedrock, a local Ollama...). The model must answer with JSON following a schema of the data
  we need (using the vendor's structured output when LiteLLM knows it has one, the prompt
  otherwise). The account's fiscal data is given as the expected customer, so that the
  supplier is not mixed up with it.
- Models that can read PDF files (Claude, GPT-4o, Gemini...) get the PDF itself, so **scanned
  invoices** work too. The others get the PDF's text layer (pypdf): they work with regular
  PDFs, while a scan is refused with a message saying so.
- The answer is treated as untrusted input and normalised before reaching the form: NIF /
  CIF detected by their check character (`ESB12345674` → CIF `B12345674`), Spanish provinces
  derived from the postal code (invoices print "Bizkaia", "Lleida", "A Coruña"...), amounts
  rounded to cents, rates bounded, anything unusable left empty.
- Rates outside the form's presets (IGIC 7 %, the 19 % IRPF of rents...) are kept and shown.

Configuration (`.env` / environment; see `.env.example`):

| Variable | Default | |
|---|---|---|
| `LLM_PROVIDER` | *(empty)* | A [LiteLLM provider](https://docs.litellm.ai/docs/providers): `anthropic`, `openai`, `gemini`, `mistral`, `azure`, `bedrock`, `ollama`... |
| `LLM_MODEL` | *(empty)* | The vendor's model, e.g. `claude-sonnet-4-5`, `gpt-4o`, `gemini-2.5-flash`, `llama3.1`. With `LLM_PROVIDER`, enables the feature; without them the button answers that PDF import is not available (`503`). |
| `LLM_API_KEY` | *(empty)* | The vendor's API key (a secret: only in your `.env`). Not needed by local models. |
| `LLM_API_BASE` | *(empty)* | A custom endpoint: an Ollama server, an Azure deployment, a proxy... |
| `LLM_TIMEOUT` | `120` | Seconds before giving up on a PDF |
| `INVOICE_PDF_MAX_BYTES` | `10485760` | Largest PDF accepted (`413` above) |

For example:

```bash
LLM_PROVIDER=anthropic  LLM_MODEL=claude-sonnet-4-5  LLM_API_KEY=sk-ant-...
LLM_PROVIDER=openai     LLM_MODEL=gpt-4o             LLM_API_KEY=sk-...
LLM_PROVIDER=gemini     LLM_MODEL=gemini-2.5-flash   LLM_API_KEY=...
LLM_PROVIDER=ollama     LLM_MODEL=llama3.1           LLM_API_BASE=http://host.docker.internal:11434
```

Vendors that need more than a key (the API version of Azure, the AWS credentials of
Bedrock...) read LiteLLM's own variables for them (`AZURE_API_VERSION`, `AWS_REGION_NAME`...):
add those to the `backend` service environment in `compose.yaml`. LiteLLM is set to use the
model metadata bundled with it rather than downloading it from GitHub at run time.

> **Privacy.** Importing sends the PDF — personal and financial data of the supplier and of
> the account — to the configured LLM vendor (nothing leaves your network with a local
> model). Make sure that is acceptable (and covered by your data processing agreements)
> before enabling it in production. The backend never logs the contents of an invoice. With
> a hosted vendor, every import is a paid API call.

## Clients

The *Clientes* page is the tenant's client directory: a searchable, paginated list (name,
NIF/CIF, address) with an **edit** and a **delete** icon per row — deleting asks for
confirmation — and a *Nuevo Cliente* button opening a full-page form like the invoice one.

Clients live in their own module (`app/clients`) and are **never referenced by invoices**: when
an invoice is created for a client, its data (name, NIF/CIF, address) is copied into a `Subject`
of the Invoicing module that belongs to that invoice. Editing or deleting a client therefore
never changes an invoice — issued ones show the client exactly as it was when they were issued.
A draft re-saved with a `clientId` refreshes its copy (in place when the copy is its own; legacy
drafts sharing a subject with another invoice get a fresh copy instead).

**Every field of a client is required and validated**: the name (2+ characters); the
identification — a NIF (DNI or NIE) or CIF is normalised (upper-case, no blanks or hyphens) and
its check character verified (`app/invoicing/spanish_ids.py`), `OTHER` accepts any foreign
identifier; and the address — street, postal code (checked against the country's format),
country (an ISO code), province and city.

The form's address block goes *Dirección → Código postal → País → Provincia → Ciudad*, with
searchable selects (react-select) fed by the **Geo module** (`app/geo`, `/api/geo/*`):

- **Countries**: all ISO 3166-1 countries, labelled with their Spanish name (`pycountry`'s
  translations); the ISO code is what gets stored.
- **Provinces** depend on the country: the lowest-level ISO 3166-2 divisions (for Spain, the
  50 provinces plus Ceuta and Melilla). The province *name* is stored and validated against
  that list; countries without ISO divisions get a free-text province.
- **Cities** depend on the province and act as suggestions: the user can type a locality that
  is not listed. The list comes from GeoNames (`scripts/build_geo_data.py` regenerates
  `app/geo/data/`). GeoNames only records the *autonomous community* of Spanish localities,
  so the list for a Spanish province covers its whole community; other countries have no list
  yet. To get exact per-province lists, replace `app/geo/data/cities.json` with a file keyed
  by ISO province codes (e.g. built from the INE municipality register).

Migration `0008` copies every pre-existing subject into the client directory and drops the ones
no invoice refers to.

## Invoice numbering

Invoice numbers are `prefix` + correlative number + `suffix`, taken from one of the tenant's
**serials** (*Ajustes → Series de facturación*). A serial has:

- a **prefix** and a **suffix** (letters, digits and `. _ / -`; no blanks) — at least one of the
  two is required, and the pair must be unique within the account (two serials producing the
  same numbers would be a problem);
- an **initial number** (≥ 1, default 1): the first invoice issued with the serial gets it, each
  following one gets the previous number + 1 (a transaction-scoped advisory lock makes this safe
  under concurrency);
- an optional **validity period** (`startDate`, `endDate`, both inclusive): an invoice can only
  take a number from the serial if its *issue date* falls inside it. Without an end date the
  serial never expires; the invoice form only offers the serials available on the chosen date.

Once an issued invoice uses a serial, its prefix, suffix and initial number are **frozen** and it
cannot be deleted — Spanish invoicing requires correlative, unbroken numbering within a series.
To retire a serial, give it an end date. Drafts that remembered a deleted (unused) serial simply
lose the reference.

Migration `0007` converts the free-text serials of existing invoices: every legacy serial `X` of
a tenant becomes a serial with prefix `X-` (so `F-2026` + `42` still renders `F-2026-42`) and its
invoices are linked to it.

## Accounts & authentication

There is no self-registration: accounts are created by a `SUPER_ADMIN` from the admin panel.

**Roles**

- `SUPER_ADMIN` — manages the accounts of the system (create, edit, pause / activate, delete,
  re-send activation links) and the system settings. Has **no** invoicing data and cannot see
  anybody's invoices: the invoicing endpoints answer `403`.
- `ADMIN` — a tenant. Owns its subjects and invoices; never sees other tenants' data (foreign
  ids are simply `404`, and invoice numbers are sequenced per tenant). Cannot reach `/api/admin`.

**Account lifecycle**

1. The `SUPER_ADMIN` creates the account (e-mail, optional name, role). It starts **paused** and
   without a password, and an e-mail with an activation link is sent right away (if the e-mail
   cannot be sent, nothing is created and the API answers `503`).
2. The link opens `/activate/<token>`, where the user chooses a password. Submitting the form
   sets the password, **activates** the account and **invalidates** the link.
3. Links expire after 24 hours by default; the `SUPER_ADMIN` can change that in *Ajustes*
   (1 h – 30 days, applied to links issued from then on) and can re-send a link at any time —
   which replaces the previous one and also works as a password reset for an active account.
4. Pausing an account takes effect immediately (its open sessions stop working, login answers
   `403`) and revokes any pending activation link. Activating manually does not hand out a
   password: a user without one still has to use a link. A `SUPER_ADMIN` cannot pause, delete
   or demote their own account.
5. Deleting an account removes everything it owns (subjects, invoices, lines) through database
   cascades.
6. Any logged-in user (either role) changes their own password from the user menu in the top
   bar (*Cambiar contraseña*), which asks for the current one. A forgotten password is recovered
   by a `SUPER_ADMIN` re-sending the activation link (or, for a `SUPER_ADMIN` locked out, with
   the CLI: `make super-admin` creates a fresh account).

**Sessions.** `POST /api/auth/login` sets an `HttpOnly`, `SameSite=Lax` cookie holding a signed
token (HS256, `SECRET_KEY`); `SESSION_TTL_HOURS` is its lifetime (7 days by default) and the
`Secure` flag is on when `APP_ENV=prod`. The user is loaded from the database on every request, so
pausing or deleting an account is effective at once. Passwords are stored as bcrypt hashes
(`PASSWORD_HASH_ROUNDS`, 12 by default) and must be 8–72 characters; login answers the same `401`
for unknown e-mails and wrong passwords (and takes the same time). CSRF is covered by the
`SameSite=Lax` cookie together with a JSON-only API and an explicit CORS allow-list.

**First SUPER_ADMIN.** The backend container creates it on start-up from `SUPER_ADMIN_EMAIL` /
`SUPER_ADMIN_PASSWORD` (`.env`) when the e-mail does not exist yet — change those values, or leave
them empty and use the CLI instead:

```bash
make super-admin EMAIL=admin@example.com        # prompts for the password
docker compose exec backend python -m app.cli users create-super-admin --email admin@example.com
```

**E-mail.** The backend container always talks to the `mailpit` service (host and port are fixed
in `compose.yaml`, like the database URL); `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` and
`MAIL_FROM` come from `.env`, and links are built from `APP_PUBLIC_URL`. Open http://localhost:8025
to read the activation e-mails. The `SMTP_HOST` / `SMTP_PORT` in `.env` only apply to a backend
running on the host; with `SMTP_HOST` empty, e-mails are written to the log instead of being
sent. For production, point the backend at a real relay through a compose override or the
environment.

**Migrating existing data.** Subjects and invoices created before accounts existed have no owner.
Migration `0005` hands them to a paused placeholder tenant, `legacy@isofactu.local`, so nothing is
lost: a `SUPER_ADMIN` can rename it, send it an activation link, or delete it (together with the
legacy data) from the panel. Fresh databases do not get that account.

## Project structure

```
isofactu/
├── compose.yaml               # Docker Compose: db, mailpit, backend, frontend-build, frontend (dev profile)
├── .env.example               # Template of `.env` (git-ignored): Postgres, ports, SECRET_KEY, SMTP, first SUPER_ADMIN, LLM
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app factory (/api/docs, CORS, SPA mount)
│   │   ├── api.py             # /api router (+ /api/health)
│   │   ├── spa.py             # Serves ./public with history-API fallback
│   │   ├── core/              # Settings, async engine / session, declarative base, mailer, ApiModel
│   │   ├── accounts/          # Accounts module
│   │   │   ├── models.py      #   User, ActivationToken, AppSetting
│   │   │   ├── role.py        #   SUPER_ADMIN | ADMIN
│   │   │   ├── account_status.py # ACTIVE | PAUSED
│   │   │   ├── security.py    #   bcrypt hashing, session tokens, activation tokens
│   │   │   ├── service.py     #   Create / activate / pause accounts, send links, authenticate
│   │   │   ├── deps.py        #   Current user + role guards (CurrentTenant, CurrentSuperAdmin)
│   │   │   ├── emails.py      #   Activation e-mail (text + HTML)
│   │   │   ├── schemas.py     #   Pydantic models = API contract
│   │   │   ├── repository.py  #   Data access (users, system settings)
│   │   │   └── router.py      #   /api/auth, /api/admin
│   │   ├── clients/           # Clients module: the client directory (/api/client)
│   │   ├── dashboard/         # Dashboard module: income, expenses, pending collection (/api/dashboard)
│   │   ├── geo/               # Geo module: countries, provinces, cities (+ data/, see scripts/)
│   │   ├── invoicing/         # Invoicing module (every row belongs to a tenant)
│   │   │   ├── models.py      #   FiscalData, Serial, Subject (recipient copy), Invoice, InvoiceLine
│   │   │   ├── value_objects.py  # InvoiceNumber, IdentificationDocument, Address, Issuer (composites)
│   │   │   ├── document_type.py  # CIF | NIF | OTHER
│   │   │   ├── invoice_kind.py   # ISSUED | RECEIVED (income / expense)
│   │   │   ├── extraction.py  #   Reading received invoices from PDF (any LLM, via LiteLLM) into a form draft
│   │   │   ├── invoice_state.py  # DRAFT | ISSUED
│   │   │   ├── payment_method.py # TRANSFER | CASH | CARD | DIRECT_DEBIT
│   │   │   ├── money.py       #   bcmath-compatible decimal helpers
│   │   │   ├── spanish_ids.py #   NIF / NIE / CIF validation
│   │   │   ├── schemas.py     #   Pydantic models = API contract
│   │   │   ├── repository.py  #   Data access, scoped to one tenant
│   │   │   └── router.py      #   /api/fiscal-data, /api/serial, /api/invoice, /api/received-invoice
│   │   ├── fixtures/          # factory_boy factories + loader (shared by tests and CLI)
│   │   └── cli.py             # Management commands (`users create-super-admin`, `fixtures load`)
│   ├── alembic/               # Migrations (`alembic revision --autogenerate -m "..."`)
│   ├── scripts/               # build_geo_data.py: regenerates app/geo/data from GeoNames
│   ├── tests/                 # pytest (unit + API integration against PostgreSQL)
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Auth gate + /activate/<token> route; picks the shell by role
│   │   ├── TenantApp.tsx      # ADMIN shell: dashboard, invoices (issued / received)...
│   │   ├── AdminApp.tsx       # SUPER_ADMIN shell: accounts, settings
│   │   ├── api/               # Typed API client (api, auth, admin) + contract types
│   │   ├── pages/             # Login, ActivateAccount, Dashboard, Invoices, InvoiceForm, Clients, ClientForm, settings pages, admin/
│   │   ├── components/        # TopNav, forms, SearchSelect (react-select), party fields (client / supplier), dashboard widgets, invoice form / table, admin/
│   │   └── lib/               # AuthProvider + useAuth, tiny router, formatting, useApi hook, party form helpers
│   └── vite.config.ts         # Builds to ../public, proxies /api in dev
└── public/                    # Built frontend assets (generated, git-ignored)
```

## Key concepts

- **User / account** — someone who can log in. `ADMIN` users are tenants: every subject and invoice has one as `owner`. `SUPER_ADMIN` users only manage accounts.
- **FiscalData** — the tenant's own identity (company name, CIF/NIF, address); one per account, edited in *Ajustes*.
- **Serial** — a numbering series of a tenant (prefix, initial number, suffix, validity period). Locked once an issued invoice uses it.
- **Client** — an entry of the tenant's client directory (name, NIF/CIF, address). Independent from invoices.
- **Subject** — an invoice's own copy of its recipient: taken from a client when an issued invoice is created, or from the fiscal data for a received one.
- **Invoice** — of a `kind`: `ISSUED` (income) or `RECEIVED` (expense). Carries a copy of its issuer (**Issuer** value object: the fiscal data, or the supplier as typed in), links a recipient, has a date, an invoice number, a state (`DRAFT` → `ISSUED` for issued invoices; received ones are always `ISSUED` and stay editable) and an optional IRPF retention rate, and contains one or more lines. Issued invoices also record the day they were collected (`collectedOn`).
- **InvoiceLine** — a concept with description, quantity, unit price and VAT rate. Amounts are computed with fixed-point decimals.
- **InvoiceNumber** — value object: prefix + sequential number + suffix (`F-2026-42`), copied from the serial at issue time; unassigned while the invoice is a draft. On a received invoice, the supplier's whole number as printed (no prefix / suffix).

## Fixtures

Test/demo data is defined **once** as [factory_boy](https://factoryboy.readthedocs.io/) factories
in `backend/app/fixtures/factories.py` (with Faker's `es_ES` locale: valid NIF/CIF numbers, Spanish
names and addresses) and consumed from two places:

**1. Manually, through the management CLI** (inside the backend container) — to fill a
development database. Everything generated belongs to a demo tenant, `demo@isofactu.local`
(password `demo1234`), created on first use — with generated fiscal data and a `F-<year>-`
serial — so that you can log in and browse the data. Issued invoices are numbered correlatively
from that serial in issue-date order, and most of those older than a few weeks are marked as
collected:

```bash
make fixtures                                   # purge + 6 clients, 20 issued + 8 received invoices, seed 42
make fixtures ARGS="--invoices 50 --received 20 --clients 10" # same, with options
make fixtures-purge                             # remove invoices, clients and serials (accounts and fiscal data are kept)

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
async def test_something(tenant_client, invoice_factory, tenant, subject):
    invoice_factory.create_batch(3, owner=tenant, recipient=subject, lines=1)   # added to the session
    response = await tenant_client.get("/api/invoice")       # logged in as `tenant`
    assert response.json()["total"] == 3

async def test_other(invoice):            # a persisted invoice (owned by `tenant`) with lines
    assert invoice.total > 0

def test_pure():                          # no database needed
    invoice = InvoiceFactory.build(lines=2, issuer__document__type=DocumentType.CIF)
```

| Fixture                                                      | Provides                                   |
|--------------------------------------------------------------|--------------------------------------------|
| `client_factory`, `subject_factory`, `invoice_factory`, `received_invoice_factory`, `invoice_line_factory`, `user_factory` | Factory classes bound to the test session |
| `tenant`, `other_tenant`, `super_admin`                      | Persisted, active accounts (password `PASSWORD`) |
| `fiscal_data`                                                | The fiscal data of `tenant` (needed to save invoices through the API) |
| `serial`                                                     | A `F-2026-` serial of `tenant` (needed to issue invoices) |
| `subject`, `invoice`                                         | One persisted instance, owned by `tenant` (`subject` is a recipient copy) |
| `session`, `client`                                          | Async SQLAlchemy session / anonymous HTTP test client |
| `tenant_client`, `super_admin_client`                        | HTTP test clients already logged in        |
| `mailer`                                                     | `InMemoryMailer`: e-mails sent during the test (`mailer.outbox`) |

`InvoiceFactory()` gives the invoice and its generated recipient the same (generated) owner and a
generated issuer snapshot; pass `owner=tenant` / `issuer=fiscal_data.as_issuer()` to pin them.
`ReceivedInvoiceFactory()` makes a received one (generated supplier, supplier's number, no serial);
pass `recipient=SubjectFactory.copy_of_account(fiscal_data)` to address it to a tenant.
The bcrypt work factor is lowered to 4 rounds in the test-suite.

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
