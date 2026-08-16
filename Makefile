SHELL := /bin/bash

.PHONY: setup start stop restart build logs health smoke-test versions clean test components check-components nix-update

setup:
	./scripts/with_nix.sh ./scripts/bootstrap.sh

start:
	./scripts/with_nix.sh ./scripts/start.sh

stop:
	docker compose down

restart: stop start

build:
	./scripts/with_nix.sh ./scripts/build.sh

components:
	./scripts/with_nix.sh python3 ./scripts/components.py sync

check-components:
	./scripts/with_nix.sh python3 ./scripts/components.py status

logs:
	docker compose logs -f

health:
	./scripts/healthcheck.sh

smoke-test:
	./scripts/smoke_test.sh

versions:
	./scripts/with_nix.sh python3 ./scripts/components.py status

test:
	PYTHONPATH=. pytest -q tests

clean:
	docker compose down --remove-orphans

nix-update:
	nix flake update
