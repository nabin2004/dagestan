"""
dagestan.graph.temporal_graph
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Core temporal graph data structure.

Provides CRUD operations on nodes and edges, full-graph snapshots
with timestamps, and JSON persistence for v0.1.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import Edge, EdgeType, Node, NodeType


class TemporalGraph:
    """
    A typed temporal knowledge graph.

    Stores nodes and edges in memory with full temporal metadata.
    Supports snapshots (serialized graph state at a point in time)
    and JSON-based persistence.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        # Adjacency index: node_id → list of edge_ids (outgoing + incoming)
        self._adj: dict[str, list[str]] = {}

    # ── Node operations ─────────────────────────────────────────────

    def add_node(self, node: Node) -> Node:
        """Add a node to the graph. Returns the node (for chaining)."""
        self._nodes[node.id] = node
        if node.id not in self._adj:
            self._adj[node.id] = []
        return node

    def get_node(self, node_id: str) -> Node | None:
        """Retrieve a node by ID, or None if not found."""
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> list[Node]:
        """Return all nodes of a given type."""
        return [n for n in self._nodes.values() if n.type == node_type]

    def get_nodes_by_label(self, label: str) -> list[Node]:
        """Return all nodes whose label contains the given string (case-insensitive)."""
        label_lower = label.lower()
        return [n for n in self._nodes.values() if label_lower in n.label.lower()]

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its connected edges. Returns True if removed."""
        if node_id not in self._nodes:
            return False

        # Remove all connected edges
        connected_edge_ids = list(self._adj.get(node_id, []))
        for edge_id in connected_edge_ids:
            self._remove_edge_from_adj(edge_id)
            self._edges.pop(edge_id, None)

        del self._nodes[node_id]
        self._adj.pop(node_id, None)
        return True

    @property
    def nodes(self) -> list[Node]:
        """All nodes in the graph."""
        return list(self._nodes.values())

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # ── Edge operations ─────────────────────────────────────────────

    def add_edge(self, edge: Edge) -> Edge:
        """
        Add an edge to the graph.

        Both source and target nodes must already exist.
        Raises ValueError if either node is missing.
        """
        if edge.source_id not in self._nodes:
            raise ValueError(
                f"Source node {edge.source_id!r} not found in graph"
            )
        if edge.target_id not in self._nodes:
            raise ValueError(
                f"Target node {edge.target_id!r} not found in graph"
            )

        self._edges[edge.id] = edge
        self._adj.setdefault(edge.source_id, []).append(edge.id)
        self._adj.setdefault(edge.target_id, []).append(edge.id)
        return edge

    def get_edge(self, edge_id: str) -> Edge | None:
        """Retrieve an edge by ID."""
        return self._edges.get(edge_id)

    def get_edges(
        self,
        node_id: str | None = None,
        edge_type: EdgeType | None = None,
        direction: str = "both",  # "outgoing", "incoming", "both"
    ) -> list[Edge]:
        """
        Get edges, optionally filtered by connected node and/or type.

        Args:
            node_id: If set, only edges connected to this node.
            edge_type: If set, only edges of this type.
            direction: "outgoing", "incoming", or "both" (relative to node_id).
        """
        if node_id is not None:
            edge_ids = self._adj.get(node_id, [])
            candidates = [self._edges[eid] for eid in edge_ids if eid in self._edges]

            if direction == "outgoing":
                candidates = [e for e in candidates if e.source_id == node_id]
            elif direction == "incoming":
                candidates = [e for e in candidates if e.target_id == node_id]
        else:
            candidates = list(self._edges.values())

        if edge_type is not None:
            candidates = [e for e in candidates if e.type == edge_type]

        return candidates

    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge. Returns True if removed."""
        if edge_id not in self._edges:
            return False
        self._remove_edge_from_adj(edge_id)
        del self._edges[edge_id]
        return True

    @property
    def edges(self) -> list[Edge]:
        """All edges in the graph."""
        return list(self._edges.values())

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    # ── Neighbors ───────────────────────────────────────────────────

    def neighbors(self, node_id: str, direction: str = "both") -> list[Node]:
        """
        Get neighboring nodes.

        Args:
            node_id: The node to find neighbors for.
            direction: "outgoing", "incoming", or "both".
        """
        edges = self.get_edges(node_id=node_id, direction=direction)
        neighbor_ids: set[str] = set()
        for e in edges:
            if e.source_id == node_id:
                neighbor_ids.add(e.target_id)
            if e.target_id == node_id:
                neighbor_ids.add(e.source_id)

        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    # ── Snapshot / Persistence ──────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """
        Create a full serialized snapshot of the current graph state.

        Returns a dict that can be written directly to JSON.
        """
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
        }

    def load_snapshot(self, data: dict[str, Any]) -> None:
        """
        Restore graph state from a snapshot dict.

        Replaces all current data.
        """
        self._nodes.clear()
        self._edges.clear()
        self._adj.clear()

        for node_data in data.get("nodes", []):
            node = Node.from_dict(node_data)
            self._nodes[node.id] = node
            self._adj.setdefault(node.id, [])

        for edge_data in data.get("edges", []):
            edge = Edge.from_dict(edge_data)
            self._edges[edge.id] = edge
            self._adj.setdefault(edge.source_id, []).append(edge.id)
            self._adj.setdefault(edge.target_id, []).append(edge.id)

    def save_to_file(self, path: str | Path) -> None:
        """Save current graph state to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.snapshot(), f, indent=2)

    def load_from_file(self, path: str | Path) -> None:
        """Load graph state from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"No graph file at {path}")
        with open(path) as f:
            data = json.load(f)
        self.load_snapshot(data)

    # ── Internal helpers ────────────────────────────────────────────

    def _remove_edge_from_adj(self, edge_id: str) -> None:
        """Remove an edge ID from all adjacency lists."""
        edge = self._edges.get(edge_id)
        if edge is None:
            return
        for nid in (edge.source_id, edge.target_id):
            adj_list = self._adj.get(nid, [])
            if edge_id in adj_list:
                adj_list.remove(edge_id)

    # ── Dunder ──────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"TemporalGraph(nodes={self.node_count}, edges={self.edge_count})"

    def __len__(self) -> int:
        return self.node_count
