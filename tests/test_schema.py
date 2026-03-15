"""Tests for dagestan.graph.schema — Node and Edge data types."""

from datetime import datetime, timezone

from dagestan.graph.schema import (
    DEFAULT_DECAY_RATES,
    Edge,
    EdgeType,
    Node,
    NodeType,
)


class TestNodeType:
    def test_enum_values(self):
        assert NodeType.ENTITY == "entity"
        assert NodeType.CONCEPT == "concept"
        assert NodeType.EVENT == "event"
        assert NodeType.PREFERENCE == "preference"
        assert NodeType.GOAL == "goal"

    def test_all_types_have_decay_rates(self):
        types = [getattr(NodeType, attr) for attr in dir(NodeType) if not attr.startswith("_")]
        for ntype in types:
            assert ntype in DEFAULT_DECAY_RATES


class TestEdgeType:
    def test_enum_values(self):
        assert EdgeType.RELATES_TO == "relates_to"
        assert EdgeType.CAUSED == "caused"
        assert EdgeType.CONTRADICTS == "contradicts"
        assert EdgeType.HAPPENED_BEFORE == "happened_before"
        assert EdgeType.HAS_PREFERENCE == "has_preference"
        assert EdgeType.WANTS == "wants"


class TestNode:
    def test_create_with_defaults(self):
        node = Node(type=NodeType.ENTITY, label="Alice")
        assert node.type == NodeType.ENTITY
        assert node.label == "Alice"
        assert node.confidence_score == 1.0
        assert node.decay_rate == DEFAULT_DECAY_RATES[NodeType.ENTITY]
        assert node.id  # Should have auto-generated ID
        assert node.created_at is not None

    def test_create_with_custom_values(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        node = Node(
            type=NodeType.GOAL,
            label="Build Dagestan",
            id="custom_id",
            confidence_score=0.8,
            decay_rate=0.05,
            created_at=now,
            source="session_1",
            attributes={"priority": "high"},
        )
        assert node.id == "custom_id"
        assert node.confidence_score == 0.8
        assert node.decay_rate == 0.05
        assert node.source == "session_1"
        assert node.attributes["priority"] == "high"

    def test_serialization_roundtrip(self):
        node = Node(
            type=NodeType.PREFERENCE,
            label="Loves coffee",
            attributes={"strength": "strong"},
            source="test",
        )
        data = node.to_dict()
        restored = Node.from_dict(data)

        assert restored.id == node.id
        assert restored.type == node.type
        assert restored.label == node.label
        assert restored.attributes == node.attributes
        assert restored.confidence_score == node.confidence_score
        assert restored.source == node.source

    def test_reinforce(self):
        node = Node(type=NodeType.ENTITY, label="Bob")
        node.confidence_score = 0.5
        node.reinforce()
        assert node.confidence_score == 0.7  # 0.5 + 0.2
        # Should not exceed 1.0
        node.confidence_score = 0.95
        node.reinforce()
        assert node.confidence_score == 1.0

    def test_repr(self):
        node = Node(type=NodeType.CONCEPT, label="Machine Learning")
        r = repr(node)
        assert "concept" in r
        assert "Machine Learning" in r


class TestEdge:
    def test_create_with_defaults(self):
        edge = Edge(source_id="a", target_id="b", type=EdgeType.RELATES_TO)
        assert edge.source_id == "a"
        assert edge.target_id == "b"
        assert edge.type == EdgeType.RELATES_TO
        assert edge.confidence_score == 1.0
        assert edge.id

    def test_serialization_roundtrip(self):
        edge = Edge(
            source_id="a",
            target_id="b",
            type=EdgeType.CAUSED,
            confidence_score=0.7,
            attributes={"weight": 1},
        )
        data = edge.to_dict()
        restored = Edge.from_dict(data)

        assert restored.id == edge.id
        assert restored.source_id == "a"
        assert restored.target_id == "b"
        assert restored.type == EdgeType.CAUSED
        assert restored.confidence_score == 0.7
        assert restored.attributes == {"weight": 1}
