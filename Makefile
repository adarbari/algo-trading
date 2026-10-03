# Every CI step is a make target, so "it passed locally" means "it will pass in CI".
PY ?= .venv/bin/python
BIN = $(dir $(PY))
# Golden datasets live in their own fixture store, never in the production data store.
GOLDEN_URL ?= file://datasets/golden/store


.PHONY: install lock-check lint format typecheck arch layout ownership ownership-update dupes dupes-update filelen unit property integration e2e test \
        evaluate baseline datasets-verify datasets-build golden-store check nightly features-doc web-install web-check web-visual

UV ?= uv

install:         ## library + every app + dev tools into .venv, exactly as locked
	$(UV) sync --all-packages --locked
	$(BIN)pre-commit install

lock-check:      ## uv.lock matches every pyproject.toml in the workspace
	$(UV) lock --check

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

layout:          ## directory layout fitness tests + early warning: folders at 8+ of 10 modules
	$(PY) -m pytest -q tests/architecture/test_layout.py tests/architecture/test_layout_buckets.py
	$(PY) scripts/layout_report.py

ownership:       ## every responsibility done only by its owner (ADR 0019); ratchet only shrinks
	$(PY) scripts/check_ownership.py --summary

ownership-update: ## after fixing violations: shrink architecture/known_violations.toml
	$(PY) scripts/check_ownership.py --update

dupes:           ## no new copy-pasted code in src/ and apps/ (pylint duplicate-code ratchet)
	$(PY) scripts/check_dupes.py

dupes-update:    ## after removing duplicates: lower architecture/dupes_baseline.txt
	$(PY) scripts/check_dupes.py --update

features-doc:    ## regenerate the feature catalogue docs/data/features.md from the registry
	$(PY) scripts/features_doc.py

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

datasets-verify: ## committed golden CSVs match their checksums
	$(BIN)algotrade-ingest golden verify

datasets-build:  ## regenerate golden CSVs from the catalogue (then review + commit)
	$(BIN)algotrade-ingest golden build

golden-store:    ## (re)load the golden CSVs into the fixture store
	rm -rf datasets/golden/store
	ALGOTRADE_DATA_URL=$(GOLDEN_URL) $(BIN)algotrade-ingest golden load

evaluate: golden-store  ## strategy scorecard vs committed baseline
	$(BIN)algotrade-backtest --data-url $(GOLDEN_URL) evaluate --report scorecard.md

baseline: golden-store  ## accept current results as the new baseline (review the diff!)
	$(BIN)algotrade-backtest --data-url $(GOLDEN_URL) evaluate --update-baseline

# ----------------------------------------------------------------------------- web (apps/web, ADR 0025)
# Node 24 + npm (npm workspaces: apps/web and its design-system package); lockfile apps/web/package-lock.json.
WEB = apps/web
NPM ?= npm

$(WEB)/node_modules/.package-lock.json: $(WEB)/package-lock.json
	cd $(WEB) && $(NPM) ci --no-fund --no-audit

web-install: $(WEB)/node_modules/.package-lock.json  ## web deps + the Playwright browser
	cd $(WEB) && npx playwright install chromium

web-check: $(WEB)/node_modules/.package-lock.json  ## generated files fresh, ds:check, lint, types, unit, build, storybook, e2e
	cd $(WEB) && $(NPM) run check

web-visual:      ## screenshots + axe over every story, in the CI Linux image (needs Docker)
	cd $(WEB) && $(NPM) run visual:docker

check: lock-check lint typecheck arch layout ownership dupes filelen datasets-verify test evaluate web-check

nightly:
	HYPOTHESIS_PROFILE=nightly $(PY) -m pytest tests/property
	$(MAKE) evaluate
