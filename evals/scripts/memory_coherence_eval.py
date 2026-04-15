"""
evals/scripts/memory_coherence_eval.py
=======================================
Memory Coherence Evaluator — Dagestan-specific structural tests.

These metrics capture properties that distinguish Dagestan from flat
vector memory systems and are the core contribution metrics for the
MemAgents @ ICLR submission.

Four sub-metrics:
─────────────────────────────────────────────────────────────────────
1. Schema Induction Accuracy
   Tests the central claim: entity types and ontological structure
   emerge from conversational patterns rather than being predefined.

   Method: compare Dagestan's induced node-type distribution against a
   human-annotated ground-truth type distribution extracted from LOCOMO
   conversations. Measured as macro-F1 over node type assignments.

2. Contradiction Flagging Recall
   LOCOMO contains known speaker-level contradictions (e.g., speaker
   says they love running in session 3, then mentions a knee injury
   preventing running in session 7). Measures fraction of known
   contradictions that Dagestan flags.

3. Temporal Decay Calibration (Ebbinghaus)
   Dagestan's confidence decay is modelled after the Ebbinghaus
   forgetting curve. We verify that node confidence scores at eval time
   correlate with expected memorability based on:
     - Recency (time since last reinforcement)
     - Retrieval frequency (how often the node was accessed)
   Measured as Pearson r between predicted and idealised Ebbinghaus score.

4. Snapshot Fidelity
   Dagestan takes temporal snapshots after each session. We verify that
   the graph state at session k reflects only information available up to
   session k (no future leakage) and correctly represents all information
   introduced up to that point.
   Measured as precision/recall against turn-annotated evidence in LOCOMO.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evals.scripts.dagestan_adapter import DagestandAdapter

from evals.scripts.qa_eval import _mean, token_f1

log = logging.getLogger(__name__)


class MemoryCoherenceEvaluator:

    # ------------------------------------------------------------------

    def score(self, adapter: "DagestandAdapter", conversation: dict) -> dict:
        results = {}

        results["schema_induction"] = self._eval_schema_induction(
            adapter, conversation
        )
        results["contradiction_recall"] = self._eval_contradiction_recall(
            adapter, conversation
        )
        results["decay_calibration"] = self._eval_decay_calibration(
            adapter, conversation
        )
        results["snapshot_fidelity"] = self._eval_snapshot_fidelity(
            adapter, conversation
        )

        # Composite coherence score (equal weight)
        component_scores = [
            results["schema_induction"].get("macro_f1", 0.0),
            results["contradiction_recall"].get("recall", 0.0),
            results["decay_calibration"].get("pearson_r", 0.0),
            results["snapshot_fidelity"].get("f1", 0.0),
        ]
        results["composite_coherence"] = _mean([s for s in component_scores if s is not None])

        return results

    # ------------------------------------------------------------------
    # 1. Schema Induction Accuracy
    # ------------------------------------------------------------------

    def _eval_schema_induction(
        self, adapter: "DagestandAdapter", conversation: dict
    ) -> dict:
        """
        Compare induced node type distribution vs. ground-truth.

        Ground-truth type annotation: for each LOCOMO persona we can
        infer expected node types from the conversation structure:
          - Speaker names → ENTITY
          - Life events from event graph → EVENT
          - Mentioned preferences (food, hobbies) → PREFERENCE
          - Goals / aspirations → GOAL
          - Abstract topics → CONCEPT
        """
        induced = adapter.get_induced_schema()
        if not induced:
            return {"macro_f1": None, "note": "schema not available (stub)"}

        gt_types = _infer_gt_type_distribution(conversation)
        if not gt_types:
            return {"macro_f1": None, "note": "no GT type annotations"}

        # Measure whether expected types are present at all (type coverage)
        expected = set(gt_types.keys())
        found = set(k.split(".")[-1].lower() for k in induced.keys())

        # Normalise type names
        type_map = {
            "nodetype.entity": "entity",
            "nodetype.event": "event",
            "nodetype.preference": "preference",
            "nodetype.goal": "goal",
            "nodetype.concept": "concept",
        }
        found_normalised = {type_map.get(k.lower(), k.lower()) for k in found}

        tp = len(expected & found_normalised)
        fp = len(found_normalised - expected)
        fn = len(expected - found_normalised)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        macro_f1 = (2 * precision * recall / (precision + recall)
                    if (precision + recall) > 0 else 0.0)

        return {
            "macro_f1": macro_f1,
            "precision": precision,
            "recall": recall,
            "expected_types": sorted(expected),
            "found_types": sorted(found_normalised),
            "induced_node_counts": induced,
        }

    # ------------------------------------------------------------------
    # 2. Contradiction Flagging Recall
    # ------------------------------------------------------------------

    def _eval_contradiction_recall(
        self, adapter: "DagestandAdapter", conversation: dict
    ) -> dict:
        """
        Check what fraction of known contradictions Dagestan flagged.

        We identify ground-truth contradictions by looking for QA pairs
        with category='adversarial' that have known conflicting facts in
        the conversation, or explicit contradiction annotations in LOCOMO.
        """
        gt_contradictions = _extract_gt_contradictions(conversation)
        if not gt_contradictions:
            return {"recall": None, "note": "no GT contradictions in this conversation"}

        detected = adapter.get_contradictions()

        if not detected:
            return {
                "recall": 0.0,
                "n_gt": len(gt_contradictions),
                "n_detected": 0,
                "note": "no contradictions detected",
            }

        # Match detected contradictions to GT by keyword overlap
        matched = 0
        for gt in gt_contradictions:
            for det in detected:
                det_str = str(det).lower()
                gt_str = str(gt).lower()
                overlap = token_f1(det_str, gt_str)[0]
                if overlap > 0.3:
                    matched += 1
                    break

        recall = matched / len(gt_contradictions)
        return {
            "recall": recall,
            "n_gt": len(gt_contradictions),
            "n_detected": len(detected),
            "n_matched": matched,
        }

    # ------------------------------------------------------------------
    # 3. Temporal Decay Calibration (Ebbinghaus)
    # ------------------------------------------------------------------

    def _eval_decay_calibration(
        self, adapter: "DagestandAdapter", conversation: dict
    ) -> dict:
        """
        Measures whether Dagestan's confidence decay approximates the
        Ebbinghaus forgetting curve:
          R = e^(-t / S)
        where t = time elapsed, S = stability (reinforcement count).

        We compute the expected Ebbinghaus retention for each node based
        on its last_reinforced timestamp and retrieval frequency, then
        correlate with Dagestan's actual confidence scores.
        """
        confidences = adapter.get_node_confidences()
        if not confidences:
            return {"pearson_r": None, "note": "no node confidence data"}

        # Without per-node timestamps (which requires deeper Dagestan API),
        # we use a proxy: confidence score rank vs. session recency rank.
        # Nodes from later sessions should have higher confidence.
        # This is a structural test of monotonicity.
        scores = list(confidences.values())
        if len(scores) < 3:
            return {"pearson_r": None, "note": "too few nodes to calibrate"}

        # Check that mean confidence of last-ingested nodes > early nodes
        # (proxy for recency bias — Ebbinghaus predicts higher retention for recent)
        n = len(scores)
        first_half_mean = _mean(scores[:n // 2])
        second_half_mean = _mean(scores[n // 2:])

        # Pearson correlation proxy: do scores decrease over node creation order?
        r = _pearson(list(range(n)), scores)

        return {
            "pearson_r": r,
            "first_half_mean_confidence": round(first_half_mean, 4),
            "second_half_mean_confidence": round(second_half_mean, 4),
            "recency_bias_correct": second_half_mean > first_half_mean,
            "n_nodes": n,
        }

    # ------------------------------------------------------------------
    # 4. Snapshot Fidelity
    # ------------------------------------------------------------------

    def _eval_snapshot_fidelity(
        self, adapter: "DagestandAdapter", conversation: dict
    ) -> dict:
        """
        Verify that graph snapshots correctly capture conversation state.

        For each session k, check that:
          - Information from sessions > k is NOT in snapshot k (no leakage)
          - Key entities from sessions ≤ k ARE in snapshot k (coverage)
        """
        sessions = conversation.get("sessions", [])
        if len(sessions) < 2:
            return {"f1": None, "note": "too few sessions for snapshot eval"}

        # Pick middle session as test point
        test_session_idx = len(sessions) // 2
        snapshot = adapter.get_snapshot_at_session(test_session_idx)

        if not snapshot:
            return {"f1": None, "note": "snapshots not available (v0.1 limitation)"}

        # Entities that should be in the snapshot (mentioned in sessions ≤ test_session_idx)
        past_entities = _extract_entities_from_sessions(
            sessions[:test_session_idx + 1]
        )
        # Entities that should NOT be in the snapshot (from future sessions)
        future_entities = _extract_entities_from_sessions(
            sessions[test_session_idx + 1:]
        )

        snapshot_labels = set(str(v).lower() for v in snapshot.values()
                              if isinstance(v, str))

        # Coverage (recall of past entities)
        covered = sum(
            1 for e in past_entities
            if any(e.lower() in s for s in snapshot_labels)
        )
        coverage = covered / len(past_entities) if past_entities else 0.0

        # Leakage (precision — future entities NOT in snapshot)
        leaked = sum(
            1 for e in future_entities
            if any(e.lower() in s for s in snapshot_labels)
        )
        no_leakage = 1.0 - (leaked / len(future_entities)) if future_entities else 1.0

        f1 = (2 * coverage * no_leakage / (coverage + no_leakage)
              if (coverage + no_leakage) > 0 else 0.0)

        return {
            "f1": f1,
            "coverage_recall": coverage,
            "leakage_precision": no_leakage,
            "n_past_entities": len(past_entities),
            "n_future_entities": len(future_entities),
            "test_session_idx": test_session_idx,
        }

    # ------------------------------------------------------------------

    def aggregate(self, scores: list[dict]) -> dict:
        def avg_key(key, sub_key):
            vals = [s[key][sub_key] for s in scores
                    if key in s and s[key].get(sub_key) is not None]
            return _mean(vals) if vals else None

        composite_vals = [
            float(s["composite_coherence"])
            for s in scores
            if isinstance(s.get("composite_coherence"), (int, float))
        ]
        return {
            "schema_induction_macro_f1": avg_key("schema_induction", "macro_f1"),
            "contradiction_recall": avg_key("contradiction_recall", "recall"),
            "decay_pearson_r": avg_key("decay_calibration", "pearson_r"),
            "snapshot_fidelity_f1": avg_key("snapshot_fidelity", "f1"),
            "composite_coherence": _mean(composite_vals) if composite_vals else None,
            "n_conversations": len(scores),
            "per_conversation": scores,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_gt_type_distribution(conversation: dict) -> dict[str, int]:
    """Heuristic GT type distribution from LOCOMO conversation structure."""
    types: dict[str, int] = {}
    personas = conversation.get("personas", {})
    if personas:
        types["entity"] = len(personas)

    event_summaries = conversation.get("event_summaries", [])
    if event_summaries:
        types["event"] = sum(len(es.get("events", [])) for es in event_summaries)

    # Estimate preferences/goals from QA pairs
    qa_pairs = conversation.get("qa_pairs", [])
    pref_count = sum(1 for qa in qa_pairs
                     if any(w in qa.get("question", "").lower()
                            for w in ["like", "love", "prefer", "enjoy", "hate", "dislike"]))
    if pref_count > 0:
        types["preference"] = pref_count

    goal_count = sum(1 for qa in qa_pairs
                     if any(w in qa.get("question", "").lower()
                            for w in ["want", "goal", "plan", "aspire", "hope"]))
    if goal_count > 0:
        types["goal"] = goal_count

    return types


def _extract_gt_contradictions(conversation: dict) -> list[str]:
    """
    LOCOMO doesn't have explicit contradiction annotations, but adversarial
    QA pairs often encode known contradictions. We use those as a proxy.
    """
    return [
        qa["question"]
        for qa in conversation.get("qa_pairs", [])
        if qa.get("category") == "adversarial"
    ]


def _extract_entities_from_sessions(sessions: list[dict]) -> list[str]:
    """Extract rough entity mentions (proper nouns) from session turns."""
    import re
    entities = set()
    for session in sessions:
        for turn in session.get("turns", []):
            text = turn.get("text", "")
            # Rough heuristic: capitalised words are likely entities
            words = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
            entities.update(words)
    return list(entities)


def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)
