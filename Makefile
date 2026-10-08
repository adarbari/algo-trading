# Every CI step is a make target, so "it passed locally" means "it will pass in CI".
PY ?= .venv/bin/python
BIN = $(dir $(PY))
# Golden datasets live in their own fixture store, never in the production data store.
GOLDEN_URL ?= file://datasets/golden/store


.PHONY: test-shard coverage-combine check-gates changed install no-shared-venv doctor status lock-check lint format typecheck arch layout ownership ownership-update dupes dupes-update rest-allowlist rest-allowlist-update filelen numbering unit property integration e2e test \
        evaluate regime-scorecard baseline datasets-verify datasets-build golden-store check nightly features-doc web-install web-check web-real web-visual web-build

UV ?= uv
WORKERS ?= auto
# WEB_WORKERS=N caps vitest workers in web-check / check (vitest reads VITEST_MAX_WORKERS, = --maxWorkers); empty = vitest default
WEB_WORKERS ?=
BASE ?= origin/main

doctor:          ## is this machine ready? (uv, Node 24, Docker, gh, venv, web deps, disk, merged-PR worktrees, .env keys, store); prints the fix for each failure
	@$(if $(wildcard $(PY)),$(PY),python3) scripts/doctor.py

status:          ## PRs + CI, running ingest jobs, last nightly, store latest session, dev servers (~15 lines, read-only)
	@$(if $(wildcard $(PY)),$(PY),python3) scripts/status.py

install: no-shared-venv  ## library + every app + dev tools into .venv, exactly as locked
	$(UV) sync --all-packages --locked
	$(BIN)pre-commit install

# A worktree's .venv links to the main checkout's, which launchd's nightly and the API run:
# syncing through the link points that venv at this worktree's unmerged code.
no-shared-venv:  ## refuse to sync when .venv is a link (a worktree): it would rewrite the main checkout's venv
	@if [ -L .venv ]; then \
	  echo "refusing: .venv links to the main checkout's venv; syncing here points it (and the nightly and API that run it) at this worktree's code." >&2; \
	  echo "  in a worktree, run the code through PYTHONPATH: source worktree.env (scripts/worktree.sh writes it)" >&2; \
	  echo "  dependency changes: uv lock here; make install in the main checkout after the PR merges" >&2; \
	  exit 1; \
	fi

lock-check:      ## uv.lock matches every pyproject.toml in the workspace
	$(UV) lock --check

lint:
	$(BIN)ruff check src libs apps tests scripts
	$(BIN)ruff format --check src libs apps tests scripts

format:
	$(BIN)ruff check --fix src libs apps tests scripts
	$(BIN)ruff format src libs apps tests scripts

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

rest-allowlist:  ## REST GET routes only shrink (ADR 0037): architecture/rest_allowlist.toml vs its committed count
	$(PY) scripts/check_rest_allowlist.py

rest-allowlist-update: ## after retiring GET routes (removing their entries): lower the committed count
	$(PY) scripts/check_rest_allowlist.py --update

features-doc:    ## regenerate docs/data/features.md (catalogue) and docs/data/field-guide.md (field guide)
	$(PY) scripts/features_doc.py

filelen:         ## no file over 1000 lines
	$(PY) scripts/check_file_length.py

numbering:       ## ADR numbers not taken on origin/main; web rule numbers 1..n and cited ones exist
	$(PY) scripts/check_numbering.py

unit:
	$(PY) -m pytest tests/unit tests/architecture tests/contract tests/libs tests/apps tests/scripts

property:
	$(PY) -m pytest tests/property

integration:
	$(PY) -m pytest tests/integration

e2e:
	$(PY) -m pytest tests/e2e

changed:         ## narrow first check: mirrored tests of files changed vs origin/main (BASE=...), then the fast gates; `make check` still gates
	@paths="$$($(PY) scripts/changed_tests.py $(BASE))"; \
	if [ -n "$$paths" ]; then $(PY) -m pytest -q -x --no-header --tb=short $$paths; else echo "no covering tests changed"; fi
	@$(PY) scripts/changed_web.py $(BASE)
	@$(MAKE) --no-print-directory arch layout ownership

test:            ## everything, with the coverage gate, one worker per CPU (WORKERS=0 runs serially)
	$(PY) -m pytest -n $(WORKERS) --cov --cov-report=term --cov-report=xml

# CI runs the suite as three parallel shards (docs/ci.md "Pipeline"); together they are `make test`.
# A fitness test (tests/architecture/pipeline) checks the shards cover every tests/ folder.
TEST_SHARDS = unit-a unit-b apps rest
# tests/unit split in two by subfolder (the #286 run: unit 5.6 min, apps 3.3, rest 1.7)
TEST_SHARD_unit-a = tests/unit/features tests/unit/quant tests/unit/engines tests/unit/strategies tests/unit/analytics
TEST_SHARD_unit-b = tests/unit/services tests/unit/config tests/unit/data tests/unit/core tests/unit/storage
TEST_SHARD_apps = tests/apps tests/libs tests/contract tests/architecture
# rest: few tests, the slow ones
TEST_SHARD_rest = tests/property tests/integration tests/e2e tests/scripts tests/reconciliation

test-shard:      ## one CI shard (SHARD=unit-a|unit-b|apps|rest): its coverage data in .coverage.<shard>, no gate (coverage-combine gates)
	@test -n "$(TEST_SHARD_$(SHARD))" || { echo "SHARD must be one of: $(TEST_SHARDS)" >&2; exit 2; }
	COVERAGE_FILE=.coverage.$(SHARD) $(PY) -m pytest -n $(WORKERS) --cov --cov-report= --cov-fail-under=0 $(TEST_SHARD_$(SHARD))

coverage-combine: ## the 90% coverage gate over the shards' data files (.coverage.*), then coverage.xml
	$(BIN)coverage combine --keep $(wildcard .coverage.*)
	$(BIN)coverage report --fail-under=90
	$(BIN)coverage xml

perf:            ## strict timing budgets (the `perf` tests), serially; run on an idle machine
	$(PY) -m pytest -p no:xdist -m perf

datasets-verify: ## committed golden CSVs match their checksums
	$(BIN)algotrade-ingest golden verify

datasets-build:  ## regenerate golden CSVs from the catalogue (then review + commit)
	$(BIN)algotrade-ingest golden build

golden-store:    ## (re)load the golden CSVs into the fixture store
	rm -rf datasets/golden/store
	ALGOTRADE_DATA_URL=$(GOLDEN_URL) $(BIN)algotrade-ingest golden load

evaluate: golden-store  ## strategy scorecard vs committed baseline, then the regime scorecard section
	$(BIN)algotrade-backtest --data-url $(GOLDEN_URL) evaluate --report scorecard.md
	$(BIN)algotrade-backtest --data-url $(GOLDEN_URL) regime-scorecard

regime-scorecard:  ## the regime episode scorecard over the configured store (ALGOTRADE_DATA_URL)
	$(BIN)algotrade-backtest regime-scorecard --report regime-scorecard.txt

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

web-check: $(WEB)/node_modules/.package-lock.json  ## generated files fresh, ds:check, lint, types, unit, build, storybook, e2e (WEB_WORKERS=N caps vitest)
	cd $(WEB) && $(if $(WEB_WORKERS),VITEST_MAX_WORKERS=$(WEB_WORKERS) )$(NPM) run check

web-real: $(WEB)/node_modules/.package-lock.json golden-store  ## real-app smoke: Vite dev + the real API, empty and golden stores, every route
	cd $(WEB) && ALGOTRADE_PY=$(abspath $(PY)) npx playwright test -c playwright.real.config.ts

web-visual:      ## screenshots + axe over every story, in the CI Linux image (needs Docker)
	cd $(WEB) && $(NPM) run visual:docker

# The build the API serves on its own origin (ADR 0044, docs/hosting.md): API calls go to the
# same origin's root (VITE_API_BASE_URL empty), Supabase keys from apps/web/.env.local. It goes
# to var/web, not dist/ (which `make check` rebuilds for the dev setup). Redo after a web change.
WEB_DIST ?= var/web
web-build: $(WEB)/node_modules/.package-lock.json  ## the production web build the API serves (ALGOTRADE_WEB_DIST=var/web); redo after a web change
	cd $(WEB) && VITE_API_BASE_URL= $(NPM) run build -- --outDir $(abspath $(WEB_DIST)) --emptyOutDir

# One full check per worktree: a second concurrent run refuses (scripts/ops/check_lock.sh).
check:
	scripts/ops/check_lock.sh $(MAKE) check-gates

check-gates: lock-check lint typecheck arch layout ownership dupes rest-allowlist filelen numbering datasets-verify test evaluate web-check web-real

nightly:
	HYPOTHESIS_PROFILE=nightly $(PY) -m pytest tests/property
	$(MAKE) evaluate
