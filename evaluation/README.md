# Dagestan × LOCOMO Evaluation Suite

Evaluation harness for benchmarking Dagestan's temporal knowledge graph memory
against the [LOCOMO benchmark](https://snap-research.github.io/locomo)
(Maharana et al., 2024 — *Evaluating Very Long-Term Conversational Memory of LLM Agents*).

Target venue: **MemAgents @ ICLR 2026**

---

## Core Claim Under Evaluation

> Dagestan introduces **dynamic schema induction** for personal memory graphs, where
> entity types and ontological structure emerge from conversational patterns rather
> than being predefined, enabling more accurate, personalised, and adaptive memory
> representation than fixed-schema systems.

---

## Directory Structure

```
evals/
├── run_locomo_eval.py        ← main evaluation runner
├── run_ablations.py          ← ablation study runner
├── configs/
│   ├── locomo_gemini_flash.yaml  ← full benchmark (~$2, Gemini Flash)
│   ├── ablation.yaml             ← ablation study (10 conversations)
│   └── smoke_test.yaml           ← CI dry-run (no LLM calls, 3 conversations)
├── scripts/
│   ├── data_loader.py        ← LOCOMO dataset loader (HF or local JSON)
│   ├── dagestan_adapter.py   ← Dagestan API wrapper for eval
│   ├── baselines.py          ← comparison baselines (no-memory, flat-RAG, etc.)
│   ├── qa_eval.py            ← QA task evaluator (5 categories, token F1)
│   ├── event_summarization_eval.py  ← FactScore event summarisation
│   ├── memory_coherence_eval.py     ← Dagestan-specific structural tests
│   └── metrics.py            ← aggregation + leaderboard display
├── locomo/
│   ├── download_locomo.py    ← download from HuggingFace
│   └── locomo_dataset.json   ← cached dataset (after first download)
└── results/                  ← output directory (created at runtime)
    └── <run_id>/
        ├── config.yaml
        ├── qa_results.json
        ├── summarization_results.json
        ├── coherence_results.json
        └── summary.json
```

---

## Setup

```bash
# Install Dagestan
pip install -e ".[openai]"   # or [anthropic]
pip install google-generativeai  # for Gemini

# Install eval dependencies
pip install datasets huggingface_hub pyyaml sentence-transformers chromadb

# Download LOCOMO dataset
python evals/locomo/download_locomo.py
```

Set your API key:
```bash
export GEMINI_API_KEY=your_key_here
```

---

## Running the Benchmark

### Full benchmark run (~$2 on Gemini Flash, ~90 mins)
```bash
python evals/run_locomo_eval.py --config evals/configs/locomo_gemini_flash.yaml
```

### Smoke test (no LLM calls, CI-safe)
```bash
python evals/run_locomo_eval.py --config evals/configs/smoke_test.yaml
```

### Single task
```bash
python evals/run_locomo_eval.py \
    --config evals/configs/locomo_gemini_flash.yaml \
    --task qa
```

### Limit to N conversations (fast iteration)
```bash
python evals/run_locomo_eval.py \
    --config evals/configs/locomo_gemini_flash.yaml \
    --limit 5
```

---

## Ablation Study

Tests the contribution of each Dagestan component:

```bash
# Full ablation (all conditions, 10 conversations each)
python evals/run_ablations.py --config evals/configs/ablation.yaml

# Individual ablation conditions
python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval hybrid
python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval graph
python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval vector
python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval none
python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --no-schema-induction
```

Expected ablation table columns:

| Condition                | QA F1 | Summ F1 | Coherence |
|--------------------------|-------|---------|-----------|
| Dagestan hybrid          |       |         |           |
| Dagestan graph-only      |       |         |           |
| Dagestan vector-only     |       |         |           |
| Dagestan no schema induct|       |         |           |
| No memory (window)       |       |         |           |
| Flat vector RAG          |       |         |           |
| Session summary RAG      |       |         |           |
| Observation RAG          |       |         |           |

*(Fill in after running.)*

---

## Tasks

### Task 1: Question Answering (F1)
Mirrors LOCOMO paper setup. Five reasoning categories:
- **single_hop** — answer from a single session
- **multi_hop** — synthesise across multiple sessions
- **temporal** — time-aware reasoning (hardest for LLMs per LOCOMO paper)
- **open_domain** — external knowledge + conversation
- **adversarial** — model should correctly refuse to answer

Scoring: token-level F1 (partial match), identical to LOCOMO paper.

### Task 2: Event Summarization (FactScore)
Dagestan retrieves context for a time window; evaluator generates a summary and
scores it against the ground-truth temporal event graph using FactScore
(precision/recall/F1 on atomic facts).

### Task 3: Memory Coherence (Dagestan-specific)
Four sub-metrics testing structural properties unique to Dagestan:

| Metric | What it measures |
|--------|-----------------|
| Schema Induction Macro-F1 | Do emerged node types match GT entity distribution? |
| Contradiction Recall | Fraction of LOCOMO adversarial contradictions caught |
| Decay Calibration (Pearson r) | Correlation of confidence scores with Ebbinghaus model |
| Snapshot Fidelity F1 | No future leakage + full past coverage in graph snapshots |

---

## Key Design Decisions

**Why Gemini Flash?** Lowest cost per token of any frontier model (~$0.075/$0.30
per 1M input/output tokens). Full LOCOMO benchmark = ~8M tokens ≈ $2 total.

**Offline curation model.** Dagestan's nightly curation runs *between* sessions
(not during), matching its intended deployment pattern. This is important for
evaluation validity.

**Retrieval trace logging.** Every QA retrieval logs which nodes/chunks were used,
enabling recall@k analysis (how often was the correct source retrieved?), matching
the LOCOMO paper's RAG evaluation methodology.

**Stub provider.** The `stub` provider makes zero LLM calls and returns empty
strings everywhere. Use `smoke_test.yaml` to verify the eval harness is correctly
wired before spending real API budget.

---

## Citation

If you use this eval suite, please cite:

```bibtex
@inproceedings{maharana2024locomo,
  title={Evaluating Very Long-Term Conversational Memory of LLM Agents},
  author={Maharana, Adyasha and Lee, Dong-Ho and Tulyakov, Sergey and
          Bansal, Mohit and Barbieri, Francesco and Fang, Yuwei},
  booktitle={arXiv preprint arXiv:2402.17753},
  year={2024}
}
```
