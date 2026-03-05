# API Reference

## Dagestan (Main Interface)

```python
from dagestan import Dagestan
```

### Constructor

```python
Dagestan(
    storage="json",       # Backend: "json" (v0.1), "sqlite" (planned)
    db_path="./dagestan_memory.json",  # Storage file path
    provider=None,        # "openai" or "anthropic"
    api_key=None,         # API key (or set env var)
    model=None,           # Model name override
    llm_client=None,      # Custom callable: (system_prompt, user_prompt) -> str
    auto_save=True,       # Save after ingest/curate
)
```

### Methods

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `ingest(conversation, source="")` | `str` or `list[dict]` | `(nodes_added, edges_added)` | Extract knowledge from conversation |
| `retrieve(query, top_k=10, as_text=True)` | `str` | `str` or `list[RetrievalResult]` | Query the graph for context |
| `curate(current_time=None)` | `datetime` (optional) | `CurationReport` | Run decay + contradiction + gap detection |
| `strategy(top_k=15, as_text=True)` | — | `str` or `dict` | Generate context summary |
| `save()` | — | `None` | Save graph to storage |
| `snapshot()` | — | `dict` | Get serialized graph state |
| `add_node(node)` | `Node` | `Node` | Add a node directly |
| `add_edge(edge)` | `Edge` | `Edge` | Add an edge directly |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `graph` | `TemporalGraph` | Direct access to underlying graph |
| `node_count` | `int` | Number of nodes |
| `edge_count` | `int` | Number of edges |

---

## Node

```python
from dagestan.graph.schema import Node, NodeType
```

```python
Node(
    type=NodeType.ENTITY,     # ENTITY, CONCEPT, EVENT, PREFERENCE, GOAL
    label="User",             # Human-readable name
    id=None,                  # Auto-generated if not provided
    attributes={},            # Arbitrary key-value metadata
    created_at=None,          # Auto-set to now if not provided
    last_reinforced=None,     # Auto-set to now if not provided
    confidence_score=1.0,     # 0.0 to 1.0
    decay_rate=None,          # Auto-set from DEFAULT_DECAY_RATES
    source="",                # Session/conversation tag
)
```

### Methods

| Method | Description |
|--------|-------------|
| `to_dict()` | Serialize to plain dict |
| `from_dict(data)` | Class method: deserialize from dict |
| `reinforce(timestamp=None)` | Reset decay clock, boost confidence by 0.2 |

---

## Edge

```python
from dagestan.graph.schema import Edge, EdgeType
```

```python
Edge(
    source_id="...",          # ID of origin node
    target_id="...",          # ID of destination node
    type=EdgeType.RELATES_TO, # RELATES_TO, CAUSED, CONTRADICTS, HAPPENED_BEFORE, HAS_PREFERENCE, WANTS
    id=None,                  # Auto-generated
    created_at=None,          # Auto-set to now
    confidence_score=1.0,     # Bounded by connected node confidence after decay
    attributes={},            # Arbitrary metadata
)
```

---

## TemporalGraph

```python
from dagestan.graph.temporal_graph import TemporalGraph
```

| Method | Description |
|--------|-------------|
| `add_node(node)` | Add a node |
| `get_node(node_id)` | Get node by ID (or None) |
| `get_nodes_by_type(node_type)` | Filter nodes by type |
| `get_nodes_by_label(label)` | Search nodes by label (case-insensitive) |
| `remove_node(node_id)` | Remove node and connected edges |
| `add_edge(edge)` | Add an edge (validates endpoints exist) |
| `get_edge(edge_id)` | Get edge by ID |
| `get_edges(node_id, edge_type, direction)` | Filtered edge query |
| `remove_edge(edge_id)` | Remove an edge |
| `neighbors(node_id, direction)` | Get neighboring nodes |
| `snapshot()` | Serialize full graph state |
| `load_snapshot(data)` | Restore from snapshot |
| `save_to_file(path)` | Write to JSON file |
| `load_from_file(path)` | Read from JSON file |

---

## Graph Operations

```python
from dagestan.graph.operations import (
    detect_contradictions,
    apply_decay,
    compute_centrality,
    detect_gaps,
    detect_bridges,
)
```

| Function | Signature | Returns |
|----------|-----------|---------|
| `detect_contradictions(graph)` | `TemporalGraph → list[tuple[Node, Node, Node]]` | `(entity, node_a, node_b)` triples |
| `apply_decay(graph, current_time, min_confidence)` | `TemporalGraph → int` | Number of nodes decayed |
| `compute_centrality(graph, recency_weight)` | `TemporalGraph → dict[str, float]` | `node_id → score` |
| `detect_gaps(graph)` | `TemporalGraph → list[dict]` | Gap descriptions |
| `detect_bridges(graph)` | `TemporalGraph → list[Node]` | Bridge nodes |

---

## ConversationExtractor

```python
from dagestan.extraction.extractor import ConversationExtractor
```

```python
extractor = ConversationExtractor(
    llm_client=None,      # Custom callable
    provider="openai",    # Or "anthropic"
    api_key=None,
    model=None,
    source_tag="",
)

nodes, edges = extractor.extract(conversation)
# conversation: str or list[{"role": ..., "content": ...}]
```

---

## Curator

```python
from dagestan.curation.curator import Curator
```

```python
curator = Curator(llm_client=None)  # None = flag-only mode
report = curator.run_curation(graph, current_time=None)
```

### CurationReport

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `str` | When curation ran |
| `nodes_decayed` | `int` | Nodes whose confidence was reduced |
| `contradictions_found` | `int` | Potential conflicts detected |
| `contradictions_resolved` | `int` | Conflicts resolved via LLM |
| `gaps_found` | `int` | Incomplete entity profiles |
| `bridges_found` | `int` | Cross-cluster bridge nodes |
| `details` | `list[dict]` | Detailed findings |

---

## Retriever

```python
from dagestan.retrieval.retriever import Retriever
```

```python
retriever = Retriever(
    query_weight=0.4,
    centrality_weight=0.3,
    confidence_weight=0.3,
    neighbor_boost=0.5,
)

results = retriever.retrieve(graph, "query text", top_k=10)
text = retriever.retrieve_as_text(graph, "query text")
```

### RetrievalResult

| Field | Type | Description |
|-------|------|-------------|
| `node` | `Node` | The retrieved node |
| `score` | `float` | Relevance score |
| `reason` | `str` | Why this node was retrieved |

---

## Custom LLM Client

Any callable matching this signature works:

```python
def my_llm(system_prompt: str, user_prompt: str) -> str:
    # Call your LLM here
    return response_text

mem = Dagestan(llm_client=my_llm)
```

This means Dagestan works with any LLM — local models, custom APIs, anything that takes two strings and returns a string.

---

## Visualization Server

The `viz` module provides a zero-dependency HTTP server for interactive graph exploration.

### Running

```bash
python -m viz.server                          # auto-detect graph file
python -m viz.server --file graph.json        # specific file
python -m viz.server --port 9000 --host 0.0.0.0  # custom bind
```

### REST API Endpoints

| Endpoint | Method | Response | Description |
|----------|--------|----------|-------------|
| `/api/graph` | GET | `{"nodes": [...], "edges": [...]}` | Full graph JSON snapshot |
| `/api/graph/stats` | GET | `{"node_count", "edge_count", "node_types", ...}` | Graph statistics |
| `/api/graph/hash` | GET | `{"hash": "md5..."}` | Hash for change detection |
| `/api/files` | GET | `[{"path", "node_count", "edge_count", ...}]` | List graph JSON files in project |
| `/api/events` | GET | SSE stream | Server-Sent Events — pushes `graph-update` on file change |
| `/api/export?format=tikz` | GET | text | Export graph (formats: `tikz`, `dot`, `latex_tables`, `csv`) |
| `/api/export/formats` | GET | `[{"id", "name", "description"}]` | List available export formats |
| `/api/switch?file=path` | GET | `{"ok": true}` | Switch to a different graph file |

### GraphState

```python
from viz.server import GraphState

state = GraphState(graph_path="memory.json", watch_dir=".")
state.reload()          # Returns True if data changed
state.data              # Current graph dict
state.hash              # MD5 hash of graph file
state.get_stats()       # Node/edge counts, type distributions
state.list_graph_files()  # Find all graph JSONs in watch_dir
```

### FileWatcher

```python
from viz.watcher import FileWatcher

def on_change(data):
    print(f"Graph updated: {len(data['nodes'])} nodes")

watcher = FileWatcher("memory.json", interval=0.5, on_change=on_change)
watcher.start()   # Background thread polls file mtime
watcher.stop()
```

### Export Functions

```python
from viz.export import export_tikz, export_dot, export_latex_tables, export_csv

graph_data = {"nodes": [...], "edges": [...]}

tikz_code = export_tikz(graph_data, layout="spring", scale=3.0, paper_mode=True)
dot_code  = export_dot(graph_data)
tables    = export_latex_tables(graph_data)
csv_text  = export_csv(graph_data)
```

| Function | Output | Use Case |
|----------|--------|----------|
| `export_tikz(data, layout, scale, show_confidence, paper_mode)` | TikZ/PGF code | Direct `\input{}` in LaTeX |
| `export_dot(data)` | Graphviz DOT | Compile with `dot` → PDF/SVG |
| `export_latex_tables(data)` | LaTeX `tabular` environments | Node/edge listing tables |
| `export_csv(data)` | CSV text | Data appendices, pgfplots |

### Demo Graph Generator

```bash
python -m viz.generate_demo --output demo.json --nodes 25
```

```python
from viz.generate_demo import build_demo_graph

graph = build_demo_graph(node_count=20)
graph.save_to_file("demo.json")
```
