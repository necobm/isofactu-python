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

Partially there, with known gaps:

- [ ] **Fiscal data** — cannot be overridden for a single invoice yet.
- [ ] **Clients** — cannot be created inline from the invoice form yet; suppliers (for received
      invoices) are not modelled.
- [ ] **Drafts** — must already satisfy the same content rules as issued invoices (the spec allows
      incomplete drafts) and cannot be deleted.
- [ ] **Dashboard** — the layout exists but every figure and chart is static sample data.

### Next: complete the MVP

1. **Per-invoice issuer** — allow editing the fiscal data for a single invoice only.
2. **Suppliers** — a supplier directory for received invoices; create a client inline from the
   invoice form.
3. **Draft rules** — let drafts be saved incomplete, enforce required fields only when issuing,
   and allow deleting drafts.
4. **Received invoices (expenses)** — record supplier invoices with their concepts, VAT and IRPF.
5. **Taxes**
   - VAT to pay for a date range, with presets (*this month*, *current quarter*, *current year*).
   - Pending IRPF from income and IRPF already withheld/advanced, by quarter or fiscal year.
6. **Live dashboard** — replace the sample data with real income, expenses and tax figures.

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

This starts four things:

1. `db` — PostgreSQL 17 (exposed on `127.0.0.1:5433`).
2. `mailpit` — catches every e-mail the app sends (activation links). Web UI on http://localhost:8025.
3. `frontend-build` — one-shot Node container that compiles the React app into `./public` and exits.
4. `backend` — FastAPI server: applies Alembic migrations, creates the first `SUPER_ADMIN`
   account, then serves the API **and** the SPA.

Open http://localhost:8000 for the app and http://localhost:8000/api/docs for the API documentation.

Log in with the `SUPER_ADMIN` account from `.env` (`admin@isofactu.local` / `admin1234` by default)
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

If you prefer a local virtualenv, the root `.env` already points `DATABASE_URL` at the Dockerised
database:

```bash
docker compose up -d db mailpit
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.cli users create-super-admin --email admin@isofactu.local   # prompts for a password
uvicorn app.main:app --reload       # http://localhost:8000
```

The root `.env` points `SMTP_HOST` at the Mailpit container's published port. With `SMTP_HOST`
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
| GET    | `/api/invoice`                          | ADMIN        | Collection of invoices (`?state=&limit=&offset=`) |
| GET    | `/api/invoice/{id}`                     | ADMIN        | Invoice detail                                 |
| POST   | `/api/invoice`                          | ADMIN        | Create an invoice (draft or issued) for `clientId` with its lines (`409` until the fiscal data is set) |
| PUT    | `/api/invoice/{id}`                     | ADMIN        | Replace a draft invoice (optionally re-pointing it at a `clientId`), or issue it |

Example — `GET /api/invoice`:

```json
{
  "items": [
    {
      "id": 1,
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
- Drafts and issued invoices obey the same content rules: at least one line, a non-blank
  `description` on every line and a positive subtotal. Anything else is a `422`.
- Line amounts: `subtotal = quantity × unitPrice`, `total = subtotal + taxAmount` (VAT). The
  optional IRPF withholding applies to the whole invoice: `retentionAmount = subtotal × retentionRate`
  is deducted from the invoice `total`.
- Monetary amounts are JSON numbers with at most two decimals (`120.98`); the backend validates and
  computes them with `Decimal`, so nothing is lost in arithmetic. Inputs also accept numeric strings.
- Line amounts use scale 2 with **half-up rounding** (`99.99 × 21 % = 20.9979 → 21.00`).

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
├── .env                       # Shared defaults (Postgres, ports, SECRET_KEY, SMTP, first SUPER_ADMIN)
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
│   │   ├── geo/               # Geo module: countries, provinces, cities (+ data/, see scripts/)
│   │   ├── invoicing/         # Invoicing module (every row belongs to a tenant)
│   │   │   ├── models.py      #   FiscalData, Serial, Subject (recipient copy), Invoice, InvoiceLine
│   │   │   ├── value_objects.py  # InvoiceNumber, IdentificationDocument, Address, Issuer (composites)
│   │   │   ├── document_type.py  # CIF | NIF | OTHER
│   │   │   ├── invoice_state.py  # DRAFT | ISSUED
│   │   │   ├── payment_method.py # TRANSFER | CASH | CARD | DIRECT_DEBIT
│   │   │   ├── money.py       #   bcmath-compatible decimal helpers
│   │   │   ├── spanish_ids.py #   NIF / NIE / CIF validation
│   │   │   ├── schemas.py     #   Pydantic models = API contract
│   │   │   ├── repository.py  #   Data access, scoped to one tenant
│   │   │   └── router.py      #   /api/fiscal-data, /api/serial, /api/invoice, /api/subject
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
│   │   ├── TenantApp.tsx      # ADMIN shell: dashboard, invoices...
│   │   ├── AdminApp.tsx       # SUPER_ADMIN shell: accounts, settings
│   │   ├── api/               # Typed API client (api, auth, admin) + contract types
│   │   ├── pages/             # Login, ActivateAccount, Dashboard, Invoices, InvoiceForm, Clients, ClientForm, settings pages, admin/
│   │   ├── components/        # TopNav, forms, SearchSelect (react-select), dashboard widgets, invoice form / table, admin/
│   │   └── lib/               # AuthProvider + useAuth, tiny router, formatting, useApi hook
│   └── vite.config.ts         # Builds to ../public, proxies /api in dev
└── public/                    # Built frontend assets (generated, git-ignored)
```

## Key concepts

- **User / account** — someone who can log in. `ADMIN` users are tenants: every subject and invoice has one as `owner`. `SUPER_ADMIN` users only manage accounts.
- **FiscalData** — the tenant's own identity (company name, CIF/NIF, address); one per account, edited in *Ajustes*.
- **Serial** — a numbering series of a tenant (prefix, initial number, suffix, validity period). Locked once an issued invoice uses it.
- **Client** — an entry of the tenant's client directory (name, NIF/CIF, address). Independent from invoices.
- **Subject** — an invoice's own copy of its recipient, taken from a client when the invoice is created.
- **Invoice** — carries a copy of the issuer's fiscal data (**Issuer** value object), links a recipient, has a date, an invoice number, a state (`DRAFT` → `ISSUED`) and an optional IRPF retention rate, and contains one or more lines.
- **InvoiceLine** — a concept with description, quantity, unit price and VAT rate. Amounts are computed with fixed-point decimals.
- **InvoiceNumber** — value object: prefix + sequential number + suffix (`F-2026-42`), copied from the serial at issue time; unassigned while the invoice is a draft.

## Fixtures

Test/demo data is defined **once** as [factory_boy](https://factoryboy.readthedocs.io/) factories
in `backend/app/fixtures/factories.py` (with Faker's `es_ES` locale: valid NIF/CIF numbers, Spanish
names and addresses) and consumed from two places:

**1. Manually, through the management CLI** (inside the backend container) — to fill a
development database. Everything generated belongs to a demo tenant, `demo@isofactu.local`
(password `demo1234`), created on first use — with generated fiscal data and a `F-<year>-`
serial — so that you can log in and browse the data. Issued invoices are numbered correlatively
from that serial in issue-date order:

```bash
make fixtures                                   # purge + 6 clients, 20 invoices, seed 42
make fixtures ARGS="--invoices 50 --clients 10" # same, with options
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
| `client_factory`, `subject_factory`, `invoice_factory`, `invoice_line_factory`, `user_factory` | Factory classes bound to the test session |
| `tenant`, `other_tenant`, `super_admin`                      | Persisted, active accounts (password `PASSWORD`) |
| `fiscal_data`                                                | The fiscal data of `tenant` (needed to save invoices through the API) |
| `serial`                                                     | A `F-2026-` serial of `tenant` (needed to issue invoices) |
| `subject`, `invoice`                                         | One persisted instance, owned by `tenant` (`subject` is a recipient copy) |
| `session`, `client`                                          | Async SQLAlchemy session / anonymous HTTP test client |
| `tenant_client`, `super_admin_client`                        | HTTP test clients already logged in        |
| `mailer`                                                     | `InMemoryMailer`: e-mails sent during the test (`mailer.outbox`) |

`InvoiceFactory()` gives the invoice and its generated recipient the same (generated) owner and a
generated issuer snapshot; pass `owner=tenant` / `issuer=fiscal_data.as_issuer()` to pin them.
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
