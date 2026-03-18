SHELL := /usr/bin/env bash

PYTHON ?= python3
REPO_ROOT := $(CURDIR)

# Source scripts/configs live in `evaluation/`.
# The runners expect to import from `evals.scripts.*` and to find configs under
# `evals/configs/*`, so we create a small symlink-based shim.
EVAL_SRC_DIR := $(REPO_ROOT)/evaluation
EVALS_DIR := $(REPO_ROOT)/evals

.PHONY: evals-shim evals-deps smoke locomo qa summarization coherence ablations ablations-baselines download-locomo

evals-deps:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install datasets huggingface_hub pyyaml

evals-shim:
	@mkdir -p "$(EVALS_DIR)/scripts" "$(EVALS_DIR)/configs" "$(EVALS_DIR)/locomo"
	@mkdir -p "$(EVALS_DIR)"
	@touch "$(EVALS_DIR)/__init__.py"
	@touch "$(EVALS_DIR)/scripts/__init__.py"
	@touch "$(EVALS_DIR)/configs/.keep"
	@touch "$(EVALS_DIR)/locomo/.keep"
	@ln -sf "$(EVAL_SRC_DIR)/run_locomo_eval.py" "$(EVALS_DIR)/run_locomo_eval.py"
	@ln -sf "$(EVAL_SRC_DIR)/run_ablations.py" "$(EVALS_DIR)/run_ablations.py"
	@ln -sf "$(EVAL_SRC_DIR)/download_locomo.py" "$(EVALS_DIR)/locomo/download_locomo.py"
	@ln -sf "$(EVAL_SRC_DIR)/locomo_gemini_flash.yaml" "$(EVALS_DIR)/configs/locomo_gemini_flash.yaml"
	@ln -sf "$(EVAL_SRC_DIR)/ablation.yaml" "$(EVALS_DIR)/configs/ablation.yaml"
	@ln -sf "$(EVAL_SRC_DIR)/smoke_test.yaml" "$(EVALS_DIR)/configs/smoke_test.yaml"
	@ln -sf "$(EVAL_SRC_DIR)/data_loader.py" "$(EVALS_DIR)/scripts/data_loader.py"
	@ln -sf "$(EVAL_SRC_DIR)/dagestan_adapter.py" "$(EVALS_DIR)/scripts/dagestan_adapter.py"
	@ln -sf "$(EVAL_SRC_DIR)/baselines.py" "$(EVALS_DIR)/scripts/baselines.py"
	@ln -sf "$(EVAL_SRC_DIR)/qa_eval.py" "$(EVALS_DIR)/scripts/qa_eval.py"
	@ln -sf "$(EVAL_SRC_DIR)/event_summarization_eval.py" "$(EVALS_DIR)/scripts/event_summarization_eval.py"
	@ln -sf "$(EVAL_SRC_DIR)/memory_coherence_eval.py" "$(EVALS_DIR)/scripts/memory_coherence_eval.py"
	@ln -sf "$(EVAL_SRC_DIR)/metrics.py" "$(EVALS_DIR)/scripts/metrics.py"

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

