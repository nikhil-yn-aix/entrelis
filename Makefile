SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
T0 := $(shell date +%s.%N)

.PHONY: setup up down check fix slow

.env:
	cp .env.example .env
	for k in FALKORDB_PASSWORD FALKORDB_RW_PASSWORD FALKORDB_RO_PASSWORD; do \
		sed -i "s/^$$k=.*/$$k=$$(openssl rand -hex 24)/" .env; \
	done

users.acl: .env
	pw() { v=$$(grep -m1 "^$$1=" .env | cut -d= -f2-); : "$${v:?$$1 is empty in .env}"; printf '%s' "$$v"; }; \
	umask 022; \
	{ \
		printf 'user default on >%s ~* &* +@all\n' "$$(pw FALKORDB_PASSWORD)"; \
		printf 'user rw on >%s ~* &* +@all -@dangerous +info -graph.config\n' "$$(pw FALKORDB_RW_PASSWORD)"; \
		printf 'user ro on >%s ~* resetchannels +@read +@connection -@dangerous +info +graph.ro_query +graph.explain +graph.list +xread\n' "$$(pw FALKORDB_RO_PASSWORD)"; \
	} > $@

setup: .env
	uv sync
	git config core.hooksPath .githooks
	docker compose pull

up: users.acl
	docker compose up -d --wait

down:
	docker compose down

check: users.acl
	docker compose up -d --wait falkordb
	uv run ruff format --check
	uv run ruff check
	uv run pyright
	uv run lint-imports
	uv run pytest tests/unit tests/integration -n 4 --dist loadfile -q -p no:cacheprovider
	@awk -v s=$(T0) -v e=$$(date +%s.%N) 'BEGIN { printf "check passed in %.1f s\n", e - s }'

fix:
	uv run ruff format
	uv run ruff check --fix

slow: users.acl
	docker compose up -d --wait falkordb
	HYPOTHESIS_PROFILE=slow uv run pytest tests/unit tests/slow -q
