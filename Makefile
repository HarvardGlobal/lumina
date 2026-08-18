SHELL := /bin/bash

.PHONY: setup start stop restart build logs health smoke-test versions clean test components check-components nix-check nix-update

setup:
	./scripts/with_nix.sh ./scripts/bootstrap.sh

start:
	./scripts/with_nix.sh ./scripts/start.sh

stop:
	./scripts/compose.sh down

restart: stop start

build:
	./scripts/with_nix.sh ./scripts/build.sh

components:
	./scripts/with_nix.sh python3 ./scripts/components.py sync

check-components:
	./scripts/with_nix.sh python3 ./scripts/components.py status

logs:
	./scripts/compose.sh logs -f

health:
	./scripts/healthcheck.sh

smoke-test:
	./scripts/smoke_test.sh

versions:
	./scripts/with_nix.sh python3 ./scripts/components.py status

test:
	@if command -v nix >/dev/null 2>&1; then \
		./scripts/with_nix.sh python3 -m pytest -q --cov=services/archive/app --cov=services/api --cov-report=term-missing --cov-fail-under=80 tests; \
	elif [[ -x .venv/bin/python ]]; then \
		PYTHONPATH=. .venv/bin/python -m pytest -q --cov=services/archive/app --cov=services/api --cov-report=term-missing --cov-fail-under=80 tests; \
	else \
		echo "Nix is not installed and .venv is missing. Install Nix or create .venv with the pinned requirements." >&2; exit 1; \
	fi

clean:
	./scripts/compose.sh down --remove-orphans

nix-update:
	nix flake update

nix-check:
	nix flake check
	nix develop --command python3 -c 'import fastapi, sqlalchemy, pyarrow, boto3; print("Core imports OK")'
