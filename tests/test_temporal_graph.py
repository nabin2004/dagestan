"""Tests for dagestan.graph.temporal_graph — Core graph data structure."""

import json
import tempfile
from pathlib import Path

import pytest

from dagestan.graph.schema import Edge, EdgeType, Node, NodeType
from dagestan.graph.temporal_graph import TemporalGraph


@pytest.fixture
def graph():
    """Empty graph."""
    return TemporalGraph()


@pytest.fixture
def populated_graph():
    """Graph with a few nodes and edges."""
    g = TemporalGraph()
    alice = g.add_node(Node(type=NodeType.ENTITY, label="Alice", id="alice"))
    coffee = g.add_node(Node(type=NodeType.PREFERENCE, label="Loves coffee", id="coffee"))
    startup = g.add_node(Node(type=NodeType.GOAL, label="Build startup", id="startup"))

    g.add_edge(Edge(source_id="alice", target_id="coffee", type=EdgeType.HAS_PREFERENCE, id="e1"))
    g.add_edge(Edge(source_id="alice", target_id="startup", type=EdgeType.WANTS, id="e2"))

    return g


class TestNodeOperations:
    def test_add_and_get_node(self, graph):
        node = Node(type=NodeType.ENTITY, label="Test", id="test1")
        graph.add_node(node)
        assert graph.get_node("test1") is node
        assert graph.node_count == 1

    def test_get_nonexistent_node(self, graph):
        assert graph.get_node("nope") is None

    def test_get_nodes_by_type(self, populated_graph):
        entities = populated_graph.get_nodes_by_type(NodeType.ENTITY)
        assert len(entities) == 1
        assert entities[0].label == "Alice"

    def test_get_nodes_by_label(self, populated_graph):
        matches = populated_graph.get_nodes_by_label("coffee")
        assert len(matches) == 1
        assert matches[0].id == "coffee"

        # Case-insensitive
        matches = populated_graph.get_nodes_by_label("COFFEE")
        assert len(matches) == 1

    def test_remove_node(self, populated_graph):
        assert populated_graph.node_count == 3
        assert populated_graph.edge_count == 2

        # Removing Alice should also remove her edges
        assert populated_graph.remove_node("alice") is True
        assert populated_graph.node_count == 2
        assert populated_graph.edge_count == 0

    def test_remove_nonexistent_node(self, graph):
        assert graph.remove_node("nope") is False

    def test_nodes_property(self, populated_graph):
        nodes = populated_graph.nodes
        assert len(nodes) == 3


class TestEdgeOperations:
    def test_add_edge(self, graph):
        graph.add_node(Node(type=NodeType.ENTITY, label="A", id="a"))
        graph.add_node(Node(type=NodeType.ENTITY, label="B", id="b"))
        edge = Edge(source_id="a", target_id="b", type=EdgeType.RELATES_TO)
        graph.add_edge(edge)
        assert graph.edge_count == 1

    def test_add_edge_missing_source(self, graph):
        graph.add_node(Node(type=NodeType.ENTITY, label="B", id="b"))
        edge = Edge(source_id="missing", target_id="b", type=EdgeType.RELATES_TO)
        with pytest.raises(ValueError, match="Source node"):
            graph.add_edge(edge)

    def test_add_edge_missing_target(self, graph):
        graph.add_node(Node(type=NodeType.ENTITY, label="A", id="a"))
        edge = Edge(source_id="a", target_id="missing", type=EdgeType.RELATES_TO)
        with pytest.raises(ValueError, match="Target node"):
            graph.add_edge(edge)

    def test_get_edges_by_node(self, populated_graph):
        edges = populated_graph.get_edges(node_id="alice")
        assert len(edges) == 2

    def test_get_edges_by_direction(self, populated_graph):
        out = populated_graph.get_edges(node_id="alice", direction="outgoing")
        assert len(out) == 2

        inc = populated_graph.get_edges(node_id="alice", direction="incoming")
        assert len(inc) == 0

        inc_coffee = populated_graph.get_edges(node_id="coffee", direction="incoming")
        assert len(inc_coffee) == 1

    def test_get_edges_by_type(self, populated_graph):
        pref_edges = populated_graph.get_edges(edge_type=EdgeType.HAS_PREFERENCE)
        assert len(pref_edges) == 1

    def test_remove_edge(self, populated_graph):
        assert populated_graph.remove_edge("e1") is True
        assert populated_graph.edge_count == 1
        assert populated_graph.remove_edge("e1") is False  # Already removed


class TestNeighbors:
    def test_neighbors(self, populated_graph):
        neighbors = populated_graph.neighbors("alice")
        labels = {n.label for n in neighbors}
        assert labels == {"Loves coffee", "Build startup"}

    def test_neighbors_direction(self, populated_graph):
        out_neighbors = populated_graph.neighbors("alice", direction="outgoing")
        assert len(out_neighbors) == 2

        in_neighbors = populated_graph.neighbors("alice", direction="incoming")
        assert len(in_neighbors) == 0


class TestSnapshotAndPersistence:
    def test_snapshot_roundtrip(self, populated_graph):
        snapshot = populated_graph.snapshot()
        assert snapshot["node_count"] == 3
        assert snapshot["edge_count"] == 2

        new_graph = TemporalGraph()
        new_graph.load_snapshot(snapshot)
        assert new_graph.node_count == 3
        assert new_graph.edge_count == 2

        # Verify data integrity
        alice = new_graph.get_node("alice")
        assert alice is not None
        assert alice.label == "Alice"

    def test_file_save_load(self, populated_graph):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_graph.json"
            populated_graph.save_to_file(path)

            assert path.exists()
            # Verify it's valid JSON
            with open(path) as f:
                data = json.load(f)
            assert data["node_count"] == 3

            # Load into new graph
            new_graph = TemporalGraph()
            new_graph.load_from_file(path)
            assert new_graph.node_count == 3
            assert new_graph.edge_count == 2

    def test_load_nonexistent_file(self, graph):
        with pytest.raises(FileNotFoundError):
            graph.load_from_file("/tmp/nonexistent_dagestan_graph.json")

    def test_repr(self, populated_graph):
        r = repr(populated_graph)
        assert "nodes=3" in r
        assert "edges=2" in r
