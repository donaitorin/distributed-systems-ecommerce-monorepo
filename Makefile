COMPOSE := docker compose
UV_BACKEND := uv --directory backend
LONG_RUNNING := postgres redis-cart redis-cache kafka kafka-ui object-storage gateway dev-auth auth catalog catalog-worker

.PHONY: up down logs ps dev-token seed test-backend test-backend-unit lint-backend format-backend

up:
	@test -f .env || { echo ".env not found: run 'cp .env.example .env' first"; exit 1; }
	$(COMPOSE) build catalog auth
	$(COMPOSE) up -d
	$(COMPOSE) up -d --wait $(LONG_RUNNING)

down:
	$(COMPOSE) down

dev-token:
	@$(COMPOSE) exec -T dev-auth python -m ecommerce_auth.dev_tokens token --role $(or $(ROLE),admin)

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
