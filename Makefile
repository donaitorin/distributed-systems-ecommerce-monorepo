COMPOSE := docker compose
export BUILDX_NO_DEFAULT_ATTESTATIONS := 1
UV_BACKEND := uv --directory backend
PNPM_FRONTEND := cd frontend && corepack pnpm
LONG_RUNNING := postgres redis-cart redis-cache kafka kafka-ui object-storage gateway auth auth-worker accounts accounts-worker cart cart-worker orders orders-worker payments payments-worker catalog catalog-worker store backoffice

FRONTEND_NODE_CHECK := check-node

.PHONY: check-node up down logs ps dev-token seed test test-backend test-backend-unit test-frontend lint lint-backend lint-frontend format-backend openapi check-openapi check-routes check-rate-limit check-dead-letters check-failure-scenarios check-not-found-csp dlq-inspect dlq-replay install-frontend storybook build-storybook test-storybook check-comments test-scripts

check-node:
	@python3 scripts/check_node_version.py

up:
	@test -f .env || { echo ".env not found: run 'cp .env.example .env' first"; exit 1; }
	$(COMPOSE) build catalog auth accounts cart orders payments store backoffice
	$(COMPOSE) up -d --no-build
	$(COMPOSE) up -d --no-build --wait $(LONG_RUNNING)

down:
	$(COMPOSE) down

dev-token:
	@ROLE=$(or $(ROLE),admin) ./scripts/dev-token.sh

seed:
	$(COMPOSE) run --build --rm --no-deps catalog python -m catalog.tools.seed --count $(or $(COUNT),200000)

DLQ_CLI := $(COMPOSE) run --rm --no-deps -T orders-worker python -m ecommerce_messaging.dlq_cli

dlq-inspect:
	@test -n "$(TOPIC)" || { echo "usage: make dlq-inspect TOPIC=orders.events.dlq [SHOW_PAYLOAD=1]"; exit 2; }
	@$(DLQ_CLI) inspect $(TOPIC) $(if $(SHOW_PAYLOAD),--show-payload)

dlq-replay:
	@test -n "$(TOPIC)" || { echo "usage: make dlq-replay TOPIC=orders.events.dlq (OFFSETS=\"0:12 3:4\" | ALL=1) [DRY_RUN=1]"; exit 2; }
	@$(DLQ_CLI) replay $(TOPIC) $(if $(OFFSETS),$(foreach location,$(OFFSETS),--offset $(location)),$(if $(ALL),--all)) $(if $(DRY_RUN),--dry-run)

check-dead-letters:
	./scripts/check_dead_letters.sh

check-failure-scenarios:
	./scripts/check_failure_scenarios.sh $(SCENARIO)

check-not-found-csp:
	python3 scripts/check_not_found_csp.py

logs:
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

ps:
	$(COMPOSE) ps -a

test: test-backend test-frontend

test-backend:
	$(UV_BACKEND) run pytest
	python3 scripts/check_package_coverage.py backend/coverage.xml

test-backend-unit:
	$(UV_BACKEND) run pytest -m "not integration"

lint: lint-backend lint-frontend

lint-backend:
	$(UV_BACKEND) run ruff check .
	$(UV_BACKEND) run ruff format --check .
	$(UV_BACKEND) run mypy libs services tools tests

openapi: $(FRONTEND_NODE_CHECK)
	$(UV_BACKEND) run python tools/dump_openapi.py ../frontend/packages/api-client/openapi
	$(PNPM_FRONTEND) --filter @ecommerce/api-client generate

check-openapi: $(FRONTEND_NODE_CHECK)
	@dir=$$(mktemp -d); trap 'rm -rf $$dir' EXIT; \
	$(UV_BACKEND) run python tools/dump_openapi.py $$dir && \
	diff -r $$dir frontend/packages/api-client/openapi && \
	$(PNPM_FRONTEND) --filter @ecommerce/api-client check-generated

check-routes:
	./scripts/check_gateway_routes.sh

check-rate-limit:
	./infra/gateway/tests/check_rate_limit.sh

install-frontend: $(FRONTEND_NODE_CHECK)
	$(PNPM_FRONTEND) install --frozen-lockfile

test-frontend: $(FRONTEND_NODE_CHECK)
	$(PNPM_FRONTEND) test

lint-frontend: $(FRONTEND_NODE_CHECK)
	$(PNPM_FRONTEND) lint
	$(PNPM_FRONTEND) typecheck

storybook: $(FRONTEND_NODE_CHECK)
	$(PNPM_FRONTEND) storybook

build-storybook: $(FRONTEND_NODE_CHECK)
	$(PNPM_FRONTEND) build-storybook

test-storybook: build-storybook
	$(PNPM_FRONTEND) test-storybook

format-backend:
	$(UV_BACKEND) run ruff check --fix .
	$(UV_BACKEND) run ruff format .

check-comments: $(FRONTEND_NODE_CHECK)
	python3 scripts/check_comments.py

test-scripts: $(FRONTEND_NODE_CHECK)
	PYTHONPATH=scripts uv run --no-project --with pytest python -m pytest scripts/tests -q -p no:cacheprovider
