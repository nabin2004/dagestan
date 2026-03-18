# Dagestan Project Workflow

## Overview
Dagestan is a temporal knowledge graph system designed to serve as structured memory for LLMs. It combines graph-based reasoning with vector embedding search to enable advanced retrieval, contradiction detection, and context curation from conversation dumps.

## Key Components
- **Temporal Graph**: Stores entities, concepts, events, preferences, and goals as nodes with temporal metadata (creation, reinforcement, confidence, decay).
- **Vector Store**: Stores conversational chunks as embeddings for fast similarity search (using sentence-transformers and ChromaDB).
- **Hybrid Retriever**: Coordinates between graph traversal and vector search to retrieve relevant context.
- **Extractor**: Uses LLMs to convert conversation text into typed graph nodes and edges.
- **Curator/Strategy**: Applies decay, contradiction detection/resolution, gap/bridge detection, and generates structured summaries for LLM context injection.

## Workflow Steps
1. **Ingestion**
   - Conversation text is processed by an LLM extractor.
   - Extracted entities, events, preferences, etc. are added as nodes/edges to the temporal graph.
   - Chunks of conversation are embedded and stored in the vector database.

2. **Snapshot & Storage**
   - The full graph state is periodically serialized to JSON (with timestamp).
   - Vector store persists conversational chunks and embeddings.

3. **Curation**
   - Decay is applied to node confidence scores based on time and type.
   - Contradictions (e.g., conflicting preferences/goals) are detected and resolved via LLM or decay.
   - Gaps and bridges in knowledge are identified for further exploration.

4. **Strategy Generation**
   - Curated graph is scored for centrality and importance.
   - Structured summaries (entities, goals, preferences, events, gaps) are generated for LLM context.

5. **Hybrid Retrieval**
   - User query is parsed for candidate entities (via substring or NER).
   - Graph neighborhood is expanded (1-2 hops) for context.
   - Vector search retrieves similar conversational chunks.
   - Results are combined, with graph results boosted for structure and temporal relevance.
   - Final ranked results include provenance (node/edge IDs) and retrieval trace.

## Hybrid Strategy: Graph + Conversation Dump Embedding Search
Dagestan's retrieval is hybrid:
- **Graph Traversal**: Enables reasoning about relationships, time, and contradictions. Supports neighbor expansion and centrality weighting.
- **Embedding Search**: Finds semantically similar conversation chunks using vector similarity. Useful for recall and fuzzy matching.
- **Combination**: Graph results are boosted (factor configurable), and vector results are merged. This ensures both structured and semantic matches are surfaced.

## Temporal & Contradiction Model
- Nodes have `created_at`, `last_reinforced`, `confidence_score`, and `decay_rate`.
- Confidence decays exponentially; reinforcement restores confidence.
- Contradictions are flagged when two nodes of the same type connect to the same entity with high confidence. LLM resolves which is current; others decay.

## Storage & Visualization
- Graph is stored as JSON (v0.1); vector store uses ChromaDB.
- Visualization layer enables inspection of graph structure and retrieval provenance.

## Extensibility
- Minimal ontology (5 node types, 6 edge types) for robustness.
- LLMs are used only for extraction and contradiction resolution; all other operations are pure computation.
- Future versions may add semantic matching, SQLite/Neo4j storage, richer ontology.

---

**Dagestan** enables advanced memory and retrieval for LLMs by combining the strengths of temporal graphs and embedding search, supporting reasoning, contradiction detection, and structured context generation from conversation history.