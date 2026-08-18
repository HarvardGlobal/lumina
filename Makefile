SHELL := /bin/bash

.PHONY: setup start stop restart build logs health smoke-test versions clean test components check-components nix-update

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
	@if [[ -x .venv/bin/python ]]; then \
		PYTHONPATH=. .venv/bin/python -m pytest -q --cov=services/archive/app --cov=services/api --cov-report=term-missing --cov-fail-under=80 tests; \
	else \
		./scripts/with_nix.sh python3 -m pytest -q --cov=services/archive/app --cov=services/api --cov-report=term-missing --cov-fail-under=80 tests; \
	fi

clean:
	./scripts/compose.sh down --remove-orphans

nix-update:
	nix flake update
