"""
dagestan.curation.nightly_curator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Standalone offline process for memory maintenance and consolidation.
Handles contradiction resolution, Ebbinghaus decay, pruning, and schema consolidation.
"""

import logging
import math
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sentence_transformers import SentenceTransformer

from dagestan.embeddings.vector_store import VectorStore
from dagestan.graph.temporal_graph import TemporalGraph


class ResolutionStrategy(str, Enum):
    KEEP_LATEST = "KEEP_LATEST"
    KEEP_HIGHEST_CONFIDENCE = "KEEP_HIGHEST_CONFIDENCE"
    MERGE = "MERGE"
    SURFACE_TO_USER = "SURFACE_TO_USER"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NightlyCurator:
    """
    Offline curator for maintaining the graph and vector memories.
    """

    def __init__(
        self,
        graph: TemporalGraph,
        vector_store: VectorStore,
        prune_threshold: float = 0.05,
        resolution_strategy: ResolutionStrategy = ResolutionStrategy.KEEP_LATEST,
        model_name: str = "all-MiniLM-L6-v2"
    ):
        self.graph = graph
        self.vector_store = vector_store
        self.prune_threshold = prune_threshold
        self.resolution_strategy = resolution_strategy
        self.model = SentenceTransformer(model_name)

    def run(self) -> Dict[str, Any]:
        """Execute the full nightly curation pipeline."""
        start_time = _now()
        logging.info("Starting Nightly Curator...")

        report = {
            "timestamp": start_time.isoformat(),
            "contradictions_resolved": 0,
            "chunks_pruned": 0,
            "edges_pruned": 0,
            "nodes_pruned": 0,
            "types_merged": 0,
            "decay_stats": {"avg_node_confidence": 0.0, "avg_edge_confidence": 0.0}
        }

        # 1. Contradiction Resolution
        report["contradictions_resolved"] = self._resolve_contradictions()

        # 2. Ebbinghaus Decay & 3. Pruning
        stats = self._apply_decay_and_prune()
        report.update(stats)

        # 4. Schema Consolidation
        report["types_merged"] = self._consolidate_schema()

        logging.info(f"Curation complete: {report}")
        return report

    def _resolve_contradictions(self) -> int:
        resolved_count = 0
        queue = list(self.graph.contradictions_queue)
        self.graph.contradictions_queue.clear()

        for conflict in queue:
            new_edge_data = conflict["new_edge"]
            existing_edge_data = conflict["existing_edge"]
            
            new_created = datetime.fromisoformat(new_edge_data["created_at"])
            existing_created = datetime.fromisoformat(existing_edge_data["created_at"])
            
            action = "none"
            
            if self.resolution_strategy == ResolutionStrategy.KEEP_LATEST:
                # Remove existing, add new
                self.graph.remove_edge(existing_edge_data["id"])
                
                # We need to recreate Edge object
                from dagestan.graph.schema import Edge
                new_edge = Edge.from_dict(new_edge_data)
                self.graph.add_edge(new_edge)
                action = "replaced"
                
            elif self.resolution_strategy == ResolutionStrategy.KEEP_HIGHEST_CONFIDENCE:
                new_conf = new_edge_data.get("confidence_score", 1.0)
                old_conf = existing_edge_data.get("confidence_score", 1.0)
                if new_conf > old_conf:
                    self.graph.remove_edge(existing_edge_data["id"])
                    from dagestan.graph.schema import Edge
                    self.graph.add_edge(Edge.from_dict(new_edge_data))
                    action = "replaced_higher_conf"
                else:
                    action = "ignored_lower_conf"

            elif self.resolution_strategy == ResolutionStrategy.SURFACE_TO_USER:
                logging.warning(f"Contradiction surfaced for user review: {conflict}")
                self.graph.contradictions_queue.append(conflict)
                action = "surfaced"
                continue
                
            logging.info(f"Resolved conflict {existing_edge_data['id']} vs {new_edge_data['id']} -> {action}")
            resolved_count += 1
            
        return resolved_count

    def _apply_decay_and_prune(self) -> Dict[str, Any]:
        """Apply Ebbinghaus decay to everything and prune if below threshold."""
        now = _now()
        nodes_pruned = 0
        edges_pruned = 0
        chunks_pruned = 0
        
        total_node_conf = 0.0
        
        # We can't safely mutate dictionary while iterating
        node_ids = [n.id for n in self.graph.nodes]
        for nid in node_ids:
            node = self.graph.get_node(nid)
            if not node:
                continue
                
            # e^(-days * decay_rate)
            days_elapsed = (now - node.last_reinforced).total_seconds() / 86400
            if days_elapsed < 0:
                days_elapsed = 0
                
            decay_factor = math.exp(-days_elapsed * node.decay_rate)
            new_conf = node.confidence_score * decay_factor
            
            # Pinned nodes have attributes['pinned'] = True
            is_pinned = node.attributes.get("pinned", False)
            
            if new_conf < self.prune_threshold and not is_pinned:
                self.graph.remove_node(nid)
                nodes_pruned += 1
            else:
                node.confidence_score = new_conf
                total_node_conf += new_conf
                
        total_edge_conf = 0.0
        edge_ids = [e.id for e in self.graph.edges]
        for eid in edge_ids:
            edge = self.graph.get_edge(eid)
            if not edge:
                continue
                
            # Edges decay based on timestamp or source node decay
            days_elapsed = (now - edge.created_at).total_seconds() / 86400
            if days_elapsed < 0:
                days_elapsed = 0
                
            # We assume a fixed decay for edges for simplicity, e.g. 0.02
            decay_factor = math.exp(-days_elapsed * 0.02)
            new_conf = edge.confidence_score * decay_factor
            
            is_pinned = edge.attributes.get("pinned", False)
            if new_conf < self.prune_threshold and not is_pinned:
                self.graph.remove_edge(eid)
                edges_pruned += 1
            else:
                edge.confidence_score = new_conf
                total_edge_conf += new_conf

        # Vector chunks pruning
        # This requires scanning all chunks, which chromadb doesn't easily expose without limit/offset.
        # We'll query all chunks:
        results = self.vector_store.collection.get()
        if results.get("ids"):
            from datetime import datetime
            for i, chunk_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i]
                timestamp_str = metadata.get("timestamp")
                if not timestamp_str:
                    continue
                try:
                    ts = datetime.fromisoformat(timestamp_str)
                except ValueError:
                    continue
                    
                days_elapsed = (now - ts).total_seconds() / 86400
                if days_elapsed < 0:
                    days_elapsed = 0
                    
                # Standard decay factor for chunks: stability = 0.02
                decay_factor = math.exp(-days_elapsed * 0.02)
                chunk_score = float(metadata.get("decay_score", 1.0)) * decay_factor
                
                is_pinned = str(metadata.get("pinned", "false")).lower() == "true"
                
                if chunk_score < self.prune_threshold and not is_pinned:
                    self.vector_store.delete(chunk_id)
                    chunks_pruned += 1
                else:
                    # Update metadata. Chromadb upsert needs everything again.
                    metadata["decay_score"] = chunk_score
                    self.vector_store.collection.update(
                        ids=[chunk_id],
                        metadatas=[metadata]
                    )

        remaining_nodes = self.graph.node_count
        remaining_edges = self.graph.edge_count
        
        return {
            "nodes_pruned": nodes_pruned,
            "edges_pruned": edges_pruned,
            "chunks_pruned": chunks_pruned,
            "decay_stats": {
                "avg_node_confidence": total_node_conf / remaining_nodes if remaining_nodes > 0 else 0.0,
                "avg_edge_confidence": total_edge_conf / remaining_edges if remaining_edges > 0 else 0.0
            }
        }

    def _consolidate_schema(self) -> int:
        """Merge near-duplicate induced entity and relation types."""
        types_merged = 0
        
        # 1. Consolidate Node Types
        node_types = list(self.graph.schema_registry["node_types"])
        if len(node_types) > 1:
            embeddings = self.model.encode(node_types)
            # Find pairs with sim > 0.85
            merges = self._find_similar_pairs(node_types, embeddings, 0.85)
            for t1, t2 in merges:
                # Merge t2 into t1
                self.graph.schema_registry["node_types"].remove(t2)
                types_merged += 1
                for node in self.graph.get_nodes_by_type(t2):
                    node.type = t1

        # 2. Consolidate Edge Types
        edge_types = list(self.graph.schema_registry["edge_types"])
        if len(edge_types) > 1:
            embeddings = self.model.encode(edge_types)
            # Find pairs with sim > 0.85
            merges = self._find_similar_pairs(edge_types, embeddings, 0.85)
            for t1, t2 in merges:
                # Merge t2 into t1
                self.graph.schema_registry["edge_types"].remove(t2)
                types_merged += 1
                for edge in self.graph.get_edges(edge_type=t2):
                    edge.type = t1
                    
        return types_merged

    def _find_similar_pairs(self, items: List[str], embeddings, threshold: float) -> List[tuple[str, str]]:
        import numpy as np
        merges = []
        skip = set()
        
        # Compute cosine similarity matrix
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norm_emb = embeddings / np.where(norms == 0, 1e-10, norms)
        sim_matrix = np.dot(norm_emb, norm_emb.T)
        
        for i in range(len(items)):
            if items[i] in skip: continue
            for j in range(i + 1, len(items)):
                if items[j] in skip: continue
                if sim_matrix[i, j] > threshold:
                    # Choose shorter or lexicographically first as primary
                    t1, t2 = items[i], items[j]
                    if len(t2) < len(t1) or (len(t2) == len(t1) and t2 < t1):
                        t1, t2 = t2, t1
                    merges.append((t1, t2))
                    skip.add(t2)
        return merges
