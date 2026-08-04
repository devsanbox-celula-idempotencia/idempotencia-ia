.PHONY: install run test lint revision migrate \
        docker-build docker-up docker-down docker-logs docker-shell \
        prod-up prod-down prod-logs prod-deploy

# ---------------------------------------------------------------- desarrollo
install:
	pip install --only-binary=:all: -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check app tests scripts

revision:
	alembic revision --autogenerate -m "$(m)"

migrate:
	alembic upgrade head

# ---------------------------------------------------------------- docker (dev)
docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@echo "API en http://127.0.0.1:8000/docs"

# Levanta también Ollama y Redis en contenedores
docker-up-full:
	docker compose --profile ollama --profile redis up -d
	docker compose exec ollama ollama pull qwen2.5:3b

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

docker-shell:
	docker compose exec api bash

# ---------------------------------------------------------------- docker (prod)
prod-up:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f api

# Despliegue completo: código nuevo, imagen nueva, verificación
prod-deploy:
	git pull
	docker compose -f docker-compose.prod.yml up -d --build
	@sleep 5
	@curl -fsS http://127.0.0.1:8000/ready || (echo "FALLO: /ready no responde bien" && exit 1)
	@echo "Despliegue correcto"
