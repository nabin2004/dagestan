# Dagestan — Implementation Checklist

What's done, what's next, version by version through v5.0.

---

## v0.1 — Foundation ✅

- [x] Node types: ENTITY, CONCEPT, EVENT, PREFERENCE, GOAL
- [x] Edge types: RELATES_TO, CAUSED, CONTRADICTS, HAPPENED_BEFORE, HAS_PREFERENCE, WANTS
- [x] Node dataclass with temporal metadata (created_at, last_reinforced, confidence_score, decay_rate)
- [x] Edge dataclass with typed relationships and confidence
- [x] TemporalGraph core: add/get/remove nodes and edges
- [x] Adjacency index for fast neighbor lookups
- [x] Snapshot and load_snapshot (full graph serialization)
- [x] JSON file persistence (save_to_file / load_from_file)
- [x] ConversationExtractor: conversation text → typed nodes + edges via LLM
- [x] Extraction prompt templates (structured JSON output)
- [x] Contradiction detection (same-entity conflicting preferences/goals)
- [x] Temporal decay (exponential, per-type decay rates)
- [x] Centrality scoring (degree + recency-weighted)
- [x] Gap detection (incomplete entity profiles)
- [x] Bridge node detection (cross-cluster connectors)
- [x] Curator pipeline: decay → contradictions → LLM resolution → gaps → bridges
- [x] CurationReport dataclass
- [x] Strategy generation (structured context summary from curated graph)
- [x] strategy_to_prompt() for LLM context injection
- [x] Retriever: keyword matching + centrality + confidence scoring + neighbor expansion
- [x] retrieve_as_text() formatted output
- [x] Main Dagestan class: ingest(), retrieve(), curate(), strategy(), snapshot()
- [x] Node deduplication on ingest (reinforce existing instead of duplicating)
- [x] CLI: info, nodes, edges, retrieve, curate, strategy, export
- [x] pyproject.toml with optional openai/anthropic deps
- [x] 63 unit tests passing
- [x] README, architecture docs, API reference, blueprint, contributing guide

---

## v0.2 — Storage & Tuning

### SQLite Backend
- [ ] Implement `SQLiteStorage` class in `dagestan/storage/store.py`
- [ ] Schema: `nodes` table (id, type, label, attributes_json, created_at, last_reinforced, confidence_score, decay_rate, source)
- [ ] Schema: `edges` table (id, source_id, target_id, type, created_at, confidence_score, attributes_json)
- [ ] Schema: `snapshots` table (id, timestamp, graph_json) for historical snapshots
- [ ] Indexes on node type, edge source_id/target_id, confidence_score
- [ ] Incremental save (only write changed nodes/edges, not full dump)
- [ ] Transaction support (atomic writes)
- [ ] Migration from JSON to SQLite (one-command conversion)
- [ ] Register SQLiteStorage in `get_storage()` factory
- [ ] Tests for SQLite CRUD, persistence across restarts, concurrent read

### Graph Operations Tuning
- [ ] Tune default decay rates against real conversation data
- [ ] Contradiction detection: add label similarity heuristic (not just same-type-same-entity)
- [ ] Contradiction detection: weight by temporal distance (recent vs old)
- [ ] Gap detection: configurable thresholds for "under-characterized"
- [ ] Bridge detection: cache component computation (avoid recomputing per-node)
- [ ] Centrality: add PageRank-style iterative scoring as alternative
- [ ] Configurable operation parameters via Dagestan constructor

### Extraction Improvements
- [ ] Prompt versioning: track which prompt version produced each node
- [ ] Extraction retry with backoff on LLM failure
- [ ] Batch extraction: process multiple conversation turns in one LLM call
- [ ] Extraction quality scoring: confidence on extracted nodes based on LLM output

### Tests & Quality
- [ ] SQLite storage tests
- [ ] Integration test: full ingest → curate → retrieve cycle with mock LLM
- [ ] Property-based tests for graph invariants (node removal always cleans edges, etc.)
- [ ] Test coverage report (target: >85%)

---

## v0.3 — Retrieval & Context Compression

### Semantic Retrieval
- [ ] Lightweight embedding support (optional dependency, e.g., sentence-transformers or a small model)
- [ ] Hybrid scoring: keyword match + embedding similarity + centrality + confidence
- [ ] Embedding cache: store embeddings alongside nodes in storage
- [ ] Fallback: keyword-only mode when no embedding model is available

### Graph Traversal
- [ ] Multi-hop retrieval: follow edges N hops from seed nodes
- [ ] Subgraph extraction: retrieve a coherent subgraph around query-relevant nodes
- [ ] Path-aware retrieval: return the relationship chain, not just isolated nodes
- [ ] Temporal window filtering: retrieve only nodes from a time range

### Context Compression
- [ ] Token budget: retriever accepts max_tokens parameter
- [ ] Priority-based truncation: drop lowest-relevance nodes to fit budget
- [ ] Summary generation: compress retrieved subgraph into natural language summary
- [ ] Context diff: return only what changed since last retrieval

### Integration Layer
- [ ] `dagestan/integrations/openai.py` — drop-in wrapper for OpenAI chat completions
- [ ] `dagestan/integrations/anthropic.py` — drop-in wrapper for Anthropic messages
- [ ] Auto-inject memory context into system prompt
- [ ] Auto-ingest assistant responses into graph
- [ ] Session management: track conversation sessions for source tagging

### Tests
- [ ] Retrieval quality tests with known-answer queries
- [ ] Context compression tests (verify token budget is respected)
- [ ] Integration wrapper tests with mock LLM clients
- [ ] Multi-hop traversal tests

---

## v1.0 — Research & Benchmarks

### Benchmark Suite
- [ ] Define benchmark tasks:
  - [ ] Temporal reasoning (what changed between session 1 and session 5?)
  - [ ] Contradiction resolution (user said X then said not-X)
  - [ ] Preference tracking (does the system remember user likes?)
  - [ ] Long-term coherence (does context stay consistent across 20+ sessions?)
  - [ ] Context relevance (is the injected context actually useful?)
- [ ] Implement benchmark runner: automated task execution + scoring
- [ ] Baseline implementations:
  - [ ] Naive context window (include last N messages)
  - [ ] Vector DB retrieval (ChromaDB or similar)
  - [ ] Mem0 integration for comparison
- [ ] Metrics:
  - [ ] Contradiction rate in LLM responses
  - [ ] Context relevance score (LLM-as-judge)
  - [ ] Token efficiency (useful context per token)
  - [ ] Response coherence across sessions
  - [ ] Latency: ingestion time, retrieval time, curation time

### Neo4j Backend
- [ ] Implement `Neo4jStorage` class
- [ ] Cypher query support for complex graph traversals
- [ ] Connection pooling and error handling
- [ ] Schema migration from SQLite to Neo4j
- [ ] Performance comparison: JSON vs SQLite vs Neo4j at different graph sizes

### Paper
- [ ] Write evaluation methodology section
- [ ] Run all benchmarks, record results honestly
- [ ] Document where Dagestan fails or underperforms baselines
- [ ] Write paper draft: intro, related work, method, experiments, results, discussion
- [ ] Internal review and revision
- [ ] arXiv preprint submission

### Production Hardening
- [ ] Logging: structured logging throughout pipeline
- [ ] Error handling: graceful degradation at every stage
- [ ] Configuration file support (dagestan.toml or similar)
- [ ] Graph size limits and warnings
- [ ] Memory usage profiling for large graphs

### Tests
- [ ] Benchmark reproducibility tests
- [ ] Neo4j storage tests
- [ ] End-to-end tests with real LLM calls (marked as slow/optional)
- [ ] Stress test: 10k+ nodes, measure operation latency

---

## v2.0 — Reasoning Engine

### Symbolic Inference
- [ ] Rule engine: define IF-THEN rules over graph patterns
- [ ] Forward chaining: automatically derive new edges/nodes from existing patterns
- [ ] Example rule: IF Entity→wants→Goal AND Goal→relates_to→Concept, THEN Entity→relates_to→Concept
- [ ] Rule confidence propagation (derived facts have lower confidence than observed ones)
- [ ] User-definable rules via config or API

### Multi-Agent Memory
- [ ] Shared graph: multiple agents read/write to the same graph
- [ ] Agent-scoped views: each agent sees only relevant subgraph
- [ ] Conflict resolution between agents' contributions
- [ ] Access control: which agents can modify which nodes

### Advanced Graph Operations
- [ ] Cluster detection: automatically group related nodes into topics
- [ ] Trend detection: identify patterns in how preferences/goals shift over time
- [ ] Prediction: "based on past goal changes, user is likely to want X next"
- [ ] Graph summarization: compress old/low-confidence subgraphs into summary nodes

### Ontology Extension
- [ ] Dynamic node types: allow user-defined types beyond the base 5
- [ ] Dynamic edge types: allow user-defined relationship types
- [ ] Type hierarchy: Preference is-a Attribute, Goal is-a Intention, etc.
- [ ] Schema validation: ensure graph consistency when types are extended

### Tests
- [ ] Rule engine tests (forward chaining correctness)
- [ ] Multi-agent conflict resolution tests
- [ ] Cluster detection tests on known graph structures
- [ ] Dynamic ontology tests

---

## v3.0 — Scale & Ecosystem

### Performance
- [ ] Graph partitioning: split large graphs into shards by entity/topic
- [ ] Lazy loading: load subgraphs on demand instead of full graph
- [ ] Caching layer: LRU cache for frequently accessed nodes/edges
- [ ] Async operations: non-blocking ingestion and curation
- [ ] Batch ingestion: process multiple conversations in parallel

### Streaming
- [ ] Real-time ingestion: process conversation tokens as they arrive
- [ ] Incremental curation: run lightweight checks after each turn, full curation periodically
- [ ] Webhook support: notify external systems on graph changes (contradiction found, gap filled, etc.)

### Developer Experience
- [ ] Web dashboard: visualize graph state in browser
- [ ] Graph diff viewer: see what changed between two snapshots
- [ ] Playground: interactive query interface for testing retrieval
- [ ] Plugin system: allow third-party extensions for storage, extraction, operations
- [ ] Python SDK improvements: async API, context managers, type stubs

### Ecosystem Integrations
- [ ] LangChain memory integration
- [ ] LlamaIndex integration
- [ ] FastAPI middleware for auto-memory in API servers
- [ ] Telegram/Discord bot template with Dagestan memory

### Tests
- [ ] Performance benchmarks at 100k+ nodes
- [ ] Async operation tests
- [ ] Plugin system tests
- [ ] Integration tests with LangChain/LlamaIndex

---

## v4.0 — Multi-Modal & Cross-Graph

### Multi-Modal Memory
- [ ] Image reference nodes: store metadata about images discussed
- [ ] Code snippet nodes: track code shared in conversations with language/purpose
- [ ] Document reference nodes: link to external documents mentioned
- [ ] URL nodes: track links shared with extracted metadata
- [ ] File attachment tracking in conversation extraction

### Cross-Graph Operations
- [ ] Graph merging: combine two users' graphs where they overlap
- [ ] Graph comparison: diff two graphs to find unique vs shared knowledge
- [ ] Knowledge transfer: import relevant subgraph from one user to another
- [ ] Graph templates: pre-built graph structures for common domains

### Versioning
- [ ] Full graph versioning: branch, tag, rollback
- [ ] Node-level history: see all past states of a node
- [ ] Curation audit trail: record every curation decision with reasoning
- [ ] Undo support: reverse the last N operations

### Privacy & Security
- [ ] Node-level encryption for sensitive data
- [ ] PII detection: flag nodes that might contain personal information
- [ ] Data retention policies: auto-delete nodes older than N days
- [ ] Export / delete all data for a given entity (GDPR-style)
- [ ] Access logging: track who read/modified which nodes

### Tests
- [ ] Multi-modal extraction tests
- [ ] Graph merge correctness tests
- [ ] Versioning rollback tests
- [ ] PII detection tests
- [ ] Encryption round-trip tests

---

## v5.0 — Autonomous Memory

### Self-Curating Graph
- [ ] Autonomous curation scheduler: graph monitors itself and triggers curation when needed
- [ ] Adaptive decay rates: learn optimal decay rates from reinforcement patterns
- [ ] Automatic schema evolution: detect when new node/edge types are needed
- [ ] Quality self-assessment: graph evaluates its own completeness and accuracy

### Hypothesis Generation
- [ ] Gap-based hypotheses: "User probably likes X because they like Y and Z"
- [ ] Hypothesis confidence scoring and validation loop
- [ ] Active questioning: suggest questions to ask the user to fill knowledge gaps
- [ ] Hypothesis pruning: remove unvalidated hypotheses after N sessions

### Memory Compression
- [ ] Lossy compression: merge similar low-confidence nodes into summaries
- [ ] Hierarchical memory: recent detail + older summaries + ancient abstractions
- [ ] Forgetting curve: model human-like memory decay with spacing effects
- [ ] Memory consolidation: "sleep" phase that restructures and compresses the graph

### Cross-Session Reasoning
- [ ] Session-aware retrieval: understand "last time" / "before" / "after" references
- [ ] Narrative tracking: maintain a timeline of how the user's goals/preferences evolved
- [ ] Proactive context: anticipate what context will be needed before user asks
- [ ] Meta-memory: the graph knows what it knows and what it doesn't

### External Knowledge
- [ ] Fact-checking: cross-reference graph claims against external sources
- [ ] Knowledge import: ingest structured data (CSV, JSON) directly into graph
- [ ] API-backed nodes: nodes whose attributes are fetched from external APIs on demand
- [ ] Federated memory: query across multiple Dagestan instances

### Tests
- [ ] Autonomous curation behavior tests
- [ ] Hypothesis generation and pruning tests
- [ ] Memory compression integrity tests (no critical knowledge lost)
- [ ] Cross-session reasoning tests
- [ ] Federated query tests

---

## Summary

| Version | Theme | Estimated Scope |
|---------|-------|----------------|
| v0.1 ✅ | Foundation | Core graph + extraction + operations + retrieval |
| v0.2 | Storage & tuning | SQLite, operation refinement, extraction improvements |
| v0.3 | Retrieval & context | Embeddings, multi-hop traversal, context compression, integrations |
| v1.0 | Research & benchmarks | Benchmark suite, Neo4j, paper, production hardening |
| v2.0 | Reasoning engine | Symbolic inference, multi-agent, advanced operations |
| v3.0 | Scale & ecosystem | Performance, streaming, dashboard, third-party integrations |
| v4.0 | Multi-modal & cross-graph | Images/code/docs, graph merging, versioning, privacy |
| v5.0 | Autonomous memory | Self-curation, hypothesis generation, compression, meta-memory |

Each version builds on the previous one. Nothing here is promised — it's a direction, not a contract. Priorities will shift based on what actually works and what users need.
