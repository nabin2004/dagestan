"""
dagestan.retrieval.hybrid_retriever
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hybrid retrieval combining temporal graph traversal with vector similarity search.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from dagestan.graph.temporal_graph import TemporalGraph
from dagestan.embeddings.vector_store import VectorStore


class RetrievalChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    provenance: Dict[str, List[str]] = Field(default_factory=lambda: {"node_ids": [], "edge_ids": []})


class SubgraphData(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


class RetrievalResult(BaseModel):
    chunks: List[RetrievalChunk]
    subgraph: SubgraphData
    schema_types_used: List[str]
    retrieval_trace: str


class HybridRetriever:
    """
    Coordinates between TemporalGraph and VectorStore to perform hybrid retrieval.
    """

    def __init__(
        self,
        graph: TemporalGraph,
        vector_store: VectorStore,
        graph_boost_factor: float = 1.5
    ) -> None:
        self.graph = graph
        self.vector_store = vector_store
        self.graph_boost_factor = graph_boost_factor

    def _extract_candidate_entities(self, query: str) -> List[str]:
        """
        Naive entity extraction by substring matching graph nodes' labels against query.
        In a real system, this would use an LLM or NER model.
        """
        q_lower = query.lower()
        candidates = []
        for node in self.graph.nodes:
            if node.label.lower() in q_lower:
                candidates.append(node.id)
        return candidates

    def _get_neighborhood(self, node_ids: List[str], hops: int = 1) -> tuple[List[Any], List[Any]]:
        """Find the 1-2 hop neighborhood of given node IDs."""
        visited_nodes = set(node_ids)
        visited_edges = set()
        
        current_frontier = set(node_ids)
        for _ in range(hops):
            next_frontier = set()
            for nid in current_frontier:
                edges = self.graph.get_edges(node_id=nid)
                for edge in edges:
                    visited_edges.add(edge.id)
                    # Add connected node
                    other_id = edge.target_id if edge.source_id == nid else edge.source_id
                    if other_id not in visited_nodes:
                        visited_nodes.add(other_id)
                        next_frontier.add(other_id)
            current_frontier = next_frontier

        nodes = [self.graph.get_node(nid) for nid in visited_nodes if self.graph.get_node(nid)]
        edges = [self.graph.get_edge(eid) for eid in visited_edges if self.graph.get_edge(eid)]
        return nodes, edges

    def retrieve(
        self,
        query: str,
        context_node_ids: Optional[List[str]] = None,
        top_k: int = 5
    ) -> RetrievalResult:
        """
        Execute hybrid retrieval algorithm.
        """
        # 1. Parse query intent
        extracted_node_ids = self._extract_candidate_entities(query)
        if context_node_ids:
            extracted_node_ids.extend(context_node_ids)
            
        extracted_node_ids = list(set(extracted_node_ids))

        # 2. Graph lookup -> Subgraph
        neighborhood_nodes, neighborhood_edges = self._get_neighborhood(extracted_node_ids, hops=2)
        
        # 3. Collect entity_refs from subgraph
        subgraph_node_ids = {n.id for n in neighborhood_nodes}
        
        # 4 & 5. Vector search + Decay + Graph Boost
        # We query the vector store first
        vector_results = self.vector_store.search(query_text=query, top_k=top_k * 2)
        
        scored_chunks = []
        schema_types_used = set()
        
        for n in neighborhood_nodes:
            schema_types_used.add(n.type)
        for e in neighborhood_edges:
            schema_types_used.add(e.type)
            
        trace_lines = [f"Query: '{query}'"]
        if extracted_node_ids:
            names = [self.graph.get_node(nid).label for nid in extracted_node_ids if self.graph.get_node(nid)]
            trace_lines.append(f"Entity Matches: {', '.join(names)}")
        else:
            trace_lines.append("No explicit entity matches found.")

        for chunk_id, base_score, metadata in vector_results:
            import json
            
            # The lower the distance, the better (cosine distance). We want higher is better.
            # Assuming distance in [0, 2], similarity = 1 - (distance / 2)
            similarity = max(0.0, 1.0 - (base_score / 2.0))
            
            try:
                refs = json.loads(metadata.get("entity_refs", "[]"))
            except Exception:
                refs = []
                
            decay = float(metadata.get("decay_score", 1.0))
            
            # Check overlap with subgraph
            overlap = set(refs).intersection(subgraph_node_ids)
            has_graph_support = len(overlap) > 0
            
            boost = self.graph_boost_factor if has_graph_support else 1.0
            
            final_score = similarity * boost * decay
            
            trace_lines.append(f"- Chunk {chunk_id[:8]}... : sim={similarity:.2f}, boost={boost:.1f}, decay={decay:.2f} -> {final_score:.2f}")
            if has_graph_support:
                trace_lines.append(f"  Graph provenances: {len(overlap)} matching nodes in subgraph.")
                
            scored_chunks.append(
                RetrievalChunk(
                    chunk_id=chunk_id,
                    text=metadata.get("text", f"[No text recovered, chunk {chunk_id}]"), # Text is lost if not in metadata, but we can return chunk_id
                    score=final_score,
                    provenance={"node_ids": list(overlap), "edge_ids": []}
                )
            )

        # Sort and take top_k
        scored_chunks.sort(key=lambda x: x.score, reverse=True)
        top_chunks = scored_chunks[:top_k]
        
        return RetrievalResult(
            chunks=top_chunks,
            subgraph=SubgraphData(
                nodes=[n.to_dict() for n in neighborhood_nodes],
                edges=[e.to_dict() for e in neighborhood_edges]
            ),
            schema_types_used=list(schema_types_used),
            retrieval_trace="\n".join(trace_lines)
        )
