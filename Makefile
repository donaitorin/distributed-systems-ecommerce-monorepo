COMPOSE := docker compose
export BUILDX_NO_DEFAULT_ATTESTATIONS := 1
UV_BACKEND := uv --directory backend
LONG_RUNNING := postgres redis-cart redis-cache kafka kafka-ui object-storage gateway auth auth-worker accounts accounts-worker catalog catalog-worker

.PHONY: up down logs ps dev-token seed test-backend test-backend-unit lint-backend format-backend check-comments

up:
	@test -f .env || { echo ".env not found: run 'cp .env.example .env' first"; exit 1; }
	$(COMPOSE) build catalog auth accounts
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

test-backend:
	$(UV_BACKEND) run pytest

test-backend-unit:
	$(UV_BACKEND) run pytest -m "not integration"

lint-backend:
	$(UV_BACKEND) run ruff check .
	$(UV_BACKEND) run ruff format --check .
	$(UV_BACKEND) run mypy libs services

format-backend:
	$(UV_BACKEND) run ruff check --fix .
	$(UV_BACKEND) run ruff format .

check-comments:
	python3 scripts/check_comments.py
