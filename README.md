# Dagestan


**Temporal Graph Memory Layer for LLMs**

Dagestan stores LLM memory as a typed temporal knowledge graph instead of flat vector embeddings. It tracks entities, concepts, events, preferences, and goals — with time-aware confidence decay, contradiction detection, and relationship-based retrieval.

## Why

Current LLM memory solutions (vector DBs) treat memory as a pile of embeddings retrieved by similarity. They don't understand:

- **Time** — old information and new information are treated the same
- **Relationships** — there's no structure between memories
- **Contradictions** — conflicting facts coexist silently
- **Decay** — nothing fades; nothing is curated

Dagestan addresses these gaps with a graph-based approach where memory has structure, relationships, and temporal awareness.

## Status

**v0.1 — Foundation release.** Working memory layer with:

- Typed temporal graph (Entity, Concept, Event, Preference, Goal nodes)
- LLM-based knowledge extraction from conversations
- Contradiction detection between conflicting preferences/goals
- Exponential temporal decay on confidence scores
- Gap detection (incomplete entity profiles)
- Bridge node detection (cross-cluster connections)
- Centrality-based importance scoring
- Query-driven graph retrieval (keyword + structure, no embeddings)
- JSON persistence
- CLI for graph inspection
- 63 passing unit tests

## Install

```bash
# Core (no LLM dependencies)
pip install -e .

# With OpenAI
pip install -e ".[openai]"

# With Anthropic
pip install -e ".[anthropic]"

# Development
pip install -e ".[dev]"
```

## Quick Start

```python
from dagestan import Dagestan

# Initialize with an LLM provider for extraction
mem = Dagestan(provider="openai", db_path="./memory.json")

# Ingest conversation text
mem.ingest("User mentioned they love Python and want to build a startup focused on graph databases.")

# Retrieve relevant context
context = mem.retrieve("What does the user care about?")
print(context)

# Run curation (applies decay, finds contradictions)
report = mem.curate()
print(f"Contradictions found: {report.contradictions_found}")

# Get structured context for next conversation
strategy = mem.strategy()
print(strategy)
```

### Without an LLM (manual graph building)

```python
from dagestan import Dagestan, Node, Edge, NodeType, EdgeType

mem = Dagestan(db_path="./memory.json", auto_save=True)

# Add nodes directly
user = mem.add_node(Node(type=NodeType.ENTITY, label="User"))
pref = mem.add_node(Node(type=NodeType.PREFERENCE, label="Prefers tea"))
goal = mem.add_node(Node(type=NodeType.GOAL, label="Build Dagestan"))

mem.add_edge(Edge(source_id=user.id, target_id=pref.id, type=EdgeType.HAS_PREFERENCE))
mem.add_edge(Edge(source_id=user.id, target_id=goal.id, type=EdgeType.WANTS))

# Query the graph
results = mem.retrieve("user preferences")
print(results)
```

## CLI

```bash
# Show graph summary
dagestan info --db ./memory.json

# List all nodes
dagestan nodes --db ./memory.json

# Filter by type
dagestan nodes --type preference --db ./memory.json

# Query the graph
dagestan retrieve "user goals" --db ./memory.json

# Run curation
dagestan curate --db ./memory.json

# Export full graph
dagestan export --db ./memory.json
```

## Architecture

```
Conversation → Extraction (LLM) → Temporal Graph → Operations → Retrieval
                                       ↓
                                   Curation
                                 (decay, contradictions,
                                  gaps, bridges)
```

**Node Types:** Entity, Concept, Event, Preference, Goal

**Edge Types:** relates_to, caused, contradicts, happened_before, has_preference, wants

**Temporal Metadata:** Every node carries `created_at`, `last_reinforced`, `confidence_score`, and `decay_rate`. Confidence degrades exponentially unless reinforced by new conversation.

## Graph Operations

These run on the graph structure — no LLM needed for computation.

| Operation | What it does |
|-----------|-------------|
| Contradiction Detection | Finds conflicting preferences/goals for the same entity |
| Temporal Decay | Reduces confidence based on time since last reinforcement |
| Gap Detection | Identifies entities with incomplete knowledge profiles |
| Bridge Detection | Finds nodes connecting otherwise disconnected clusters |
| Centrality Scoring | Ranks nodes by connection count + recency |

## Project Structure

```
dagestan/
├── __init__.py              # Main Dagestan class (public API)
├── cli.py                   # Command-line interface
├── graph/
│   ├── schema.py            # Node, Edge, NodeType, EdgeType
│   ├── temporal_graph.py    # Core graph with CRUD + snapshots
│   └── operations.py        # Contradiction, decay, gap, bridge, centrality
├── extraction/
│   ├── extractor.py         # Conversation → graph via LLM
│   └── prompts.py           # Extraction prompt templates
├── curation/
│   ├── curator.py           # Curation pipeline orchestrator
│   └── strategy.py          # Context strategy generation
├── retrieval/
│   └── retriever.py         # Query-driven graph traversal
├── storage/
│   └── store.py             # JSON persistence (SQLite planned for v0.2)
└── integrations/            # Planned: drop-in OpenAI/Anthropic wrappers
```

## Roadmap

| Version | Focus | Status |
|---------|-------|--------|
| v0.1 | Core graph, extraction, basic operations, JSON storage | **Done** |
| v0.2 | SQLite backend, all 5 operations fully tuned | Planned |
| v0.3 | Query-driven traversal improvements, context compression | Planned |
| v1.0 | Benchmarks, paper, honest evaluation vs baselines | Planned |
| v2.0 | Graph operations as reasoning substrate | Research |

## Evaluation (Planned)

We intend to benchmark Dagestan against:
- Naive context window (just include recent messages)
- Vector DB retrieval (e.g., ChromaDB)

On tasks requiring:
- Temporal reasoning (what changed over time)
- Contradiction resolution (conflicting information)
- Preference tracking (user preferences across sessions)
- Context coherence (does the LLM response stay consistent)

Performance claims will only be made after benchmarks are actually conducted. Until then: **[not yet conducted]**.

## Constraints

- **Zero GPU required** — runs on CPU only
- **Minimal dependencies** — core is stdlib only, LLM client is optional
- **LLM-agnostic** — works with any provider via simple callable interface
- **Storage-agnostic** — JSON now, SQLite/Neo4j planned
- **Honest evaluation** — we measure where it fails, not just where it wins

## License

MIT

