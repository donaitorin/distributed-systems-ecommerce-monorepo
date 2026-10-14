COMPOSE := docker compose
LONG_RUNNING := postgres redis-cart redis-cache kafka kafka-ui object-storage gateway

.PHONY: up down logs ps

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
