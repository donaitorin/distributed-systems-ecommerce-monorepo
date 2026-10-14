COMPOSE := docker compose
UV_BACKEND := uv --directory backend
LONG_RUNNING := postgres redis-cart redis-cache kafka kafka-ui object-storage gateway

.PHONY: up down logs ps test-backend lint-backend format-backend

up:
	@test -f .env || { echo ".env not found: run 'cp .env.example .env' first"; exit 1; }
	$(COMPOSE) up -d
	$(COMPOSE) up -d --wait $(LONG_RUNNING)

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

ps:
	$(COMPOSE) ps -a

test-backend:
	$(UV_BACKEND) run pytest

lint-backend:
	$(UV_BACKEND) run ruff check .
	$(UV_BACKEND) run ruff format --check .
	$(UV_BACKEND) run mypy libs

format-backend:
	$(UV_BACKEND) run ruff check --fix .
	$(UV_BACKEND) run ruff format .
