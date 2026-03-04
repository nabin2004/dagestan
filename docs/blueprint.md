# Dagestan Blueprint

**Temporal Graph Memory Layer for LLMs**  
v0.1 | Open Source + Research

## 1. Vision & Problem Statement

Current LLM memory solutions are fundamentally flat. Vector databases retrieve by similarity — they have no concept of time, relationships, contradiction, or structure. Dagestan takes a different approach: memory as a living temporal graph of knowledge traces, not a pile of embeddings.

**The Horse vs Train Problem:** Classical algorithms are fast but rigid (horse). LLMs are powerful but expensive and slow (train). Dagestan is the memory layer that aims to make a smarter, lighter, more reasoned system possible — the foundation for efficient LLM-powered applications.

| What exists today | What Dagestan builds |
|---|---|
| Flat vector storage | Typed temporal graph |
| Similarity-based retrieval | Relationship-aware traversal |
| No contradiction handling | Active contradiction detection |
| Static snapshots | Living, curated memory |
| No time awareness | Temporal decay + reinforcement |

## 2. Core Architecture

### 2.1 Graph Schema (Minimal Ontology)

A minimal typed schema — just enough structure for intelligent operations, not so rigid it breaks on real conversations.

**Node Types:**

| Type | Description | Examples |
|------|------------|---------|
| Entity | Person, place, object | User, assistant, project |
| Concept | Idea, topic, domain | Machine learning, Nepal, coffee |
| Event | Something that happened | Conversation session, decision made |
| Preference | Like, dislike, value | Hates loud music, loves tea |
| Goal | What someone wants | Build Dagestan, get internship |

**Edge Types:**

| Type | Meaning |
|------|---------|
| relates_to | General semantic relationship |
| caused | Causal link between events or concepts |
| contradicts | Two nodes in conflict |
| happened_before | Temporal ordering |
| has_preference | Entity holds a preference |
| wants | Entity has a goal |

**Temporal Metadata (on every node and edge):**

- `created_at` — when this knowledge entered the graph
- `last_reinforced` — when it was last confirmed or referenced
- `confidence_score` — 0.0 to 1.0, degrades over time unless reinforced
- `decay_rate` — how fast confidence drops (preferences decay slower than events)
- `source` — which conversation/session produced this node

### 2.2 Pipeline Overview

| Stage | What happens | When |
|-------|-------------|------|
| Ingestion | Conversation text → typed graph nodes + edges via LLM extraction | Real-time, per turn |
| Snapshot | Full graph state saved with timestamp | End of each session / daily |
| Offline Curation | Graph operations: contradiction detection, gap detection, decay update, bridge finding | Nightly / async |
| Strategy Generation | LLM given structured graph summary → produces actionable next-session context | Post-curation |
| Retrieval | Query-driven graph traversal, not similarity search | On demand |

## 3. The Intelligence Layer — Graph Operations

These operations run on the graph itself — the LLM is used only to interpret results, not to do the computation.

### 3.1 Contradiction Detection

Find two Preference or Goal nodes belonging to the same Entity that assert conflicting states. Flag them. Pass only the conflict to LLM for resolution — not the whole graph.

```
Entity("User") → has_preference → Preference("loves coffee", t=day1)
Entity("User") → has_preference → Preference("hates coffee", t=day14)
Result: CONTRADICTION flagged, confidence of older node reduced
```

### 3.2 Temporal Decay

Confidence scores degrade over time unless a node is reinforced by new conversation. Different node types decay at different rates:

- **Goals**: slow decay — what someone wants is relatively stable
- **Preferences**: medium decay
- **Events**: fast decay — old events become less relevant quickly
- **Concepts**: very slow decay — domain knowledge persists

### 3.3 Gap Detection

Identify Entities with incomplete profiles — an Entity with Goals but no Preferences, or an Entity frequently mentioned but with no outgoing edges.

### 3.4 Bridge Node Detection

Find nodes that connect otherwise disconnected clusters. These are semantically interesting — unexpected connections that represent genuine insight.

### 3.5 Centrality Scoring

Rank nodes by connection count and recency-weighted reinforcement. High centrality = high importance. No LLM needed — pure graph math.

## 4. Package Structure

```
dagestan/
├── __init__.py              # Main Dagestan class
├── cli.py                   # CLI interface
├── graph/
│   ├── schema.py            # Node, Edge, NodeType, EdgeType
│   ├── temporal_graph.py    # Core graph, CRUD, snapshot
│   └── operations.py        # Contradiction, decay, gap, bridge, centrality
├── extraction/
│   ├── extractor.py         # Conversation → graph via LLM
│   └── prompts.py           # Extraction prompt templates
├── curation/
│   ├── curator.py           # Curation pipeline orchestrator
│   └── strategy.py          # Strategy generation
├── retrieval/
│   └── retriever.py         # Query-driven graph traversal
├── storage/
│   └── store.py             # JSON persistence (SQLite planned)
└── integrations/            # Planned: OpenAI/Anthropic wrappers
```

## 5. Developer Interface

```python
from dagestan import Dagestan

mem = Dagestan(storage='json', db_path='./memory.json', provider='openai')

# After each conversation turn
mem.ingest(conversation_history)

# Before next conversation — get context
context = mem.retrieve(query='What does the user care about?')

# Run curation
report = mem.curate()
```

### Storage Backends

- **v0.1** — JSON file (zero dependencies, easy to inspect)
- **v0.2** — SQLite (persistent, lightweight, no server)
- **v1.0** — Neo4j (full graph DB for production use)

## 6. Roadmap

| Phase | Focus | Key Deliverable |
|-------|-------|----------------|
| v0.1 — Foundation | Core graph schema, ingestion, JSON storage, basic operations | Working memory layer, pip installable |
| v0.2 — Intelligence | All 5 graph operations tuned, SQLite backend | [not yet conducted] improvement measurement vs baselines |
| v0.3 — Retrieval | Query-driven traversal replacing similarity search, context compression | Richer structured context injection |
| v1.0 — Research | Benchmarks, paper draft, honest evaluation vs Mem0 and vector DB baselines | Published open source + arXiv preprint |
| v2.0 — Reasoning | Graph operations as reasoning substrate, symbolic inference | First steps toward the reasoning engine |

## 7. Research Paper Angle

**Working Title:** "Dagestan: Temporal Knowledge Graphs as Structured Memory for Large Language Models"

**Core Claim:** Typed temporal graph memory with active graph operations (contradiction detection, decay, gap/bridge detection) produces richer, more coherent long-term context than flat vector retrieval — without requiring additional model training or GPU compute.

**Evaluation Strategy:**

- Design tasks requiring temporal reasoning, contradiction resolution, preference tracking
- Compare Dagestan retrieval vs Mem0 vs naive context window vs vector DB
- Measure: coherence of LLM responses, contradiction rate, context relevance, token efficiency
- All benchmarks runnable on CPU / minimal compute — reproducible by anyone

**What's different about this approach:**

- No existing memory system (that we're aware of) uses typed temporal graphs with active graph operations for LLM memory
- Contradiction detection in memory is largely unaddressed in current tooling
- Temporal decay is modeled explicitly — not just recency bias in retrieval
- Designed for efficiency first — not a scale-first solution

Note: the actual performance improvement over baselines is **[not yet conducted]**. Claims will only be made after proper evaluation.

## 8. Constraints

- Zero GPU required — must run on CPU only
- Minimal dependencies — no heavy ML frameworks for core functionality
- LLM-agnostic — works with any LLM via simple interface
- Storage-agnostic — JSON for v0.1, pluggable backends later
- Honest benchmarks — measure where it fails, not just where it wins
- Open source — MIT license, full reproducibility

---

Built from Nepal, with limited compute, from first principles.
