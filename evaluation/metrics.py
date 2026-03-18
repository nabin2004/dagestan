"""
evals/scripts/metrics.py
=========================
Result aggregation and leaderboard display.

Produces the final table suitable for inclusion in the MemAgents @ ICLR paper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def aggregate_results(all_results: dict[str, dict]) -> dict:
    """Combine per-task result dicts into a single summary."""
    summary: dict[str, Any] = {"tasks": {}}

    if "qa" in all_results:
        qa = all_results["qa"]
        summary["tasks"]["qa"] = {
            "overall_f1": qa.get("overall_f1"),
            "by_category": qa.get("by_category", {}),
            "n_questions": qa.get("n_questions"),
        }

    if "summarization" in all_results:
        s = all_results["summarization"]
        summary["tasks"]["summarization"] = {
            "precision": s.get("precision"),
            "recall": s.get("recall"),
            "f1": s.get("f1"),
            "n_summaries": s.get("n_summaries"),
        }

    if "coherence" in all_results:
        c = all_results["coherence"]
        summary["tasks"]["coherence"] = {
            "schema_induction_macro_f1": c.get("schema_induction_macro_f1"),
            "contradiction_recall": c.get("contradiction_recall"),
            "decay_pearson_r": c.get("decay_pearson_r"),
            "snapshot_fidelity_f1": c.get("snapshot_fidelity_f1"),
            "composite_coherence": c.get("composite_coherence"),
        }

    return summary


def print_leaderboard(summary: dict):
    """Print a formatted leaderboard table to stdout."""
    print()
    print("=" * 72)
    print(" DAGESTAN × LOCOMO EVALUATION RESULTS")
    print("=" * 72)

    tasks = summary.get("tasks", {})

    if "qa" in tasks:
        qa = tasks["qa"]
        print()
        print("  TASK 1: Question Answering (F1)")
        print("  " + "-" * 50)
        print(f"  {'Overall':30s} {_fmt(qa.get('overall_f1'))}")
        for cat, score in (qa.get("by_category") or {}).items():
            print(f"  {'  ' + cat:30s} {_fmt(score)}")

    if "summarization" in tasks:
        s = tasks["summarization"]
        print()
        print("  TASK 2: Event Summarization (FactScore)")
        print("  " + "-" * 50)
        print(f"  {'Precision':30s} {_fmt(s.get('precision'))}")
        print(f"  {'Recall':30s} {_fmt(s.get('recall'))}")
        print(f"  {'F1':30s} {_fmt(s.get('f1'))}")

    if "coherence" in tasks:
        c = tasks["coherence"]
        print()
        print("  TASK 3: Memory Coherence (Dagestan-specific)")
        print("  " + "-" * 50)
        print(f"  {'Schema Induction (macro-F1)':30s} {_fmt(c.get('schema_induction_macro_f1'))}")
        print(f"  {'Contradiction Recall':30s} {_fmt(c.get('contradiction_recall'))}")
        print(f"  {'Decay Calibration (Pearson r)':30s} {_fmt(c.get('decay_pearson_r'))}")
        print(f"  {'Snapshot Fidelity (F1)':30s} {_fmt(c.get('snapshot_fidelity_f1'))}")
        print(f"  {'Composite Coherence':30s} {_fmt(c.get('composite_coherence'))}")

    print()
    print("=" * 72)
    print()


def _fmt(val: Any, decimals: int = 4) -> str:
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.{decimals}f}"
    except (TypeError, ValueError):
        return str(val)


def load_results(results_dir: str) -> dict:
    """Load a saved summary.json from a results directory."""
    path = Path(results_dir) / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"No summary.json in {results_dir}")
    return json.loads(path.read_text())


def compare_runs(run_dirs: list[str]):
    """Print a side-by-side comparison of multiple eval runs."""
    summaries = {d: load_results(d) for d in run_dirs}
    print("\nRun comparison:")
    for run_dir, summary in summaries.items():
        print(f"\n  {run_dir}")
        print_leaderboard(summary)
