SHELL := /usr/bin/env bash

PYTHON ?= python3
REPO_ROOT := $(CURDIR)

# Canonical evaluation package lives in `evals/`.
EVALS_DIR := $(REPO_ROOT)/evals

DEFAULT_LOCOMO_CONFIG := $(EVALS_DIR)/configs/locomo_gemini_flash.yaml
DEFAULT_ABLATION_CONFIG := $(EVALS_DIR)/configs/ablation.yaml

# Defaults for the generic runner.
CONFIG ?= $(DEFAULT_LOCOMO_CONFIG)
TASK ?= all
LIMIT ?=
RETRIEVAL ?=
NO_SCHEMA_INDUCTION ?= 0
RUN_ID ?=

.DEFAULT_GOAL := help
.PHONY: help evals-check evals-shim evals-deps run smoke locomo qa summarization coherence \
	ablations ablations-baselines download-locomo

help:
	@echo "Usage:"
	@echo "  make smoke                       # CI-safe, stub provider"
	@echo "  make locomo LIMIT=5             # full benchmark (Gemini config)"
	@echo "  make qa TASK=qa LIMIT=3         # single task (overrides TASK)"
	@echo "  make run CONFIG=... TASK=...   # generic runner"
	@echo "  make download-locomo            # download/cached LOCOMO dataset"
	@echo "  make ablations                  # ablation study"
	@echo "  make ablations-baselines       # ablation baselines only"
	@echo ""
	@echo "Runner vars for make run:"
	@echo "  CONFIG=path            (default: $(DEFAULT_LOCOMO_CONFIG))"
	@echo "  TASK=all|qa|summarization|coherence (default: all)"
	@echo "  LIMIT=N                (optional)"
	@echo "  RETRIEVAL=hybrid|graph|vector|none (optional)"
	@echo "  NO_SCHEMA_INDUCTION=1 (optional)"
	@echo "  RUN_ID=some_id        (optional)"

evals-deps:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install datasets huggingface_hub pyyaml

evals-check:
	@mkdir -p "$(EVALS_DIR)/scripts" "$(EVALS_DIR)/configs" "$(EVALS_DIR)/locomo"
	@touch "$(EVALS_DIR)/__init__.py"
	@touch "$(EVALS_DIR)/scripts/__init__.py"
	@test -f "$(EVALS_DIR)/run_locomo_eval.py"
	@test -f "$(EVALS_DIR)/scripts/data_loader.py"
	@test -f "$(EVALS_DIR)/configs/smoke_test.yaml"

evals-shim: evals-check

# Runs the CI-safe harness. Note: this smoke config uses `provider: stub`.
# Your local Dagestan backend must be able to run with that provider (or the adapter must support it).
smoke: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(EVALS_DIR)/configs/smoke_test.yaml" $(if $(strip $(LIMIT)),--limit $(LIMIT),) $(if $(filter-out all,$(TASK)),--task $(TASK),) $(if $(strip $(RETRIEVAL)),--retrieval $(RETRIEVAL),) $(if $(filter 1,$(NO_SCHEMA_INDUCTION)),--no-schema-induction,) $(if $(strip $(RUN_ID)),--run-id $(RUN_ID),)

# Full LOCOMO benchmark run (Gemini Flash). Add LIMIT=5 to limit conversations.
locomo: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(DEFAULT_LOCOMO_CONFIG)" $(if $(strip $(LIMIT)),--limit $(LIMIT),) $(if $(filter-out all,$(TASK)),--task $(TASK),) $(if $(strip $(RETRIEVAL)),--retrieval $(RETRIEVAL),) $(if $(filter 1,$(NO_SCHEMA_INDUCTION)),--no-schema-induction,) $(if $(strip $(RUN_ID)),--run-id $(RUN_ID),)

run: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(if $(strip $(CONFIG)),$(CONFIG),$(DEFAULT_LOCOMO_CONFIG))" $(if $(strip $(LIMIT)),--limit $(LIMIT),) $(if $(filter-out all,$(TASK)),--task $(TASK),) $(if $(strip $(RETRIEVAL)),--retrieval $(RETRIEVAL),) $(if $(filter 1,$(NO_SCHEMA_INDUCTION)),--no-schema-induction,) $(if $(strip $(RUN_ID)),--run-id $(RUN_ID),)

qa: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(DEFAULT_LOCOMO_CONFIG)" --task qa $(if $(strip $(LIMIT)),--limit $(LIMIT),) $(if $(strip $(RETRIEVAL)),--retrieval $(RETRIEVAL),) $(if $(filter 1,$(NO_SCHEMA_INDUCTION)),--no-schema-induction,) $(if $(strip $(RUN_ID)),--run-id $(RUN_ID),)

summarization: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(DEFAULT_LOCOMO_CONFIG)" --task summarization $(if $(strip $(LIMIT)),--limit $(LIMIT),) $(if $(strip $(RETRIEVAL)),--retrieval $(RETRIEVAL),) $(if $(filter 1,$(NO_SCHEMA_INDUCTION)),--no-schema-induction,) $(if $(strip $(RUN_ID)),--run-id $(RUN_ID),)

coherence: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(DEFAULT_LOCOMO_CONFIG)" --task coherence $(if $(strip $(LIMIT)),--limit $(LIMIT),) $(if $(strip $(RETRIEVAL)),--retrieval $(RETRIEVAL),) $(if $(filter 1,$(NO_SCHEMA_INDUCTION)),--no-schema-induction,) $(if $(strip $(RUN_ID)),--run-id $(RUN_ID),)

ablations: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_ablations.py" --config "$(DEFAULT_ABLATION_CONFIG)"

ablations-baselines: evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_ablations.py" --config "$(DEFAULT_ABLATION_CONFIG)" --baselines-only

download-locomo: evals-deps evals-check
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/locomo/download_locomo.py"

