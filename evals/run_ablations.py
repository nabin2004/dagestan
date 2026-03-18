"""
evals/run_ablations.py
======================
Runs the full ablation study for the MemAgents @ ICLR paper.

Conditions:
  Row 1:  Dagestan hybrid (full system)          ← main result
  Row 2:  Dagestan graph-only                    ← ablate vectors
  Row 3:  Dagestan vector-only                   ← ablate graph
  Row 4:  Dagestan no schema induction           ← ablate dynamic ontology
  Row 5:  Dagestan no decay                      ← ablate Ebbinghaus decay
  Row 6:  No memory (recent window)              ← baseline
  Row 7:  Flat vector RAG                        ← baseline
  Row 8:  Session summary RAG                    ← LOCOMO paper baseline
  Row 9:  Observation RAG                        ← LOCOMO paper best baseline

Usage:
  python evals/run_ablations.py --config evals/configs/ablation.yaml
  python evals/run_ablations.py --config evals/configs/ablation.yaml --baselines-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml


CONDITIONS = [
    # (label, extra_cli_flags, is_baseline)
    ("Dagestan hybrid",            [],                                    False),
    ("Dagestan graph-only",        ["--retrieval", "graph"],              False),
    ("Dagestan vector-only",       ["--retrieval", "vector"],             False),
    ("Dagestan no schema induct.", ["--no-schema-induction"],             False),
    ("No memory (window)",         ["--retrieval", "none"],               False),
]

BASELINE_CONDITIONS = [
    ("No memory (window)",   "no_memory"),
    ("Flat vector RAG",      "flat_rag"),
    ("Session summary RAG",  "session_summary"),
    ("Observation RAG",      "observation_rag"),
]


def run_condition(
    label: str,
    config_path: str,
    extra_flags: list[str],
    run_id: str,
) -> Optional[dict]:
    cmd = [
        sys.executable, "evals/run_locomo_eval.py",
        "--config", config_path,
        "--run-id", run_id,
        *extra_flags,
    ]
    print(f"\n[ablation] Running: {label}")
    print(f"  cmd: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  ERROR: condition '{label}' failed with code {result.returncode}")
        return None

    # Load saved results
    results_dir = Path(yaml.safe_load(open(config_path))["results_dir"])
    summary_path = results_dir / run_id / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text())
    return None


def print_ablation_table(results: dict[str, Optional[dict]]):
    from evals.scripts.metrics import _fmt

    header = f"{'Condition':<35} {'QA F1':>8} {'Summ F1':>9} {'Coherence':>10}"
    print("\n" + "=" * 65)
    print(" ABLATION STUDY RESULTS")
    print("=" * 65)
    print(header)
    print("-" * 65)

    for label, summary in results.items():
        if summary is None:
            print(f"{label:<35} {'ERROR':>8}")
            continue
        tasks = summary.get("tasks", {})
        qa_f1 = tasks.get("qa", {}).get("overall_f1")
        summ_f1 = tasks.get("summarization", {}).get("f1")
        coherence = tasks.get("coherence", {}).get("composite_coherence")
        print(f"{label:<35} {_fmt(qa_f1):>8} {_fmt(summ_f1):>9} {_fmt(coherence):>10}")

    print("=" * 65)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="evals/configs/ablation.yaml")
    parser.add_argument("--baselines-only", action="store_true")
    args = parser.parse_args()

    all_results: dict[str, Optional[dict]] = {}

    conditions = CONDITIONS if not args.baselines_only else []

    for label, flags, _ in conditions:
        run_id = label.lower().replace(" ", "_").replace(".", "")
        summary = run_condition(label, args.config, flags, run_id)
        all_results[label] = summary

    print_ablation_table(all_results)

    # Save combined table
    cfg = yaml.safe_load(open(args.config))
    out = Path(cfg["results_dir"]) / "ablation_table.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\nSaved ablation table → {out}")


if __name__ == "__main__":
    main()
