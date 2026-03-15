"""
dagestan.graph.schema
~~~~~~~~~~~~~~~~~~~~~

Core data types for the temporal knowledge graph.

Defines node types, edge types, and their dataclass representations
with full temporal metadata. This is the minimal ontology — just enough
structure for intelligent operations without becoming brittle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class NodeType:
    """Classification of knowledge nodes in the graph."""

    ENTITY = "entity"  # Person, place, object
    CONCEPT = "concept"  # Idea, topic, domain
    EVENT = "event"  # Something that happened
    PREFERENCE = "preference"  # Like, dislike, value
    GOAL = "goal"  # What someone wants


class EdgeType:
    """Classification of relationships between nodes."""

    RELATES_TO = "relates_to"  # General semantic relationship
    CAUSED = "caused"  # Causal link
    CONTRADICTS = "contradicts"  # Two nodes in conflict
    HAPPENED_BEFORE = "happened_before"  # Temporal ordering
    HAS_PREFERENCE = "has_preference"  # Entity holds a preference
    WANTS = "wants"  # Entity has a goal


# Default decay rates per node type.
# Higher value = faster confidence loss per day.
DEFAULT_DECAY_RATES: dict[str, float] = {
    NodeType.ENTITY: 0.005,  # Very slow — entities persist
    NodeType.CONCEPT: 0.01,  # Very slow — domain knowledge persists
    NodeType.EVENT: 0.05,  # Fast — old events lose relevance
    NodeType.PREFERENCE: 0.02,  # Medium — preferences shift over time
    NodeType.GOAL: 0.01,  # Slow — goals are relatively stable
}


def _now() -> datetime:
    """UTC-aware current timestamp."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    """Generate a compact unique ID."""
    return uuid.uuid4().hex[:12]


@dataclass
class Node:
    """
    A single knowledge node in the temporal graph.

    Attributes:
        id: Unique identifier.
        type: What kind of knowledge this represents.
        label: Human-readable name / summary.
        attributes: Arbitrary key-value metadata.
        created_at: When this knowledge entered the graph.
        last_reinforced: When it was last confirmed or referenced.
        confidence_score: 0.0–1.0, degrades over time unless reinforced.
        decay_rate: How fast confidence drops (per day).
        source: Which conversation or session produced this node.
    """

    type: str
    label: str
    id: str = field(default_factory=_new_id)
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    last_reinforced: datetime = field(default_factory=_now)
    confidence_score: float = 1.0
    decay_rate: float | None = None  # None → use DEFAULT_DECAY_RATES
    source: str = ""

    def __post_init__(self) -> None:
        if self.decay_rate is None:
            self.decay_rate = DEFAULT_DECAY_RATES.get(self.type, 0.02)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
            "last_reinforced": self.last_reinforced.isoformat(),
            "confidence_score": self.confidence_score,
            "decay_rate": self.decay_rate,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        """Deserialize from a plain dict."""
        return cls(
            id=data["id"],
            type=data["type"],
            label=data["label"],
            attributes=data.get("attributes", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_reinforced=datetime.fromisoformat(data["last_reinforced"]),
            confidence_score=data.get("confidence_score", 1.0),
            decay_rate=data.get("decay_rate"),
            source=data.get("source", ""),
        )

    def reinforce(self, timestamp: datetime | None = None) -> None:
        """Mark this node as recently confirmed — resets decay clock."""
        self.last_reinforced = timestamp or _now()
        # Partial confidence recovery on reinforcement
        self.confidence_score = min(1.0, self.confidence_score + 0.2)

    def __repr__(self) -> str:
        return (
            f"Node(id={self.id!r}, type={self.type}, "
            f"label={self.label!r}, confidence={self.confidence_score:.2f})"
        )


@dataclass
class Edge:
    """
    A typed, temporal relationship between two nodes.

    Attributes:
        id: Unique identifier.
        source_id: ID of the origin node.
        target_id: ID of the destination node.
        type: What kind of relationship this represents.
        created_at: When this relationship was established.
        confidence_score: 0.0–1.0, inherits decay from connected nodes.
        attributes: Arbitrary key-value metadata on the edge.
    """

    source_id: str
    target_id: str
    type: str
    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=_now)
    confidence_score: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type,
            "created_at": self.created_at.isoformat(),
            "confidence_score": self.confidence_score,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        """Deserialize from a plain dict."""
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            type=data["type"],
            created_at=datetime.fromisoformat(data["created_at"]),
            confidence_score=data.get("confidence_score", 1.0),
            attributes=data.get("attributes", {}),
        )

    def __repr__(self) -> str:
        return (
            f"Edge(id={self.id!r}, {self.source_id} "
            f"--[{self.type}]--> {self.target_id}, "
            f"confidence={self.confidence_score:.2f})"
        )
