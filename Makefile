.PHONY: up down logs backend install test status

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

install:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

status:
	@cat STATUS.md

test-upload:
	curl -X POST "http://localhost:8000/api/v1/upload" \
	  -H "accept: application/json" \
	  -F "file=@data/sample/alunos_exemplo.csv"
