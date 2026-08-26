# Task runner for the planner.
#
# Python has no package.json. `[project.scripts]` in pyproject declares installed
# console entry points, not tasks; hatch and PDM offer script tables but only if you
# use their build backend, and tox/nox are for version matrices rather than everyday
# commands. A Makefile is what most Python projects settle on, needs nothing installed,
# and every developer can already read it.
#
# Run `make` on its own for the list.

SHELL := /bin/bash
.DEFAULT_GOAL := help

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
VAULT   := $(abspath ..)
DSN     ?= postgresql://$(USER)@127.0.0.1:55432/planner
COMPOSE := docker compose

# Passed through to the image build so a bind-mounted vault keeps host ownership on
# Linux. Harmless on macOS, where Docker Desktop maps it anyway.
export UID := $(shell id -u)
export GID := $(shell id -g)

.PHONY: help
help:  ## Show this list
	@echo "planner — run from .tooling/"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  vault: $(VAULT)"

# --- local development ---------------------------------------------------------------

$(VENV)/pyvenv.cfg:
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip

.PHONY: install
install: $(VENV)/pyvenv.cfg  ## Create the venv and install everything
	$(PIP) install -q -e ".[dev,api,mcp,postgres,docs]"
	@echo "installed"

.PHONY: test
test: install  ## Run the suite with coverage (fails under 98%)
	$(PYTEST)

.PHONY: quick
quick: install  ## Run the suite without coverage, for a tight loop
	$(PYTEST) --no-cov -q

.PHONY: cov
cov: test  ## Run the suite and open the coverage report
	open htmlcov/index.html

.PHONY: run
run: install  ## Serve the API locally against the host Postgres
	PLANNER_VAULT=$(VAULT) PLANNER_DSN=$(DSN) \
	  $(VENV)/bin/uvicorn planner.api:app --reload --port 8000

.PHONY: mcp
mcp: install  ## Run the MCP server over stdio
	PLANNER_VAULT=$(VAULT) PLANNER_DSN=$(DSN) $(PY) -m planner.mcp

.PHONY: docs
docs: install  ## Regenerate the generated doc sections and the API reference
	$(PY) -m planner.docsgen --write
	$(VENV)/bin/pdoc planner -o docs/api --no-show-source

.PHONY: docs-check
docs-check: install  ## Fail if the docs have fallen behind the code
	$(PY) -m planner.docsgen --check

# --- the vault -----------------------------------------------------------------------

.PHONY: demo
demo: install  ## Fill the vault with throwaway notes
	$(PY) demo/demo.py load

.PHONY: demo-clear
demo-clear: install  ## Remove them again
	$(PY) demo/demo.py clear

# --- containers ----------------------------------------------------------------------

.PHONY: build
build:  ## Build the API image
	$(COMPOSE) build

.PHONY: up
up:  ## Start the API and Postgres in the background
	$(COMPOSE) up -d --build
	@echo "api    http://127.0.0.1:8000/docs"
	@echo "vault  $(VAULT) (bind-mounted read-write)"

.PHONY: down
down:  ## Stop them, keeping the audit database
	$(COMPOSE) down

.PHONY: logs
logs:  ## Follow the API log
	$(COMPOSE) logs -f api

.PHONY: ps
ps:  ## Show container status
	$(COMPOSE) ps

.PHONY: shell
shell:  ## A shell inside the API container
	$(COMPOSE) exec api bash

.PHONY: db-shell
db-shell:  ## psql against the audit database
	$(COMPOSE) exec db psql -U planner -d planner

.PHONY: audit
audit:  ## The most recent operations from the audit log
	$(COMPOSE) exec db psql -U planner -d planner -c \
	  "SELECT id, status, actor, request_id, summary, finished_at \
	   FROM planner_operations ORDER BY id DESC LIMIT 20;"

.PHONY: test-docker
test-docker:  ## Run the suite in a container against the compose Postgres
	$(COMPOSE) --profile tools run --rm test

.PHONY: clean
clean:  ## Stop everything and delete the audit database volume
	$(COMPOSE) down -v
	@echo "audit history deleted; the vault is untouched"

.PHONY: clean-local
clean-local:  ## Remove the venv and generated output
	rm -rf $(VENV) htmlcov .pytest_cache .coverage docs/api
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
