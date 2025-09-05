# Makefile
VENV ?= backend/venv
BIN := $(VENV)/bin
PYTHON := $(BIN)/python
PIP := $(BIN)/pip
RUFF := $(BIN)/ruff
MYPY := $(BIN)/mypy
PRECOMMIT := $(BIN)/pre-commit
PYTEST := $(BIN)/pytest

.PHONY: bootstrap lint format type test check precommit

bootstrap:
	$(PYTHON) -m pip install -U pip
	$(PIP) install -U ruff mypy pre-commit pytest

format:
	$(RUFF) format ortho_processing

lint:
	$(RUFF) check ortho_processing

type:
	$(MYPY) ortho_processing

test:
	$(PYTEST) -q ortho_processing

check: format lint type test

precommit:
	$(PRECOMMIT) install
