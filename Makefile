COMPOSE := docker compose
export BUILDX_NO_DEFAULT_ATTESTATIONS := 1
UV_BACKEND := uv --directory backend
PNPM_FRONTEND := cd frontend && corepack pnpm
LONG_RUNNING := postgres redis-cart redis-cache kafka kafka-ui object-storage gateway auth auth-worker accounts accounts-worker cart cart-worker orders orders-worker catalog catalog-worker store backoffice

.PHONY: up down logs ps dev-token seed test test-backend test-backend-unit test-frontend lint lint-backend lint-frontend format-backend openapi check-openapi check-routes check-rate-limit install-frontend storybook build-storybook test-storybook check-comments test-scripts

up:
	@test -f .env || { echo ".env not found: run 'cp .env.example .env' first"; exit 1; }
	$(COMPOSE) build catalog auth accounts cart orders store backoffice
	$(COMPOSE) up -d --no-build
	$(COMPOSE) up -d --no-build --wait $(LONG_RUNNING)

down:
	$(COMPOSE) down

dev-token:
	@ROLE=$(or $(ROLE),admin) ./scripts/dev-token.sh

seed:
	$(COMPOSE) run --build --rm --no-deps catalog python -m catalog.tools.seed --count $(or $(COUNT),200000)

logs:
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

ps:
	$(COMPOSE) ps -a

test: test-backend test-frontend

test-backend:
	$(UV_BACKEND) run pytest

test-backend-unit:
	$(UV_BACKEND) run pytest -m "not integration"

lint: lint-backend lint-frontend

lint-backend:
	$(UV_BACKEND) run ruff check .
	$(UV_BACKEND) run ruff format --check .
	$(UV_BACKEND) run mypy libs services tools

openapi:
	$(UV_BACKEND) run python tools/dump_openapi.py ../frontend/packages/api-client/openapi
	$(PNPM_FRONTEND) --filter @ecommerce/api-client generate

check-openapi:
	@dir=$$(mktemp -d); trap 'rm -rf $$dir' EXIT; \
	$(UV_BACKEND) run python tools/dump_openapi.py $$dir && \
	diff -r $$dir frontend/packages/api-client/openapi && \
	$(PNPM_FRONTEND) --filter @ecommerce/api-client check-generated

check-routes:
	./scripts/check_gateway_routes.sh

check-rate-limit:
	./infra/gateway/tests/check_rate_limit.sh

install-frontend:
	$(PNPM_FRONTEND) install --frozen-lockfile

test-frontend:
	$(PNPM_FRONTEND) test

lint-frontend:
	$(PNPM_FRONTEND) lint
	$(PNPM_FRONTEND) typecheck

storybook:
	$(PNPM_FRONTEND) storybook

build-storybook:
	$(PNPM_FRONTEND) build-storybook

test-storybook: build-storybook
	$(PNPM_FRONTEND) test-storybook

format-backend:
	$(UV_BACKEND) run ruff check --fix .
	$(UV_BACKEND) run ruff format .

check-comments:
	python3 scripts/check_comments.py

test-scripts:
	PYTHONPATH=scripts uv run --no-project --with pytest python -m pytest scripts/tests -q -p no:cacheprovider
