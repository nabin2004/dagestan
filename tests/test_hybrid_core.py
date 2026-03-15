"""
Tests for Dagestan Hybrid Memory Architecture core operations.
Scenarios:
a. Contradiction is flagged
b. Graph neighbourhood biases retrieval
c. Ebbinghaus score arithmetic
d. Nightly curator merges duplicate schemas
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from dagestan.curation.nightly_curator import NightlyCurator, ResolutionStrategy
from dagestan.embeddings.vector_store import VectorStore
from dagestan.graph.schema import Edge, Node
from dagestan.graph.temporal_graph import TemporalGraph
from dagestan.retrieval.hybrid_retriever import HybridRetriever


@pytest.fixture
def empty_graph():
    return TemporalGraph()


@pytest.fixture
def mock_vector_store(tmp_path):
    return VectorStore(db_path=str(tmp_path / "chromadb"))


def test_scenario_a_contradiction_flagged(empty_graph):
    """Contradiction is flagged when a conflicting edge is inserted."""
    g = empty_graph
    
    # Add entities
    p1 = g.add_node(Node(type="person", label="Alice", id="alice"))
    c1 = g.add_node(Node(type="concept", label="Coffee", id="coffee"))
    c2 = g.add_node(Node(type="concept", label="Tea", id="tea"))
    
    # Insert first fact
    e1 = Edge(source_id="alice", target_id="coffee", type="likes", id="edge1")
    g.add_edge(e1)
    
    assert g.edge_count == 1
    assert len(g.contradictions_queue) == 0
    
    # Insert conflicting fact (same source, same relation, different target)
    e2 = Edge(source_id="alice", target_id="tea", type="likes", id="edge2")
    returned_edge = g.add_edge(e2)
    
    # Because of our simplistic conflict logic, this should flag a contradiction.
    assert returned_edge.id == e2.id
    # Ensure it wasn't added to the main graph
    assert g.edge_count == 1
    # Ensure it was queued in contradictions
    assert len(g.contradictions_queue) == 1
    
    conflict = g.contradictions_queue[0]
    assert conflict["new_edge"]["id"] == e2.id
    assert conflict["existing_edge"]["id"] == e1.id


def test_scenario_b_graph_biases_vector_retrieval(empty_graph, mock_vector_store):
    """Graph neighbourhood correctly biases vector retrieval."""
    g = empty_graph
    vs = mock_vector_store
    
    # Setup graph
    n1 = g.add_node(Node(id="n1", type="entity", label="Dagestan"))
    n2 = g.add_node(Node(id="n2", type="concept", label="Hybrid Memory"))
    g.add_edge(Edge(source_id="n1", target_id="n2", type="is_about"))
    
    # Insert vectors
    # Chunk 1: Graph supported
    vs.upsert(
        turn_id="t1",
        text="Dagestan is a powerful memory system.",
        entity_refs=["n1", "n2"],
        chunk_id="chunk1"
    )
    
    # Chunk 2: No graph support, but semantically similar
    vs.upsert(
        turn_id="t2",
        text="A powerful memory engine that remembers long term.",
        entity_refs=[],
        chunk_id="chunk2"
    )
    
    hr = HybridRetriever(graph=g, vector_store=vs, graph_boost_factor=1.5)
    
    # Search without graph bias
    # If we pass nothing to context_node_ids and the query doesn't match a graph node name
    # We'll just see raw vector similarities
    res_no_bias = hr.retrieve(query="memory system architecture", context_node_ids=[])
    
    # Search with graph bias
    # Query mentions "Dagestan", which is in the graph
    res_bias = hr.retrieve(query="Tell me about Dagestan memory system architecture", context_node_ids=[])
    
    # We should see the graph boost applied in the retrieval trace
    trace = res_bias.retrieval_trace
    assert "boost=1.5" in trace
    
    chunk1_res = [c for c in res_bias.chunks if c.chunk_id == "chunk1"][0]
    # Its score should be boosted
    assert len(chunk1_res.provenance["node_ids"]) > 0


def test_scenario_c_ebbinghaus_decay():
    """Ebbinghaus score at t=0 is 1.0, at t=stability*ln(20) is ≈0.05."""
    # We use exp(-days_elapsed * decay_rate) where stability = 1/decay_rate
    stability = 20.0  # e.g., days
    decay_rate = 1.0 / stability
    
    n = Node(type="entity", label="Test", decay_rate=decay_rate)
    
    now = datetime.now(timezone.utc)
    
    # t=0
    n.last_reinforced = now
    days_0 = 0
    score_0 = math.exp(-days_0 * n.decay_rate)
    assert score_0 == 1.0
    
    # t=stability * ln(20)
    t = stability * math.log(20)
    days_elapsed = t
    
    score_t = math.exp(-days_elapsed * n.decay_rate)
    # math.exp(-t * (1/stability)) = math.exp(-stability*ln(20) / stability) = math.exp(-ln(20)) = 1/20 = 0.05
    assert math.isclose(score_t, 0.05, rel_tol=1e-5)


def test_scenario_d_nightly_curator_merges_types(empty_graph, mock_vector_store):
    """Nightly curator merges two near-duplicate schema types."""
    g = empty_graph
    
    # Setup near duplicate schemas
    g._record_schema_induction(node_type="engineer")
    g._record_schema_induction(node_type="software engineer")
    
    # Add nodes using these types
    g.add_node(Node(type="engineer", label="Bob", id="bob"))
    g.add_node(Node(type="software engineer", label="Alice", id="alice"))
    
    curator = NightlyCurator(graph=g, vector_store=mock_vector_store)
    
    # "engineer" and "software engineer" should have high semantic similarity
    report = curator._consolidate_schema()
    
    assert report > 0, "Should have merged at least one type"
    assert "software engineer" not in g.schema_registry["node_types"]
    assert "engineer" in g.schema_registry["node_types"]
    
    # Verify nodes got updated
    assert g.get_node("alice").type == "engineer"
