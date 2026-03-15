"""
dagestan.embeddings.vector_store
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Vector storage for conversational chunks.
Uses sentence-transformers for embeddings and ChromaDB as the backend vector index.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer


class VectorChunk(BaseModel):
    """
    A chunk of conversational text stored in the vector database.
    """
    chunk_id: str
    turn_id: str
    text: str
    embedding: Optional[List[float]] = None
    entity_refs: List[str] = Field(default_factory=list)
    timestamp: datetime
    decay_score: float = 1.0


def _now() -> datetime:
    """UTC-aware current timestamp."""
    return datetime.now(timezone.utc)


class VectorStore:
    """
    Vector storage wrapper for conversational chunks.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        db_path: str = "./.chroma_db",
        collection_name: str = "dagestan_chunks",
    ) -> None:
        self.model = SentenceTransformer(model_name)
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def upsert(
        self,
        turn_id: str,
        text: str,
        entity_refs: List[str],
        timestamp: Optional[datetime] = None,
        chunk_id: Optional[str] = None,
    ) -> str:
        """
        Embed and store a chunk of text.
        
        Args:
            turn_id: Originating conversation turn ID.
            text: The text string to embed and store.
            entity_refs: List of graph node IDs related to this text.
            timestamp: When this turn occurred (defaults to now).
            chunk_id: Optional, explicitly set chunk_id. (Generated if None).
            
        Returns:
            The chunk_id of the stored document.
        """
        if timestamp is None:
            timestamp = _now()
            
        # Generate a fallback chunk_id based on turn_id and hash of text if not provided
        _id = chunk_id or f"{turn_id}_{hash(text) % 100000000}"
        embedding = self.model.encode(text).tolist()
        
        # ChromaDB allows bool, int, float, str. 
        # Using a JSON string for entity_refs is safest.
        metadata = {
            "turn_id": turn_id,
            "entity_refs": json.dumps(entity_refs),
            "timestamp": timestamp.isoformat(),
            "decay_score": 1.0,
        }
        
        self.collection.upsert(
            ids=[_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )
        return _id

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Search for top_k chunks matching the query text.
        
        Args:
            query_text: Text to embed and search.
            top_k: Number of results to return.
            filters: Optional metadata filters.
            
        Returns:
            A list of tuples: (chunk_id, distance_score, metadata)
        """
        query_embedding = self.model.encode(query_text).tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters,
        )
        
        out = []
        if results.get("ids") and len(results["ids"]) > 0:
            ids = results["ids"][0]
            distances = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(ids)
            metadatas = results["metadatas"][0] if "metadatas" in results and results["metadatas"] else [{}] * len(ids)
            
            for i in range(len(ids)):
                # Convert string distance to float if needed, chromadb uses float by default
                out.append((ids[i], float(distances[i]), metadatas[i]))
                
        return out

    def get_by_entity(self, node_id: str) -> List[VectorChunk]:
        """
        Retrieve all vector chunks that reference a specific graph node ID.
        """
        # We stored entity_refs as JSON strings. We can query all and filter, or use a $contains query if supported.
        # For simplicity and robustness across ChromaDB versions, we use $contains which acts on strings natively.
        results = self.collection.get(
            where={"entity_refs": {"$contains": f'"{node_id}"'}}
        )
        
        chunks = []
        if results.get("ids"):
            for i in range(len(results["ids"])):
                metadata = results["metadatas"][i]
                
                # Parse JSON string back to list of strings
                refs_json = metadata.get("entity_refs", "[]")
                try:
                    refs = json.loads(refs_json)
                except json.JSONDecodeError:
                    refs = []
                    
                if node_id in refs:
                    chunks.append(VectorChunk(
                        chunk_id=results["ids"][i],
                        turn_id=str(metadata.get("turn_id", "")),
                        text=results["documents"][i],
                        entity_refs=refs,
                        timestamp=datetime.fromisoformat(metadata["timestamp"]),
                        decay_score=float(metadata.get("decay_score", 1.0)),
                    ))
        return chunks

    def delete(self, chunk_id: str) -> None:
        """
        Delete a chunk by ID.
        """
        self.collection.delete(ids=[chunk_id])
