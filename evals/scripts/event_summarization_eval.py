"""
evals/scripts/event_summarization_eval.py
==========================================
Event summarization evaluator for the LOCOMO benchmark.

Evaluation metric: FactScore (Min et al., 2023) adapted for event graphs.
  - Precision: fraction of atomic facts in predicted summary that appear in GT
  - Recall: fraction of GT atomic facts covered by predicted summary
  - F1: harmonic mean

The ground truth is the temporal event graph G from LOCOMO.
Each event in G is treated as an atomic fact.

For Dagestan, we also measure:
  - Temporal ordering accuracy (are events recalled in the right sequence?)
  - Causal chain accuracy (are caused_by relationships preserved?)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from evals.scripts.qa_eval import _build_llm_client, _mean, token_f1

log = logging.getLogger(__name__)

SUMMARIZE_SYSTEM = """\
You are summarising the life events of a person based on their conversation history.
Focus on specific, concrete events (activities, achievements, changes in life situation).
Ignore small talk. Output one event per line. Be factual and specific.
"""

SUMMARIZE_USER_TEMPLATE = """\
Conversation memory context:
{context}

Summarise the key life events for the speaker during this period ({start} to {end}).
One event per line. Be specific.
"""

ATOMIC_DECOMPOSE_SYSTEM = """\
Decompose the following text into a list of atomic facts.
Output one fact per line. Each fact should be a single, verifiable claim.
"""


class EventSummarizationEvaluator:
    def __init__(self, provider: str = "gemini", model: str = "gemini-1.5-flash"):
        self._client = _build_llm_client(provider, model)

    # ------------------------------------------------------------------

    def summarise(self, timeframe: dict, context: str) -> str:
        """Generate an event summary from Dagestan's retrieved context."""
        start = timeframe.get("start") or "the beginning"
        end = timeframe.get("end") or "the end"
        prompt = SUMMARIZE_USER_TEMPLATE.format(
            context=context or "(no context retrieved)",
            start=start,
            end=end,
        )
        try:
            return self._client.complete(system=SUMMARIZE_SYSTEM, user=prompt)
        except Exception as e:
            log.warning("Summarisation LLM call failed: %s", e)
            return ""

    def score(
        self,
        predicted: str,
        ground_truth_events: list[str],
    ) -> dict:
        """
        FactScore-style evaluation.

        Decomposes predicted summary into atomic facts, then checks each
        against the ground truth event list using token F1 > threshold.
        """
        pred_facts = self._decompose(predicted)
        gt_facts = ground_truth_events  # already atomic in LOCOMO

        if not gt_facts:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                    "n_pred_facts": 0, "n_gt_facts": 0}

        # Precision: how many predicted facts are supported by GT?
        precision_scores = []
        for pf in pred_facts:
            best = max((token_f1(pf, gf)[0] for gf in gt_facts), default=0.0)
            precision_scores.append(1.0 if best >= 0.4 else 0.0)

        # Recall: how many GT facts are covered by predicted facts?
        recall_scores = []
        for gf in gt_facts:
            best = max((token_f1(pf, gf)[0] for pf in pred_facts), default=0.0)
            recall_scores.append(1.0 if best >= 0.4 else 0.0)

        precision = _mean(precision_scores) if precision_scores else 0.0
        recall = _mean(recall_scores) if recall_scores else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "n_pred_facts": len(pred_facts),
            "n_gt_facts": len(gt_facts),
        }

    def aggregate(self, scores: list[dict]) -> dict:
        keys = ["precision", "recall", "f1"]
        agg = {k: _mean([s[k] for s in scores]) for k in keys}
        agg["n_summaries"] = len(scores)
        agg["per_item"] = scores
        return agg

    # ------------------------------------------------------------------

    def _decompose(self, text: str) -> list[str]:
        """
        Decompose a multi-sentence summary into atomic facts.
        Falls back to line-splitting if LLM call fails.
        """
        if not text.strip():
            return []

        # Simple heuristic first — if the text is already line-per-event
        lines = [l.strip().lstrip("-•*").strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 2:
            return [l for l in lines if len(l) > 10]

        try:
            result = self._client.complete(
                system=ATOMIC_DECOMPOSE_SYSTEM,
                user=text,
            )
            facts = [l.strip().lstrip("-•*").strip()
                     for l in result.split("\n") if l.strip()]
            return [f for f in facts if len(f) > 10]
        except Exception:
            return lines
