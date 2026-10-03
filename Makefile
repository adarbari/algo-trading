# Every CI step is a make target, so "it passed locally" means "it will pass in CI".
PY ?= .venv/bin/python
BIN = $(dir $(PY))

.PHONY: install lint format typecheck arch filelen unit property integration e2e test \
        evaluate baseline datasets-verify datasets-build check nightly

install:
	python3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	$(BIN)pre-commit install

lint:
	$(BIN)ruff check src apps tests scripts
	$(BIN)ruff format --check src apps tests scripts

format:
	$(BIN)ruff check --fix src apps tests scripts
	$(BIN)ruff format src apps tests scripts

typecheck:
	$(BIN)mypy

arch:            ## dependency boundaries between layers
	$(BIN)lint-imports

filelen:         ## no file over 1000 lines
	$(PY) scripts/check_file_length.py

unit:
	$(PY) -m pytest tests/unit tests/architecture tests/contract tests/apps

property:
	$(PY) -m pytest tests/property

integration:
	$(PY) -m pytest tests/integration

e2e:
	$(PY) -m pytest tests/e2e

test:            ## everything, with the coverage gate
	$(PY) -m pytest --cov --cov-report=term --cov-report=xml

datasets-verify:
	$(BIN)algotrade-backtest datasets verify

datasets-build:
	$(BIN)algotrade-backtest datasets build

evaluate:        ## strategy scorecard vs committed baseline
	$(BIN)algotrade-backtest evaluate --report scorecard.md

baseline:        ## accept current results as the new baseline (review the diff!)
	$(BIN)algotrade-backtest evaluate --update-baseline

check: lint typecheck arch filelen datasets-verify test evaluate

nightly:
	HYPOTHESIS_PROFILE=nightly $(PY) -m pytest tests/property
	$(BIN)algotrade-backtest evaluate --report scorecard.md
