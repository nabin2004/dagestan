"""
dagestan.curation.curator
~~~~~~~~~~~~~~~~~~~~~~~~~

Nightly / on-demand curation pipeline.

Orchestrates graph maintenance operations:
1. Apply temporal decay
2. Detect contradictions
3. Resolve contradictions via LLM
4. Detect gaps (for reporting)
5. Save curated graph state
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..extraction.extractor import LLMClient
from ..extraction.prompts import (
    CONTRADICTION_RESOLUTION_SYSTEM_PROMPT,
    CONTRADICTION_RESOLUTION_USER_TEMPLATE,
)
from ..graph.operations import apply_decay, detect_bridges, detect_contradictions, detect_gaps
from ..graph.schema import Node
from ..graph.temporal_graph import TemporalGraph

logger = logging.getLogger(__name__)


@dataclass
class CurationReport:
    """Summary of what happened during a curation run."""

    timestamp: str = ""
    nodes_decayed: int = 0
    contradictions_found: int = 0
    contradictions_resolved: int = 0
    gaps_found: int = 0
    bridges_found: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "nodes_decayed": self.nodes_decayed,
            "contradictions_found": self.contradictions_found,
            "contradictions_resolved": self.contradictions_resolved,
            "gaps_found": self.gaps_found,
            "bridges_found": self.bridges_found,
            "details": self.details,
        }


class Curator:
    """
    Orchestrates graph curation — the maintenance cycle that keeps
    the knowledge graph healthy and current.

    Runs: decay → contradiction detection → LLM resolution → gap/bridge scan.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
    ) -> None:
        """
        Args:
            llm_client: Optional LLM callable for contradiction resolution.
                        If None, contradictions are flagged but not auto-resolved.
        """
        self._llm = llm_client

    def run_curation(
        self,
        graph: TemporalGraph,
        current_time: datetime | None = None,
    ) -> CurationReport:
        """
        Run the full curation pipeline on a graph.

        Modifies the graph in place. Returns a report of what changed.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        report = CurationReport(timestamp=current_time.isoformat())

        # Step 1: Apply temporal decay
        logger.info("Curation: applying temporal decay...")
        decay_count = apply_decay(graph, current_time=current_time)
        report.nodes_decayed = decay_count
        logger.info(f"Curation: {decay_count} nodes decayed.")

        # Step 2: Detect contradictions
        logger.info("Curation: detecting contradictions...")
        contradictions = detect_contradictions(graph)
        report.contradictions_found = len(contradictions)
        logger.info(f"Curation: {len(contradictions)} potential contradiction(s) found.")

        # Step 3: Resolve contradictions via LLM (if available)
        resolved = 0
        for entity, node_a, node_b in contradictions:
            resolution = self._resolve_contradiction(entity, node_a, node_b)
            if resolution is not None:
                report.details.append(resolution)
                resolved += 1
        report.contradictions_resolved = resolved

        # Step 4: Detect gaps
        logger.info("Curation: detecting knowledge gaps...")
        gaps = detect_gaps(graph)
        report.gaps_found = len(gaps)
        for gap in gaps:
            report.details.append({"type": "gap", **gap})

        # Step 5: Detect bridges
        logger.info("Curation: detecting bridge nodes...")
        bridges = detect_bridges(graph)
        report.bridges_found = len(bridges)
        for bridge in bridges:
            report.details.append({
                "type": "bridge",
                "node_id": bridge.id,
                "node_label": bridge.label,
                "description": f"Node '{bridge.label}' is a bridge connecting separate clusters.",
            })

        logger.info(
            f"Curation complete: {decay_count} decayed, "
            f"{len(contradictions)} contradictions ({resolved} resolved), "
            f"{len(gaps)} gaps, {len(bridges)} bridges."
        )

        return report

    def _resolve_contradiction(
        self,
        entity: Node,
        node_a: Node,
        node_b: Node,
    ) -> dict[str, Any] | None:
        """
        Attempt to resolve a contradiction via LLM.

        If no LLM is available, just flag it without resolution.
        Modifies node confidence scores based on LLM judgment.
        """
        result: dict[str, Any] = {
            "type": "contradiction",
            "entity_label": entity.label,
            "node_a_label": node_a.label,
            "node_b_label": node_b.label,
            "resolved": False,
        }

        if self._llm is None:
            logger.info(
                f"Contradiction flagged (no LLM for resolution): "
                f"'{node_a.label}' vs '{node_b.label}' under '{entity.label}'"
            )
            return result

        # Ask LLM to resolve
        user_prompt = CONTRADICTION_RESOLUTION_USER_TEMPLATE.format(
            entity_label=entity.label,
            node_a_label=node_a.label,
            node_a_created=node_a.created_at.isoformat(),
            node_a_confidence=node_a.confidence_score,
            node_b_label=node_b.label,
            node_b_created=node_b.created_at.isoformat(),
            node_b_confidence=node_b.confidence_score,
        )

        try:
            raw_response = self._llm(
                CONTRADICTION_RESOLUTION_SYSTEM_PROMPT,
                user_prompt,
            )
            resolution = self._parse_resolution(raw_response)
        except Exception as e:
            logger.warning(f"LLM contradiction resolution failed: {e}")
            return result

        if resolution is None:
            return result

        # Apply resolution — adjust confidence scores
        kept_label = resolution.get("keep_node_label", "")
        new_kept_conf = resolution.get("new_confidence_for_kept", 0.9)
        new_reduced_conf = resolution.get("new_confidence_for_reduced", 0.3)

        if kept_label == node_a.label:
            node_a.confidence_score = min(1.0, max(0.0, new_kept_conf))
            node_b.confidence_score = min(1.0, max(0.0, new_reduced_conf))
        elif kept_label == node_b.label:
            node_b.confidence_score = min(1.0, max(0.0, new_kept_conf))
            node_a.confidence_score = min(1.0, max(0.0, new_reduced_conf))
        else:
            logger.warning(f"LLM resolution referenced unknown label: {kept_label!r}")
            return result

        result["resolved"] = True
        result["reasoning"] = resolution.get("reasoning", "")
        result["kept_label"] = kept_label

        logger.info(
            f"Contradiction resolved: kept '{kept_label}', "
            f"reason: {resolution.get('reasoning', 'n/a')}"
        )

        return result

    def _parse_resolution(self, response: str) -> dict[str, Any] | None:
        """Parse JSON from LLM contradiction resolution response."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
            if isinstance(data, dict) and "keep_node_label" in data:
                return data
        except json.JSONDecodeError:
            pass

        return None
