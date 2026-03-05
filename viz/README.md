# Dagestan Graph Visualizer

A live, interactive web UI for visually debugging the temporal knowledge graphs created by Dagestan. Zero external dependencies — uses only Python stdlib and CDN-loaded vis-network.

## Quick Start

```bash
# From project root — auto-detects demo_memory.json / dagestan_memory.json
python -m viz.server

# Specify a graph file and port
python -m viz.server --file demo_memory.json --port 8765

# Bind to all interfaces (e.g. for remote access)
python -m viz.server --host 0.0.0.0 --port 8765
```

Then open **http://localhost:8765** in your browser.

## Generate a Demo Graph

```bash
python -m viz.generate_demo --output viz_demo_graph.json --nodes 25
python -m viz.server --file viz_demo_graph.json
```

## Features

### Graph Rendering
- **Force-directed layout** via vis-network with physics simulation
- **Node shapes by type** — Entity (circle), Concept (diamond), Event (star), Preference (triangle), Goal (hexagon)
- **Color-coded types** — blue, purple, orange, green, red
- **Confidence visualization** — node opacity/border intensity reflects confidence score; color shifts green → yellow → red as confidence decays
- **Edge styling** — arrow direction, color, and dash pattern by relationship type

### Live Updates
- **Auto-refresh** — the server watches the graph JSON file on disk (stat-based polling via `watcher.py`)
- **Server-Sent Events (SSE)** — push updates to the browser without polling; falls back to hash-based polling
- **Diff highlighting** — new nodes glow green with a ✦ marker on live updates
- **Diff dashboard** — shows count of added/removed nodes and edges after each update

### Inspection
- **Node inspector** — click any node to see type, label, confidence, decay rate, timestamps, and attributes
- **Edge inspector** — click any edge to see relationship type, confidence, source/target labels
- **Raw JSON inspector** — button to view the full raw graph JSON for debugging

### Navigation & Interaction
- **Neighborhood explorer** — double-click a node to zoom into its 1-hop neighborhood
- **Reset view** — double-click empty space to reset to full graph
- **Search** — find nodes by label (keyboard shortcut: `/`)
- **Type filters** — toggle each of the 5 node types on/off
- **Confidence filter** — filter nodes by confidence range
- **File switcher** — browse and switch between graph JSON files in the project

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `R` | Refresh graph data |
| `F` | Fit graph to viewport |
| `/` | Focus search box |
| `?` | Show help modal |
| `Esc` | Clear selection / close panels |

### Statistics Dashboard
- Node and edge counts
- Type distribution breakdown
- Average confidence score
- Count of low-confidence nodes
- Confidence histogram (via Chart.js)

### Export for Research Papers

The visualizer includes export endpoints for academic use:

```bash
# TikZ/PGF (native LaTeX graph drawing)
curl "http://localhost:8765/api/export?format=tikz"

# Graphviz DOT
curl "http://localhost:8765/api/export?format=dot"

# LaTeX tables
curl "http://localhost:8765/api/export?format=latex_tables"

# CSV (node + edge tables)
curl "http://localhost:8765/api/export?format=csv"

# List all available formats
curl "http://localhost:8765/api/export/formats"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main UI page |
| `/api/graph` | GET | Full graph JSON snapshot |
| `/api/graph/stats` | GET | Graph statistics (counts, distributions, confidence) |
| `/api/graph/hash` | GET | MD5 hash for change detection |
| `/api/files` | GET | List available graph JSON files in project |
| `/api/events` | GET | SSE stream — pushes `graph-update` events on file change |
| `/api/export?format=tikz` | GET | Export graph (tikz, dot, latex_tables, csv) |
| `/api/export/formats` | GET | List available export formats |
| `/api/switch?file=path` | GET | Switch to a different graph file |

## Architecture

```
viz/
├── __init__.py
├── __main__.py           # Entry point for python -m viz
├── server.py             # Stdlib HTTP server + REST API + SSE push
├── watcher.py            # File-change polling (stat-based, no deps)
├── export.py             # LaTeX/TikZ, Graphviz DOT, CSV export
├── generate_demo.py      # Generate demo graphs for testing
└── static/
    ├── index.html        # Main UI page (dark theme)
    ├── style.css         # Styling
    └── app.js            # vis-network graph rendering + all UI logic
```

## Design Principles

- **Zero dependencies** — server is pure Python stdlib; frontend loads vis-network and Chart.js from CDN
- **File-driven** — reads standard Dagestan graph JSON files; no database or special format needed
- **Live by default** — file changes trigger automatic browser updates via SSE
- **Research-friendly** — export to TikZ/DOT/CSV for direct inclusion in LaTeX papers
