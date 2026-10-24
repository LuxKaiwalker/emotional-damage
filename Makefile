PY := backend/.venv/bin/python
PYTHON ?= python3.12

.PHONY: help install backend frontend dev test clean

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## create the backend venv and install both sides
	$(PYTHON) -m venv backend/.venv
	$(PY) -m pip install -q --upgrade pip
	cd backend && .venv/bin/python -m pip install -q -e '.[dev]'
	cd frontend && npm install

backend: ## run the API on :8000 with reload
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

frontend: ## run the vite dev server on :5173 (proxies /api and /ws to :8000)
	cd frontend && npm run dev

dev: ## run both; ctrl-c stops both
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

test: ## backend test suite
	cd backend && .venv/bin/python -m pytest -q

clean:
	rm -rf backend/.venv backend/.media backend/.pytest_cache frontend/node_modules frontend/dist
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
