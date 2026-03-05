# Dagestan Graph Visualizer

A live, interactive web UI for visually debugging the temporal knowledge graphs created by Dagestan.

## Quick Start

```bash
# From project root
python -m viz.server

# Or specify a graph file
python -m viz.server --file demo_memory.json --port 8765
```

Then open **http://localhost:8765** in your browser.

## Features

- **Live Graph Rendering** — Interactive force-directed graph using vis-network
- **Auto-Refresh** — Watches the graph JSON file and updates the UI in real-time
- **Node Inspector** — Click any node to see full metadata, confidence, decay rate
- **Edge Inspector** — Click any edge to see relationship details
- **Stats Dashboard** — Node/edge counts, type distributions, confidence histograms
- **Temporal Decay View** — Color-coded confidence levels (green → yellow → red)
- **Filter by Type** — Toggle node types on/off
- **Search** — Find nodes by label
- **Zero Dependencies** — Uses only Python stdlib + CDN libraries

## Architecture

```
viz/
├── __init__.py
├── __main__.py       # Entry point for python -m viz
├── server.py         # HTTP server + API endpoints
└── static/
    ├── index.html    # Main UI page
    ├── style.css     # Styling
    └── app.js        # Graph visualization logic
```
