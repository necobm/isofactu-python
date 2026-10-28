# Every target runs inside the Docker containers: no Python or Node needed on the host.
.PHONY: help up dev down logs shell test test-backend test-frontend lint lint-backend lint-frontend \
        build migrate migration fixtures fixtures-purge

COMPOSE  = docker compose
BACKEND  = $(COMPOSE) exec backend
FRONTEND = $(COMPOSE) run --rm --no-deps frontend-build

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## Lifecycle -----------------------------------------------------------------
up:              ## Build & start everything -> http://localhost:8000
	$(COMPOSE) up --build

dev:             ## Same as `up`, plus the Vite dev server with HMR -> http://localhost:5173
	$(COMPOSE) --profile dev up --build

down:            ## Stop and remove containers
	$(COMPOSE) down

logs:            ## Follow backend logs
	$(COMPOSE) logs -f backend

shell:           ## Shell inside the backend container
	$(BACKEND) bash

## Quality (requires the stack to be up: `make up`) -----------------------------
test: test-backend test-frontend   ## Run all tests and checks

test-backend:    ## pytest (uses the <db>_test database, created automatically)
	$(BACKEND) pytest $(ARGS)

test-frontend:   ## TypeScript type-check
	$(FRONTEND) npm run typecheck

lint: lint-backend lint-frontend   ## Run all linters

lint-backend:    ## ruff
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .

lint-frontend:   ## eslint
	$(FRONTEND) npm run lint

## Database ---------------------------------------------------------------------
migrate:         ## Apply pending migrations
	$(BACKEND) alembic upgrade head

migration:       ## Autogenerate a migration from the models -> make migration MSG="add field"
	$(BACKEND) alembic revision --autogenerate -m "$(MSG)"

fixtures:        ## Generate fixture data (purges existing data) -> make fixtures ARGS="--invoices 50"
	$(BACKEND) python -m app.cli fixtures load --purge --yes --seed 42 $(ARGS)

fixtures-purge:  ## Remove all invoicing data
	$(BACKEND) python -m app.cli fixtures purge --yes

## Frontend ---------------------------------------------------------------------
build:           ## Rebuild the frontend into ./public
	$(FRONTEND) sh -c "npm ci --no-audit --no-fund && npm run build"
