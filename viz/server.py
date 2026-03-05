"""
viz.server
~~~~~~~~~~

Lightweight HTTP server for the Dagestan graph visualizer.
Uses only Python stdlib — no Flask, no FastAPI, no extra deps.

Serves:
- GET /                → static/index.html
- GET /static/*        → static files (JS, CSS)
- GET /api/graph       → current graph JSON snapshot
- GET /api/graph/stats → graph statistics
- GET /api/graph/hash  → hash of current graph (for change detection)
- GET /api/files       → list available graph JSON files
- GET /api/events      → Server-Sent Events stream for live updates
- GET /api/export      → export graph in LaTeX-friendly formats
- GET /api/export/formats → list available export formats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

# Add project root to path so we can import dagestan
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STATIC_DIR = Path(__file__).resolve().parent / "static"


class GraphState:
    """Holds the current graph data and tracks changes."""

    def __init__(self, graph_path: str | Path | None = None, watch_dir: str | Path | None = None):
        self.graph_path: Path | None = Path(graph_path) if graph_path else None
        self.watch_dir: Path = Path(watch_dir) if watch_dir else PROJECT_ROOT
        self._data: dict[str, Any] = {}
        self._hash: str = ""
        self._last_modified: float = 0
        self.reload()

    def reload(self) -> bool:
        """Reload from disk. Returns True if data changed."""
        if self.graph_path and self.graph_path.exists():
            try:
                mtime = self.graph_path.stat().st_mtime
                if mtime == self._last_modified:
                    return False
                self._last_modified = mtime
                with open(self.graph_path) as f:
                    raw = f.read()
                self._data = json.loads(raw)
                new_hash = hashlib.md5(raw.encode()).hexdigest()
                changed = new_hash != self._hash
                self._hash = new_hash
                return changed
            except (json.JSONDecodeError, OSError) as e:
                print(f"[viz] Warning: Failed to read {self.graph_path}: {e}")
                return False
        return False

    @property
    def data(self) -> dict[str, Any]:
        self.reload()
        return self._data

    @property
    def hash(self) -> str:
        self.reload()
        return self._hash

    def get_stats(self) -> dict[str, Any]:
        """Compute stats about the current graph."""
        data = self.data
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        node_types: dict[str, int] = {}
        confidence_sum = 0.0
        low_confidence = 0
        for n in nodes:
            ntype = n.get("type", "unknown")
            node_types[ntype] = node_types.get(ntype, 0) + 1
            conf = n.get("confidence_score", 1.0)
            confidence_sum += conf
            if conf < 0.5:
                low_confidence += 1

        edge_types: dict[str, int] = {}
        for e in edges:
            etype = e.get("type", "unknown")
            edge_types[etype] = edge_types.get(etype, 0) + 1

        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": node_types,
            "edge_types": edge_types,
            "avg_confidence": round(confidence_sum / len(nodes), 4) if nodes else 0,
            "low_confidence_nodes": low_confidence,
            "timestamp": data.get("timestamp", ""),
            "file": str(self.graph_path) if self.graph_path else None,
        }

    def list_graph_files(self) -> list[dict[str, Any]]:
        """Find all .json files in the watch directory that look like graph files."""
        files = []
        for p in sorted(self.watch_dir.glob("**/*.json")):
            # Skip node_modules, .venv, etc.
            parts = p.parts
            if any(part.startswith(".") or part in ("node_modules", "__pycache__") for part in parts):
                continue
            try:
                with open(p) as f:
                    data = json.load(f)
                if "nodes" in data and "edges" in data:
                    files.append({
                        "path": str(p.relative_to(self.watch_dir)),
                        "absolute": str(p),
                        "node_count": data.get("node_count", len(data.get("nodes", []))),
                        "edge_count": data.get("edge_count", len(data.get("edges", []))),
                        "timestamp": data.get("timestamp", ""),
                        "size": p.stat().st_size,
                    })
            except (json.JSONDecodeError, OSError):
                pass
        return files


# Global state
_state: GraphState | None = None


def _json_response(handler: "VizHandler", data: Any, status: int = 200) -> None:
    """Send a JSON response."""
    body = json.dumps(data, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _serve_static(handler: "VizHandler", path: str) -> None:
    """Serve a static file."""
    if path == "" or path == "/":
        file_path = STATIC_DIR / "index.html"
    else:
        # Sanitize path to prevent directory traversal
        clean = path.lstrip("/").replace("..", "")
        file_path = STATIC_DIR / clean

    if not file_path.exists() or not file_path.is_file():
        handler.send_error(404, f"Not found: {path}")
        return

    content_type, _ = mimetypes.guess_type(str(file_path))
    content_type = content_type or "application/octet-stream"

    with open(file_path, "rb") as f:
        body = f.read()

    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer that handles each request in a new thread (needed for SSE)."""
    daemon_threads = True


class VizHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the graph visualizer."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == "/api/graph":
            assert _state is not None
            _json_response(self, _state.data)
        elif path == "/api/graph/stats":
            assert _state is not None
            _json_response(self, _state.get_stats())
        elif path == "/api/graph/hash":
            assert _state is not None
            _json_response(self, {"hash": _state.hash})
        elif path == "/api/files":
            assert _state is not None
            _json_response(self, _state.list_graph_files())
        elif path == "/api/events":
            # Server-Sent Events for live push updates
            self._serve_sse()
            return
        elif path == "/api/export/formats":
            from .export import EXPORT_FORMATS
            _json_response(self, EXPORT_FORMATS)
        elif path == "/api/export":
            self._handle_export(params)
        elif path == "/api/switch":
            # Switch to a different graph file
            file_path = params.get("file", [None])[0]
            if file_path and _state:
                abs_path = _state.watch_dir / file_path
                if abs_path.exists():
                    _state.graph_path = abs_path
                    _state._last_modified = 0
                    _state.reload()
                    _json_response(self, {"ok": True, "file": str(abs_path)})
                else:
                    _json_response(self, {"error": f"File not found: {file_path}"}, 404)
            else:
                _json_response(self, {"error": "Missing ?file= parameter"}, 400)
        # Static files
        elif path.startswith("/static/"):
            _serve_static(self, path[len("/static/"):])
        elif path == "/" or path == "/index.html":
            _serve_static(self, "/")
        elif path == "/favicon.ico":
            handler = self
            handler.send_response(204)
            handler.end_headers()
        else:
            _serve_static(self, path)

    def _handle_export(self, params: dict[str, list[str]]) -> None:
        """Handle export requests — generate LaTeX/DOT/CSV output."""
        from .export import export_graph

        assert _state is not None
        fmt = (params.get("format") or params.get("fmt") or ["tikz"])[0]

        # Collect optional kwargs
        kwargs: dict[str, Any] = {}
        if "layout" in params:
            kwargs["layout"] = params["layout"][0]
        if "scale" in params:
            kwargs["scale"] = float(params["scale"][0])
        if "show_confidence" in params:
            kwargs["show_confidence"] = params["show_confidence"][0] != "false"
        if "show_edge_labels" in params:
            kwargs["show_edge_labels"] = params["show_edge_labels"][0] != "false"
        if "paper_mode" in params:
            kwargs["paper_mode"] = params["paper_mode"][0] != "false"
        if "monochrome" in params:
            kwargs["monochrome"] = params["monochrome"][0] == "true"
        if "rankdir" in params:
            kwargs["rankdir"] = params["rankdir"][0]
        if "booktabs" in params:
            kwargs["booktabs"] = params["booktabs"][0] != "false"

        try:
            content, filename, content_type = export_graph(_state.data, fmt, **kwargs)
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, 400)
            return

        # Check if client wants inline preview or file download
        if params.get("preview", [""])[0] == "true":
            _json_response(self, {
                "format": fmt,
                "filename": filename,
                "content": content,
            })
        else:
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

    def _serve_sse(self) -> None:
        """Server-Sent Events stream — pushes graph updates to the client."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        assert _state is not None
        last_hash = _state.hash

        try:
            while True:
                _state.reload()
                current_hash = _state.hash
                if current_hash != last_hash:
                    last_hash = current_hash
                    event_data = json.dumps({
                        "type": "graph_update",
                        "hash": current_hash,
                        "node_count": len(_state._data.get("nodes", [])),
                        "edge_count": len(_state._data.get("edges", [])),
                    })
                    self.wfile.write(f"event: update\ndata: {event_data}\n\n".encode())
                    self.wfile.flush()
                else:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()

                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Client disconnected

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logs for API polling, keep others."""
        if "/api/graph/hash" in str(args) or "/api/events" in str(args):
            return  # Don't spam logs for poll/SSE requests
        super().log_message(format, *args)


def main() -> None:
    global _state

    parser = argparse.ArgumentParser(description="Dagestan Graph Visualizer")
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="Path to graph JSON file (default: auto-detect)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8765,
        help="Port to serve on (default: 8765)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    # Auto-detect graph file if not specified
    graph_file = args.file
    if graph_file is None:
        candidates = [
            PROJECT_ROOT / "demo_memory.json",
            PROJECT_ROOT / "dagestan_memory.json",
            PROJECT_ROOT / "memory.json",
        ]
        for c in candidates:
            if c.exists():
                graph_file = str(c)
                break

    if graph_file is None:
        print("[viz] No graph file found. The UI will show an empty graph.")
        print("[viz] Create a graph file or specify one with --file")

    _state = GraphState(
        graph_path=graph_file,
        watch_dir=PROJECT_ROOT,
    )

    server = ThreadedHTTPServer((args.host, args.port), VizHandler)
    url = f"http://{args.host}:{args.port}"

    print(f"""
╔══════════════════════════════════════════════════╗
║       🔷 Dagestan Graph Visualizer 🔷            ║
╠══════════════════════════════════════════════════╣
║  URL:   {url:<40s}║
║  File:  {str(graph_file or 'None'):<40s}║
║  Press Ctrl+C to stop                           ║
╚══════════════════════════════════════════════════╝
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[viz] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
