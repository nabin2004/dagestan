"""Tests for dagestan.graph.operations — Graph intelligence layer."""

from datetime import datetime, timedelta, timezone

import pytest

from dagestan.graph.operations import (
    apply_decay,
    compute_centrality,
    detect_bridges,
    detect_contradictions,
    detect_gaps,
)
from dagestan.graph.schema import Edge, EdgeType, Node, NodeType
from dagestan.graph.temporal_graph import TemporalGraph


@pytest.fixture
def graph_with_contradiction():
    """Graph where a user has two conflicting preferences."""
    g = TemporalGraph()
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 14, tzinfo=timezone.utc)

    user = Node(type=NodeType.ENTITY, label="User", id="user", created_at=t1)
    pref_a = Node(
        type=NodeType.PREFERENCE,
        label="loves coffee",
        id="pref_a",
        created_at=t1,
        confidence_score=0.9,
    )
    pref_b = Node(
        type=NodeType.PREFERENCE,
        label="hates coffee",
        id="pref_b",
        created_at=t2,
        confidence_score=1.0,
    )

    g.add_node(user)
    g.add_node(pref_a)
    g.add_node(pref_b)

    g.add_edge(Edge(source_id="user", target_id="pref_a", type=EdgeType.HAS_PREFERENCE, id="e1"))
    g.add_edge(Edge(source_id="user", target_id="pref_b", type=EdgeType.HAS_PREFERENCE, id="e2"))

    return g


@pytest.fixture
def graph_for_decay():
    """Graph with nodes at different ages."""
    g = TemporalGraph()
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    old = now - timedelta(days=30)
    recent = now - timedelta(days=1)

    g.add_node(Node(
        type=NodeType.EVENT,
        label="Old event",
        id="old",
        created_at=old,
        last_reinforced=old,
        decay_rate=0.05,
    ))
    g.add_node(Node(
        type=NodeType.CONCEPT,
        label="Stable concept",
        id="stable",
        created_at=old,
        last_reinforced=recent,
        decay_rate=0.01,
    ))
    g.add_node(Node(
        type=NodeType.GOAL,
        label="Active goal",
        id="active",
        created_at=recent,
        last_reinforced=recent,
        decay_rate=0.01,
    ))

    return g, now


class TestContradictionDetection:
    def test_finds_contradiction(self, graph_with_contradiction):
        contradictions = detect_contradictions(graph_with_contradiction)
        assert len(contradictions) == 1

        entity, node_a, node_b = contradictions[0]
        assert entity.label == "User"
        labels = {node_a.label, node_b.label}
        assert labels == {"loves coffee", "hates coffee"}

    def test_no_contradiction_when_different_types(self):
        g = TemporalGraph()
        user = Node(type=NodeType.ENTITY, label="User", id="user")
        pref = Node(type=NodeType.PREFERENCE, label="likes tea", id="pref")
        goal = Node(type=NodeType.GOAL, label="drink more tea", id="goal")

        g.add_node(user)
        g.add_node(pref)
        g.add_node(goal)
        g.add_edge(Edge(source_id="user", target_id="pref", type=EdgeType.HAS_PREFERENCE))
        g.add_edge(Edge(source_id="user", target_id="goal", type=EdgeType.WANTS))

        contradictions = detect_contradictions(g)
        assert len(contradictions) == 0

    def test_no_contradiction_when_low_confidence(self, graph_with_contradiction):
        # Make one preference very low confidence (already decayed)
        node = graph_with_contradiction.get_node("pref_a")
        node.confidence_score = 0.05

        contradictions = detect_contradictions(graph_with_contradiction)
        assert len(contradictions) == 0

    def test_empty_graph(self):
        g = TemporalGraph()
        assert detect_contradictions(g) == []


class TestTemporalDecay:
    def test_decay_reduces_old_node_confidence(self, graph_for_decay):
        graph, now = graph_for_decay
        old_node = graph.get_node("old")
        original_conf = old_node.confidence_score

        count = apply_decay(graph, current_time=now)

        assert count > 0
        assert old_node.confidence_score < original_conf

    def test_recent_node_barely_decays(self, graph_for_decay):
        graph, now = graph_for_decay
        active = graph.get_node("active")
        original_conf = active.confidence_score

        apply_decay(graph, current_time=now)

        # 1 day with 0.01 rate: exp(-0.01 * 1) ≈ 0.99
        assert active.confidence_score > 0.98

    def test_decay_respects_min_confidence(self):
        g = TemporalGraph()
        very_old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        g.add_node(Node(
            type=NodeType.EVENT,
            label="Ancient event",
            id="ancient",
            created_at=very_old,
            last_reinforced=very_old,
            decay_rate=0.1,
        ))

        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        apply_decay(g, current_time=now, min_confidence=0.01)

        ancient = g.get_node("ancient")
        assert ancient.confidence_score >= 0.01

    def test_decay_updates_edge_confidence(self):
        g = TemporalGraph()
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)

        g.add_node(Node(
            type=NodeType.ENTITY, label="A", id="a",
            created_at=old, last_reinforced=old, decay_rate=0.05,
        ))
        g.add_node(Node(
            type=NodeType.ENTITY, label="B", id="b",
            created_at=old, last_reinforced=old, decay_rate=0.05,
        ))
        g.add_edge(Edge(source_id="a", target_id="b", type=EdgeType.RELATES_TO, id="e1"))

        apply_decay(g, current_time=now)

        edge = g.get_edge("e1")
        assert edge.confidence_score < 1.0


class TestCentrality:
    def test_hub_node_has_highest_centrality(self):
        g = TemporalGraph()
        g.add_node(Node(type=NodeType.ENTITY, label="Hub", id="hub"))
        for i in range(5):
            nid = f"leaf_{i}"
            g.add_node(Node(type=NodeType.CONCEPT, label=f"Leaf {i}", id=nid))
            g.add_edge(Edge(source_id="hub", target_id=nid, type=EdgeType.RELATES_TO))

        centrality = compute_centrality(g)
        hub_score = centrality["hub"]
        for i in range(5):
            assert hub_score >= centrality[f"leaf_{i}"]

    def test_empty_graph(self):
        g = TemporalGraph()
        assert compute_centrality(g) == {}


class TestGapDetection:
    def test_detects_isolated_entity(self):
        g = TemporalGraph()
        g.add_node(Node(type=NodeType.ENTITY, label="Lonely", id="lonely"))

        gaps = detect_gaps(g)
        assert len(gaps) == 1
        assert gaps[0]["gap_type"] == "no_outgoing_edges"

    def test_detects_missing_preferences(self):
        g = TemporalGraph()
        g.add_node(Node(type=NodeType.ENTITY, label="User", id="user"))
        g.add_node(Node(type=NodeType.GOAL, label="Get internship", id="goal"))
        g.add_edge(Edge(source_id="user", target_id="goal", type=EdgeType.WANTS))

        gaps = detect_gaps(g)
        gap_types = [gap["gap_type"] for gap in gaps]
        assert "missing_preferences" in gap_types

    def test_no_gaps_for_complete_entity(self):
        g = TemporalGraph()
        g.add_node(Node(type=NodeType.ENTITY, label="User", id="user"))
        g.add_node(Node(type=NodeType.GOAL, label="Build app", id="goal"))
        g.add_node(Node(type=NodeType.PREFERENCE, label="Likes Python", id="pref"))
        g.add_edge(Edge(source_id="user", target_id="goal", type=EdgeType.WANTS))
        g.add_edge(Edge(source_id="user", target_id="pref", type=EdgeType.HAS_PREFERENCE))

        gaps = detect_gaps(g)
        # Should have no "missing" gaps (might have under_characterized if in-degree logic triggers)
        missing_gaps = [g for g in gaps if g["gap_type"] in ("missing_preferences", "missing_goals")]
        assert len(missing_gaps) == 0


class TestBridgeDetection:
    def test_detects_bridge_node(self):
        g = TemporalGraph()
        # Two clusters connected by a bridge
        g.add_node(Node(type=NodeType.ENTITY, label="A", id="a"))
        g.add_node(Node(type=NodeType.ENTITY, label="B", id="b"))
        g.add_node(Node(type=NodeType.ENTITY, label="Bridge", id="bridge"))
        g.add_node(Node(type=NodeType.ENTITY, label="C", id="c"))
        g.add_node(Node(type=NodeType.ENTITY, label="D", id="d"))

        # Cluster 1: A -- B -- Bridge
        g.add_edge(Edge(source_id="a", target_id="b", type=EdgeType.RELATES_TO))
        g.add_edge(Edge(source_id="b", target_id="bridge", type=EdgeType.RELATES_TO))
        # Cluster 2: Bridge -- C -- D
        g.add_edge(Edge(source_id="bridge", target_id="c", type=EdgeType.RELATES_TO))
        g.add_edge(Edge(source_id="c", target_id="d", type=EdgeType.RELATES_TO))

        bridges = detect_bridges(g)
        bridge_ids = {b.id for b in bridges}
        assert "bridge" in bridge_ids

    def test_no_bridges_in_fully_connected(self):
        g = TemporalGraph()
        ids = ["a", "b", "c"]
        for nid in ids:
            g.add_node(Node(type=NodeType.ENTITY, label=nid, id=nid))
        # Triangle — no bridges
        g.add_edge(Edge(source_id="a", target_id="b", type=EdgeType.RELATES_TO))
        g.add_edge(Edge(source_id="b", target_id="c", type=EdgeType.RELATES_TO))
        g.add_edge(Edge(source_id="c", target_id="a", type=EdgeType.RELATES_TO))

        bridges = detect_bridges(g)
        assert len(bridges) == 0

    def test_small_graph(self):
        g = TemporalGraph()
        g.add_node(Node(type=NodeType.ENTITY, label="A", id="a"))
        g.add_node(Node(type=NodeType.ENTITY, label="B", id="b"))
        # Less than 3 nodes
        assert detect_bridges(g) == []
