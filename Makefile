SHELL := /usr/bin/env bash

PYTHON ?= python3
REPO_ROOT := $(CURDIR)

# Canonical evaluation package lives in `evals/`.
EVALS_DIR := $(REPO_ROOT)/evals

.PHONY: evals-shim evals-deps smoke locomo qa summarization coherence ablations ablations-baselines download-locomo

evals-deps:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install datasets huggingface_hub pyyaml

evals-shim:
	@mkdir -p "$(EVALS_DIR)/scripts" "$(EVALS_DIR)/configs" "$(EVALS_DIR)/locomo"
	@touch "$(EVALS_DIR)/__init__.py"
	@touch "$(EVALS_DIR)/scripts/__init__.py"
	@test -f "$(EVALS_DIR)/run_locomo_eval.py"
	@test -f "$(EVALS_DIR)/scripts/data_loader.py"
	@test -f "$(EVALS_DIR)/configs/smoke_test.yaml"

# Runs the CI-safe harness. Note: this smoke config uses `provider: stub`.
# Your local Dagestan backend must be able to run with that provider (or the adapter must support it).
smoke: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(EVALS_DIR)/configs/smoke_test.yaml"

# Full LOCOMO benchmark run (Gemini Flash). Add LIMIT=5 to limit conversations.
locomo: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(EVALS_DIR)/configs/locomo_gemini_flash.yaml" $(if $(LIMIT),--limit $(LIMIT),)

qa: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(EVALS_DIR)/configs/locomo_gemini_flash.yaml" --task qa $(if $(LIMIT),--limit $(LIMIT),)

summarization: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(EVALS_DIR)/configs/locomo_gemini_flash.yaml" --task summarization $(if $(LIMIT),--limit $(LIMIT),)

coherence: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_locomo_eval.py" --config "$(EVALS_DIR)/configs/locomo_gemini_flash.yaml" --task coherence $(if $(LIMIT),--limit $(LIMIT),)

ablations: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_ablations.py" --config "$(EVALS_DIR)/configs/ablation.yaml"

ablations-baselines: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/run_ablations.py" --config "$(EVALS_DIR)/configs/ablation.yaml" --baselines-only

download-locomo: evals-shim
	PYTHONPATH=. $(PYTHON) "$(EVALS_DIR)/locomo/download_locomo.py"

