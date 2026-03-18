"""
evals/run_locomo_eval.py
========================
Dagestan × LOCOMO Evaluation Runner

Evaluates Dagestan's temporal knowledge graph memory against the LOCOMO
benchmark (Maharana et al., 2024) across three tasks:

  1. Question Answering   — five reasoning categories (single-hop, multi-hop,
                            temporal, open-domain, adversarial)
  2. Event Summarization  — FactScore precision/recall/F1
  3. Memory Coherence     — contradiction detection, decay accuracy,
                            schema induction fidelity (Dagestan-specific)

Dagestan claim under evaluation
--------------------------------
  Dynamic schema induction for personal memory graphs: entity types and
  ontological structure *emerge* from conversational patterns rather than being
  predefined, enabling more accurate, personalised, and adaptive memory
  representation than fixed-schema systems.

Target venue: MemAgents @ ICLR 2026

Usage
-----
  # Full benchmark run (~$2 on Gemini Flash, 8M tokens)
  python evals/run_locomo_eval.py --config evals/configs/locomo_gemini_flash.yaml

  # Quick smoke-test on first 3 conversations
  python evals/run_locomo_eval.py --config evals/configs/locomo_gemini_flash.yaml --limit 3

  # Single task
  python evals/run_locomo_eval.py --config evals/configs/locomo_gemini_flash.yaml --task qa

  # Ablation: graph-only (no vectors), vectors-only (no graph), hybrid
  python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval graph
  python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval vector
  python evals/run_locomo_eval.py --config evals/configs/ablation.yaml --retrieval hybrid
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import yaml

from evals.scripts.data_loader import LocomoDataLoader
from evals.scripts.qa_eval import QAEvaluator
from evals.scripts.event_summarization_eval import EventSummarizationEvaluator
from evals.scripts.memory_coherence_eval import MemoryCoherenceEvaluator
from evals.scripts.dagestan_adapter import DagestandAdapter
from evals.scripts.baselines import BaselineAdapter
from evals.scripts.metrics import aggregate_results, print_leaderboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("locomo_eval")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class EvalConfig:
    # Data
    locomo_path: str = "evals/locomo/locomo_dataset.json"
    limit: Optional[int] = None               # None = full benchmark
    conversation_ids: list[str] = field(default_factory=list)  # subset

    # Model / provider
    provider: str = "gemini"                  # gemini | openai | anthropic
    model: str = "gemini-1.5-flash"
    api_key_env: str = "GEMINI_API_KEY"

    # Dagestan settings
    dagestan_db_path: str = "evals/results/dagestan_memory.json"
    schema_induction: bool = True             # True = dynamic; False = fixed
    hybrid_retrieval: bool = True
    vector_store_path: str = "evals/results/chroma_store"
    nightly_curation: bool = True             # offline curation between sessions
    decay_enabled: bool = True
    contradiction_resolution: str = "llm"     # llm | decay | none

    # Tasks
    tasks: list[str] = field(default_factory=lambda: ["qa", "summarization", "coherence"])

    # Retrieval ablation
    retrieval_mode: str = "hybrid"            # hybrid | graph | vector | none

    # Output
    results_dir: str = "evals/results"
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    @classmethod
    def from_yaml(cls, path: str) -> "EvalConfig":
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class LocomoEvalRunner:
    """
    Streams LOCOMO conversations through Dagestan, then evaluates
    memory retrieval quality against benchmark ground truth.
    """

    def __init__(self, config: EvalConfig, retrieval_mode: Optional[str] = None):
        self.cfg = config
        self.cfg.retrieval_mode = retrieval_mode or config.retrieval_mode

        self.results_dir = Path(config.results_dir) / config.run_id
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Persist the config that produced these results
        (self.results_dir / "config.yaml").write_text(yaml.dump(asdict(config)))

        log.info("Run ID: %s", config.run_id)
        log.info("Tasks:  %s", config.tasks)
        log.info("Model:  %s / %s", config.provider, config.model)
        log.info("Mode:   retrieval=%s  schema_induction=%s",
                 self.cfg.retrieval_mode, config.schema_induction)

    # ------------------------------------------------------------------

    def run(self) -> dict:
        loader = LocomoDataLoader(self.cfg.locomo_path)
        conversations = loader.load(
            limit=self.cfg.limit,
            ids=self.cfg.conversation_ids or None,
        )
        log.info("Loaded %d LOCOMO conversations", len(conversations))

        all_results: dict[str, dict] = {}

        for task in self.cfg.tasks:
            log.info("=" * 60)
            log.info("TASK: %s", task.upper())
            log.info("=" * 60)

            if task == "qa":
                results = self._run_qa(conversations)
            elif task == "summarization":
                results = self._run_summarization(conversations)
            elif task == "coherence":
                results = self._run_coherence(conversations)
            else:
                log.warning("Unknown task '%s' — skipping", task)
                continue

            all_results[task] = results
            # Save per-task results immediately (safe if run crashes later)
            self._save(f"{task}_results.json", results)

        summary = aggregate_results(all_results)
        self._save("summary.json", summary)
        print_leaderboard(summary)
        return summary

    # ------------------------------------------------------------------
    # Per-task runners
    # ------------------------------------------------------------------

    def _build_dagestan(self, conversation: dict) -> DagestandAdapter:
        """
        Replay a LOCOMO conversation through Dagestan session-by-session,
        applying nightly curation between sessions (offline curation model).
        """
        adapter = DagestandAdapter(
            provider=self.cfg.provider,
            model=self.cfg.model,
            db_path=str(self.results_dir / f"dagestan_{conversation['id']}.json"),
            vector_store_path=str(self.results_dir / f"chroma_{conversation['id']}"),
            schema_induction=self.cfg.schema_induction,
            hybrid_retrieval=self.cfg.hybrid_retrieval,
            retrieval_mode=self.cfg.retrieval_mode,
            decay_enabled=self.cfg.decay_enabled,
            contradiction_resolution=self.cfg.contradiction_resolution,
        )

        sessions = conversation.get("sessions", [])
        for session_idx, session in enumerate(sessions):
            # Ingest turns as a block (simulates real session end-of-day ingestion)
            session_text = _flatten_session(session)
            adapter.ingest_session(
                session_text=session_text,
                session_id=session_idx,
                session_date=session.get("date"),
            )

            # Offline curation: runs between sessions (nightly)
            if self.cfg.nightly_curation and session_idx < len(sessions) - 1:
                adapter.curate(reason="nightly")

        return adapter

    def _run_qa(self, conversations: list[dict]) -> dict:
        evaluator = QAEvaluator(
            provider=self.cfg.provider,
            model=self.cfg.model,
        )
        all_scores: list[dict] = []

        for conv in conversations:
            log.info("  QA · conversation %s", conv["id"])
            adapter = self._build_dagestan(conv)

            for qa_item in conv.get("qa_pairs", []):
                question = qa_item["question"]
                ground_truth = qa_item["answer"]
                category = qa_item.get("category", "unknown")

                # Dagestan retrieval
                context = adapter.retrieve(question)

                # Generate answer with retrieved context
                predicted = evaluator.answer(question, context)

                score = evaluator.score(
                    predicted=predicted,
                    ground_truth=ground_truth,
                    category=category,
                )
                score.update({
                    "conversation_id": conv["id"],
                    "question": question,
                    "predicted": predicted,
                    "ground_truth": ground_truth,
                    "category": category,
                    "retrieval_trace": adapter.last_retrieval_trace(),
                })
                all_scores.append(score)

        return evaluator.aggregate(all_scores)

    def _run_summarization(self, conversations: list[dict]) -> dict:
        evaluator = EventSummarizationEvaluator(
            provider=self.cfg.provider,
            model=self.cfg.model,
        )
        all_scores: list[dict] = []

        for conv in conversations:
            log.info("  SUMM · conversation %s", conv["id"])
            adapter = self._build_dagestan(conv)

            for summ_item in conv.get("event_summaries", []):
                timeframe = summ_item["timeframe"]
                ground_truth_events = summ_item["events"]

                # Ask Dagestan to summarise events in the timeframe
                context = adapter.retrieve_temporal_window(
                    start=timeframe["start"],
                    end=timeframe["end"],
                )
                predicted_summary = evaluator.summarise(timeframe, context)

                score = evaluator.score(
                    predicted=predicted_summary,
                    ground_truth_events=ground_truth_events,
                )
                score["conversation_id"] = conv["id"]
                all_scores.append(score)

        return evaluator.aggregate(all_scores)

    def _run_coherence(self, conversations: list[dict]) -> dict:
        """
        Dagestan-specific evaluation — tests the structural properties that
        distinguish it from flat vector memory:

          1. Schema induction accuracy     — do emerged node types match GT?
          2. Contradiction flagging recall  — are known contradictions caught?
          3. Temporal decay calibration     — do Ebbinghaus-fitted confidence
                                             scores correlate with ground truth
                                             memorability?
          4. Snapshot fidelity             — does graph state at session k
                                             correctly reflect information up to k?
        """
        evaluator = MemoryCoherenceEvaluator()
        all_scores: list[dict] = []

        for conv in conversations:
            log.info("  COHERENCE · conversation %s", conv["id"])
            adapter = self._build_dagestan(conv)

            score = evaluator.score(
                adapter=adapter,
                conversation=conv,
            )
            score["conversation_id"] = conv["id"]
            all_scores.append(score)

        return evaluator.aggregate(all_scores)

    # ------------------------------------------------------------------

    def _save(self, filename: str, data: dict):
        path = self.results_dir / filename
        path.write_text(json.dumps(data, indent=2, default=str))
        log.info("Saved → %s", path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_session(session: dict) -> str:
    """Turn a LOCOMO session dict into a plain-text conversation string."""
    lines = []
    for turn in session.get("turns", []):
        speaker = turn.get("speaker", "?")
        text = turn.get("text", "")
        caption = turn.get("image_caption", "")
        if caption:
            text = f"{text} [image: {caption}]".strip()
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Dagestan × LOCOMO evaluation runner"
    )
    parser.add_argument(
        "--config",
        default="evals/configs/locomo_gemini_flash.yaml",
        help="Path to YAML config file",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Evaluate only the first N conversations")
    parser.add_argument(
        "--task",
        choices=["qa", "summarization", "coherence", "all"],
        default="all",
        help="Which task(s) to run",
    )
    parser.add_argument(
        "--retrieval",
        choices=["hybrid", "graph", "vector", "none"],
        default=None,
        help="Override retrieval mode (ablation)",
    )
    parser.add_argument(
        "--no-schema-induction",
        action="store_true",
        help="Disable dynamic schema induction (use fixed ontology baseline)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override auto-generated run ID",
    )
    args = parser.parse_args()

    cfg = EvalConfig.from_yaml(args.config)

    if args.limit is not None:
        cfg.limit = args.limit
    if args.task != "all":
        cfg.tasks = [args.task]
    if args.no_schema_induction:
        cfg.schema_induction = False
    if args.run_id:
        cfg.run_id = args.run_id

    runner = LocomoEvalRunner(cfg, retrieval_mode=args.retrieval)
    runner.run()


if __name__ == "__main__":
    main()
