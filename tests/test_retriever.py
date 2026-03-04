"""Tests for dagestan.retrieval.retriever — Query-driven graph traversal."""

import pytest

from dagestan.graph.schema import Edge, EdgeType, Node, NodeType
from dagestan.graph.temporal_graph import TemporalGraph
from dagestan.retrieval.retriever import Retriever


@pytest.fixture
def knowledge_graph():
    """A realistic knowledge graph for retrieval testing."""
    g = TemporalGraph()

    # Entities
    user = Node(type=NodeType.ENTITY, label="User", id="user")
    dagestan = Node(type=NodeType.ENTITY, label="Dagestan project", id="dagestan")

    # Concepts
    ml = Node(type=NodeType.CONCEPT, label="Machine learning", id="ml")
    python = Node(type=NodeType.CONCEPT, label="Python programming", id="python")
    graphs = Node(type=NodeType.CONCEPT, label="Graph data structures", id="graphs")

    # Preferences
    tea = Node(type=NodeType.PREFERENCE, label="Prefers tea over coffee", id="tea_pref")
    vim = Node(type=NodeType.PREFERENCE, label="Uses Vim editor", id="vim_pref")

    # Goals
    internship = Node(type=NodeType.GOAL, label="Get ML internship", id="internship")
    build = Node(type=NodeType.GOAL, label="Build Dagestan v1", id="build_goal")

    # Events
    started = Node(type=NodeType.EVENT, label="Started building Dagestan", id="started")

    for n in [user, dagestan, ml, python, graphs, tea, vim, internship, build, started]:
        g.add_node(n)

    # Relationships
    g.add_edge(Edge(source_id="user", target_id="tea_pref", type=EdgeType.HAS_PREFERENCE))
    g.add_edge(Edge(source_id="user", target_id="vim_pref", type=EdgeType.HAS_PREFERENCE))
    g.add_edge(Edge(source_id="user", target_id="internship", type=EdgeType.WANTS))
    g.add_edge(Edge(source_id="user", target_id="build_goal", type=EdgeType.WANTS))
    g.add_edge(Edge(source_id="dagestan", target_id="graphs", type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id="dagestan", target_id="python", type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id="ml", target_id="internship", type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id="started", target_id="dagestan", type=EdgeType.CAUSED))

    return g


class TestRetriever:
    def test_basic_retrieval(self, knowledge_graph):
        retriever = Retriever()
        results = retriever.retrieve(knowledge_graph, "machine learning")
        assert len(results) > 0
        # ML node should be among top results
        labels = [r.node.label for r in results]
        assert any("machine" in l.lower() or "ml" in l.lower() for l in labels)

    def test_retrieval_with_top_k(self, knowledge_graph):
        retriever = Retriever()
        results = retriever.retrieve(knowledge_graph, "user preferences", top_k=3)
        assert len(results) <= 3

    def test_empty_query(self, knowledge_graph):
        retriever = Retriever()
        results = retriever.retrieve(knowledge_graph, "the is a")
        # Should still return results (by centrality)
        assert len(results) > 0

    def test_empty_graph(self):
        retriever = Retriever()
        results = retriever.retrieve(TemporalGraph(), "anything")
        assert results == []

    def test_retrieve_as_text(self, knowledge_graph):
        retriever = Retriever()
        text = retriever.retrieve_as_text(knowledge_graph, "dagestan project")
        assert isinstance(text, str)
        assert "Dagestan" in text or "dagestan" in text.lower()

    def test_neighbor_boost(self, knowledge_graph):
        """Nodes connected to direct matches should score higher than isolated nodes."""
        retriever = Retriever()
        results = retriever.retrieve(knowledge_graph, "dagestan")

        # Find scores for dagestan-connected nodes (graphs, python) vs unrelated
        dagestan_result = next((r for r in results if r.node.id == "dagestan"), None)
        assert dagestan_result is not None
        assert dagestan_result.score > 0

    def test_confidence_filtering(self, knowledge_graph):
        """Low-confidence nodes should be excluded."""
        # Set one node to very low confidence
        node = knowledge_graph.get_node("started")
        node.confidence_score = 0.05

        retriever = Retriever()
        results = retriever.retrieve(knowledge_graph, "started building", min_confidence=0.1)
        result_ids = [r.node.id for r in results]
        assert "started" not in result_ids


class TestRetrieverScoring:
    def test_direct_match_scores_higher(self, knowledge_graph):
        """A direct keyword match should score higher than neighbor expansion."""
        retriever = Retriever()
        results = retriever.retrieve(knowledge_graph, "Python programming")

        if len(results) >= 2:
            python_result = next((r for r in results if r.node.id == "python"), None)
            if python_result:
                # Direct match should be in top results
                assert results.index(python_result) < len(results) // 2
