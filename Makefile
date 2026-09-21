.PHONY: bootstrap check-python fmt lint typecheck test test-cov security up down down-v ps logs-db doctor-db wait-db migrate rollback verify worker

VENV := .venv
PYTHON := $(VENV)/bin/python
COMPOSE := docker compose -p job-processor-service
DB_CONTAINER := job-processor-postgres
DB_PORT ?= 5432

export DATABASE_URL ?= postgresql+psycopg://postgres:postgres@localhost:$(DB_PORT)/job_processor
export JOB_PROCESSOR_DB_PORT := $(DB_PORT)

bootstrap:
	python3.12 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]

check-python:
	$(PYTHON) -c 'import sys; raise SystemExit(0 if (sys.version_info.major, sys.version_info.minor)==(3,12) else 1)'

fmt:
	$(PYTHON) -m black .

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src

migrate:
	$(PYTHON) -m alembic upgrade head

rollback:
	$(PYTHON) -m alembic downgrade -1

worker:
	DATABASE_URL="$(DATABASE_URL)" $(PYTHON) -m job_processor_service.worker_main

test:
	$(PYTHON) -m pytest -q

test-cov:
	$(PYTHON) -m pytest --cov=src --cov-report=term --cov-fail-under=90

security:
	$(PYTHON) -m bandit -r src -x tests -lll -q
	$(VENV)/bin/trufflehog filesystem . --no-update --fail --exclude-paths .trufflehog-exclude-paths.txt

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

ps:
	$(COMPOSE) ps

logs-db:
	$(COMPOSE) logs -f postgres

doctor-db:
	@echo "== Port 5432 owner =="
	lsof -i :5432 || true
	@echo "== Running postgres:16 containers =="
	docker ps --filter ancestor=postgres:16
	@echo "== This repo container ($(DB_CONTAINER)) =="
	docker ps --filter name=$(DB_CONTAINER)

wait-db:
	@command -v docker >/dev/null || { echo "docker not found on PATH"; exit 1; }
	@container="$(DB_CONTAINER)"; \
	compose_cmd="$(COMPOSE)"; \
	db_port="$(DB_PORT)"; \
	diag() { \
		echo "== compose ps =="; \
		$$compose_cmd ps; \
		echo "== container ps ($(DB_CONTAINER)) =="; \
		docker ps --filter name="$$container"; \
		health=$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$$container" 2>/dev/null || echo "missing"); \
		echo "== health status == $$health"; \
	}; \
	if ! docker inspect "$$container" >/dev/null 2>&1; then \
		echo "Container '$$container' does not exist"; \
		diag; \
		exit 1; \
	fi; \
	max=30; i=1; \
	while [ $$i -le $$max ]; do \
		health=$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$$container" 2>/dev/null || echo "missing"); \
		if [ "$$health" = "healthy" ]; then \
			if docker exec "$$container" pg_isready -U postgres -d job_processor >/dev/null 2>&1; then \
				echo "Container '$$container' is healthy and accepting connections on localhost:$$db_port"; \
				exit 0; \
			fi; \
			echo "Container '$$container' is healthy but not yet accepting connections on localhost:$$db_port ($$i/$$max)"; \
		elif [ "$$health" = "unhealthy" ]; then \
			echo "Container '$$container' is unhealthy"; \
			diag; \
			exit 1; \
		else \
			echo "Waiting for container '$$container' health=healthy (current=$$health) ($$i/$$max)"; \
		fi; \
		sleep 1; \
		i=$$((i+1)); \
	done; \
	echo "Timed out waiting for container '$$container' to become healthy after $$max seconds"; \
	diag; \
	exit 1

verify:
	$(MAKE) up
	$(MAKE) wait-db
	$(MAKE) migrate
	$(MAKE) check-python
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test
	$(MAKE) test-cov
	$(MAKE) security
	$(COMPOSE) ps