# Dagestan Architecture

## Overview

Dagestan is a temporal knowledge graph that serves as structured memory for LLMs. Instead of storing conversation history as flat vector embeddings, it maintains a typed graph of entities, concepts, events, preferences, and goals — each with temporal metadata that models how knowledge ages and changes.

## Core Design Decisions

### Why a Graph, Not Vectors

Vector databases retrieve by cosine similarity. This works for "find things similar to X" but fails at:

- **Temporal reasoning**: "What did the user say about coffee last week vs today?" Vectors have no time axis.
- **Contradiction detection**: Two conflicting embeddings will happily coexist. A graph can detect that two preference nodes for the same entity conflict.
- **Relationship traversal**: "What's connected to what the user cares about?" requires structure. Nearest-neighbor search doesn't do this.
- **Decay**: Old information should fade unless reinforced. Vectors don't decay.

The tradeoff: graphs are more complex to maintain and require extraction. We accept this cost because the downstream quality of retrieved context is better for tasks that need reasoning about relationships and time.

### Minimal Ontology

The graph uses 5 node types and 6 edge types. This is intentionally minimal. A richer ontology would capture more nuance but would also:

- Break more often on unexpected input
- Require more complex extraction prompts
- Make graph operations harder to reason about

The philosophy: start with the minimum structure that enables useful operations. Extend later if real usage demands it.

### LLM for Extraction, Graph for Reasoning

The LLM is used **only** during extraction (conversation → graph) and contradiction resolution (which of two conflicting nodes is more likely correct). All graph operations — decay, centrality, gap detection, bridge detection — are pure computation on the graph structure. No LLM calls, no API costs, no latency.

This is a deliberate design choice: use the expensive, powerful tool (LLM) for the task it's good at (language understanding), and use cheap, reliable tools (graph algorithms) for everything else.

## Pipeline

```
1. Ingestion
   Conversation text → LLM extraction → typed nodes + edges → graph

2. Snapshot
   Full graph state serialized with timestamp → JSON file

3. Curation (offline / on-demand)
   apply_decay() → detect_contradictions() → resolve via LLM →
   detect_gaps() → detect_bridges() → save curated graph

4. Strategy Generation
   Curated graph → centrality scoring → structured context summary

5. Retrieval
   Query → keyword matching → centrality weighting → neighbor expansion →
   ranked results
```

## Temporal Model

Every node has:

- `created_at`: when it entered the graph
- `last_reinforced`: when it was last confirmed (newer = stronger)
- `confidence_score`: 0.0 to 1.0, decays over time
- `decay_rate`: how fast confidence drops (varies by type)

Decay is exponential: `confidence *= exp(-decay_rate * days_since_reinforced)`

Default decay rates:

| Node Type | Decay Rate | Reasoning |
|-----------|-----------|-----------|
| Entity | 0.005/day | Entities rarely become irrelevant |
| Concept | 0.01/day | Domain knowledge persists |
| Goal | 0.01/day | Goals are relatively stable |
| Preference | 0.02/day | Preferences change over weeks |
| Event | 0.05/day | Events become less relevant quickly |

Reinforcement (re-mentioning a concept) partially restores confidence (+0.2, capped at 1.0).

## Contradiction Model

A contradiction is flagged when:

1. Two nodes of the same type (usually Preference or Goal) are connected to the same Entity
2. Both have confidence > 0.1 (haven't already decayed away)

When found, the contradiction is passed to the LLM with both nodes' labels, timestamps, and confidence scores. The LLM decides which is more likely current. The "losing" node gets its confidence reduced; the "winning" node gets a slight boost.

If no LLM is available, contradictions are flagged but not resolved. The graph continues to carry both until one decays away naturally.

## Retrieval Model (v0.1)

Retrieval in v0.1 uses keyword matching combined with graph structure. No embeddings.

For each node, a score is computed:

```
score = (query_weight × keyword_match) +
        (centrality_weight × normalized_centrality) +
        (confidence_weight × confidence_score)
```

Nodes that are neighbors of direct keyword matches get a boost (neighbor expansion). This captures the graph structure: if you ask about "Python", the node "Dagestan project" (connected to Python) should also appear.

Default weights: 0.4 query, 0.3 centrality, 0.3 confidence.

This is a starting point. Future versions will likely need semantic matching or lightweight embeddings for better recall. The current approach is chosen for zero-dependency simplicity.

## Storage (v0.1)

JSON file. The entire graph is serialized as a single JSON document with all nodes and edges. This is simple to implement, debug, and inspect manually.

Limitations:
- Not concurrent-safe (single writer assumed)
- Loads entire graph into memory
- No indexing beyond in-memory dicts

This is acceptable for v0.1 where graph sizes are small (hundreds to low thousands of nodes). SQLite is planned for v0.2, Neo4j for v1.0.

## Visualization Layer

Dagestan includes a built-in interactive graph visualizer (`viz/`) for debugging and exploring knowledge graphs in the browser. It is intentionally kept **zero-dependency** — the server uses only Python stdlib (`http.server`, `json`, `threading`), and the frontend loads vis-network from a CDN.

### Design Decisions

**Why a built-in visualizer?**
Knowledge graphs are hard to debug from JSON alone. Seeing nodes, edges, confidence levels, and types visually accelerates development and helps users understand what the graph actually contains. Shipping a visualizer with zero setup cost makes this accessible by default.

**Stdlib-only server.**
There is no Flask, FastAPI, or any framework. The server is a `BaseHTTPRequestHandler` subclass (~400 lines) that serves static files and a small REST API. This keeps the dependency count at zero and makes the entire viz module copy-pasteable into any project.

**Server-Sent Events (SSE) for live updates.**
The server watches the graph JSON file on disk using stat-based polling (`viz/watcher.py`). When the file changes, connected browsers receive a push update via SSE — no WebSocket libraries needed. The frontend diffs the previous and current graph states to highlight newly added nodes with a green glow.

**LaTeX/academic export.**
Since Dagestan targets research use cases, the export module (`viz/export.py`) generates TikZ/PGF code, Graphviz DOT, LaTeX tables, and CSV directly from the graph data. This lets researchers include graph diagrams in papers without leaving the Dagestan ecosystem.

### Architecture

```
Browser (vis-network)
    │
    ├── GET /api/graph        → full graph JSON snapshot
    ├── GET /api/graph/stats  → node/edge counts, type distributions
    ├── GET /api/graph/hash   → MD5 hash for change detection
    ├── GET /api/files        → list available graph JSON files
    ├── GET /api/events       → SSE stream for live push updates
    ├── GET /api/export       → LaTeX/DOT/CSV export
    └── GET /api/switch?file= → switch active graph file
    │
viz/server.py (stdlib HTTPServer, threaded)
    │
    └── GraphState
         ├── reload()         → stat + read + hash graph JSON
         ├── get_stats()      → compute type/confidence distributions
         └── list_graph_files()→ scan project for graph JSONs
    │
viz/watcher.py (FileWatcher)
    └── polls file mtime, invokes on_change callback
    │
viz/export.py
    ├── export_tikz()         → TikZ/PGF graph code
    ├── export_dot()          → Graphviz DOT format
    ├── export_latex_tables() → LaTeX tabular environments
    └── export_csv()          → node/edge CSV tables
```

### Frontend Features

The single-page app (`viz/static/`) uses vis-network for force-directed graph rendering with these capabilities:

- **Node type shapes & colors** — entities (circles/blue), concepts (diamonds/purple), events (stars/orange), preferences (triangles/green), goals (hexagons/red)
- **Confidence visualization** — node opacity and border intensity reflect confidence scores; color shifts from green → yellow → red as confidence decays
- **Diff highlighting** — on live updates, new nodes glow green with a ✦ marker; the dashboard shows added/removed counts
- **Neighborhood explorer** — double-click a node to zoom into its 1-hop neighborhood; double-click empty space to reset
- **Inspector panels** — click nodes/edges to see full metadata (type, confidence, decay rate, timestamps, attributes)
- **Type filters** — toggle any of the 5 node types on/off
- **Search** — filter nodes by label text
- **Keyboard shortcuts** — `R` refresh, `F` fit view, `/` focus search, `?` help overlay, `Esc` clear selection
- **Raw JSON inspector** — button to view the raw graph JSON for debugging

