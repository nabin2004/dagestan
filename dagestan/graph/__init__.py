"""dagestan.graph — Temporal knowledge graph core."""

from .schema import DEFAULT_DECAY_RATES, Edge, EdgeType, Node, NodeType
from .temporal_graph import TemporalGraph

__all__ = [
    "Node",
    "Edge",
    "NodeType",
    "EdgeType",
    "TemporalGraph",
    "DEFAULT_DECAY_RATES",
]
