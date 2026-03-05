r"""
viz.export
~~~~~~~~~~

Export graph data to LaTeX-friendly formats for research papers.

Supported formats:
- TikZ/PGF      — native LaTeX graph drawing (\includegraphics not needed)
- LaTeX tables   — tabular environments for node/edge listings
- DOT (Graphviz) — use with dot2tex or \includegraphics on compiled .pdf
- CSV            — node/edge tables for pgfplots or data appendices
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime
from typing import Any


# ── TikZ color mappings (for print-friendly academic papers) ───────

TIKZ_NODE_COLORS: dict[str, str] = {
    "entity":     "blue!60!black",
    "concept":    "violet!70!black",
    "event":      "orange!80!black",
    "preference": "green!60!black",
    "goal":       "red!70!black",
}

TIKZ_NODE_SHAPES: dict[str, str] = {
    "entity":     "circle",
    "concept":    "diamond",
    "event":      "star",
    "preference": "regular polygon, regular polygon sides=3",
    "goal":       "regular polygon, regular polygon sides=6",
}

TIKZ_EDGE_STYLES: dict[str, str] = {
    "relates_to":      "",
    "caused":          "thick, orange!80!black",
    "contradicts":     "thick, dashed, red!70!black",
    "happened_before": "dotted, gray",
    "has_preference":  "green!60!black",
    "wants":           "red!70!black, ->",
}


def _sanitize_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "\\": r"\textbackslash{}",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def _short_id(node_id: str) -> str:
    """Create a valid TikZ node name from ID."""
    return f"n{node_id.replace('-', '').replace(' ', '')}"


def _format_edge_label(edge_type: str) -> str:
    """Format edge type as readable label."""
    return edge_type.replace("_", " ")


# ════════════════════════════════════════════════════════════
# TikZ Export
# ════════════════════════════════════════════════════════════

def export_tikz(
    data: dict[str, Any],
    *,
    layout: str = "spring",
    scale: float = 3.0,
    show_confidence: bool = True,
    show_edge_labels: bool = True,
    paper_mode: bool = True,
    font_size: str = "\\small",
) -> str:
    """
    Export graph as TikZ/PGF code for direct inclusion in LaTeX.

    Args:
        data: Graph snapshot dict with 'nodes' and 'edges'.
        layout: Layout algorithm — 'spring', 'circular', or 'layered'.
        scale: Scale factor for node positions.
        show_confidence: Annotate confidence scores on nodes.
        show_edge_labels: Show relationship labels on edges.
        paper_mode: Use print-friendly colors (black/gray-based).
        font_size: LaTeX font size command for labels.

    Returns:
        Complete TikZ code string (includable with \\input{}).
    """
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        return "% Empty graph — no nodes to render\n"

    # Compute layout positions
    positions = _compute_layout(nodes, edges, layout, scale)

    lines: list[str] = []

    # Preamble comment
    lines.append("% " + "=" * 62)
    lines.append("% Dagestan Temporal Knowledge Graph — TikZ Export")
    lines.append(f"% Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"% Nodes: {len(nodes)}, Edges: {len(edges)}")
    lines.append("% " + "=" * 62)
    lines.append("%")
    lines.append("% Required packages:")
    lines.append("%   \\usepackage{tikz}")
    lines.append("%   \\usetikzlibrary{shapes, arrows.meta, positioning, calc}")
    lines.append("%")
    lines.append("")

    # Style definitions
    lines.append("\\begin{tikzpicture}[")
    lines.append("    >=Stealth,")
    lines.append(f"    every node/.style={{font={font_size}}},")

    # Node type styles
    for ntype, color in TIKZ_NODE_COLORS.items():
        shape = TIKZ_NODE_SHAPES[ntype]
        if paper_mode:
            fill_color = f"{color}!15"
            draw_color = f"{color}"
        else:
            fill_color = f"{color}!25"
            draw_color = f"{color}!80"
        lines.append(
            f"    {ntype}node/.style={{draw={draw_color}, fill={fill_color}, "
            f"{shape}, minimum size=8mm, inner sep=1.5pt, line width=0.6pt}},"
        )

    # Edge type styles
    for etype, style in TIKZ_EDGE_STYLES.items():
        etype_clean = etype.replace("_", "")
        base = f"->, {style}" if "->" not in style else style
        if not base.startswith("->"):
            base = "-> , " + base if base else "->"
        lines.append(f"    {etype_clean}edge/.style={{{base}}},")

    lines.append("]")
    lines.append("")

    # Build node ID map
    node_map = {n["id"]: n for n in nodes}

    # Render nodes
    lines.append("% ── Nodes ──────────────────────")
    for node in nodes:
        nid = _short_id(node["id"])
        ntype = node.get("type", "entity")
        label = _sanitize_latex(node.get("label", node["id"]))
        conf = node.get("confidence_score", 1.0)
        x, y = positions.get(node["id"], (0, 0))

        style = f"{ntype}node"

        # Scale opacity/line width by confidence
        if show_confidence and conf < 0.9:
            opacity = max(0.3, conf)
            style += f", opacity={opacity:.2f}"

        conf_annotation = ""
        if show_confidence:
            conf_pct = int(conf * 100)
            conf_annotation = f" \\\\[-2pt] {{\\tiny {conf_pct}\\%}}"

        lines.append(
            f"\\node[{style}] ({nid}) at ({x:.2f}, {y:.2f}) "
            f"{{{label}{conf_annotation}}};"
        )

    lines.append("")

    # Render edges
    lines.append("% ── Edges ──────────────────────")
    for edge in edges:
        src = _short_id(edge["source_id"])
        tgt = _short_id(edge["target_id"])
        etype = edge.get("type", "relates_to")
        etype_clean = etype.replace("_", "")
        conf = edge.get("confidence_score", 1.0)

        # Skip edges to nonexistent nodes
        if edge["source_id"] not in node_map or edge["target_id"] not in node_map:
            continue

        style = f"{etype_clean}edge"
        if conf < 0.9:
            opacity = max(0.2, conf)
            style += f", opacity={opacity:.2f}"

        label_part = ""
        if show_edge_labels:
            elabel = _sanitize_latex(_format_edge_label(etype))
            label_part = f" node[midway, above, font=\\scriptsize, text=gray] {{{elabel}}}"

        # Bend slightly to avoid overlapping edges
        bend = ""
        lines.append(f"\\draw[{style}{bend}] ({src}) to{label_part} ({tgt});")

    lines.append("")
    lines.append("\\end{tikzpicture}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# LaTeX Tables Export
# ════════════════════════════════════════════════════════════

def export_latex_tables(
    data: dict[str, Any],
    *,
    include_nodes: bool = True,
    include_edges: bool = True,
    include_stats: bool = True,
    booktabs: bool = True,
    caption_prefix: str = "Knowledge Graph",
) -> str:
    """
    Export graph as LaTeX tabular environments.

    Generates publication-ready tables using booktabs formatting.

    Args:
        data: Graph snapshot dict.
        include_nodes: Include node table.
        include_edges: Include edge table.
        include_stats: Include summary statistics table.
        booktabs: Use booktabs package (\\toprule, \\midrule, \\bottomrule).
        caption_prefix: Prefix for table captions.

    Returns:
        LaTeX code string with table environments.
    """
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    lines: list[str] = []

    top = r"\toprule" if booktabs else r"\hline"
    mid = r"\midrule" if booktabs else r"\hline"
    bot = r"\bottomrule" if booktabs else r"\hline"

    lines.append("% " + "=" * 62)
    lines.append("% Dagestan Knowledge Graph — LaTeX Tables")
    lines.append(f"% Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("% Required: \\usepackage{booktabs}" if booktabs else "")
    lines.append("% " + "=" * 62)
    lines.append("")

    # ── Summary statistics table ─────────────
    if include_stats:
        type_counts: dict[str, int] = {}
        total_conf = 0.0
        for n in nodes:
            ntype = n.get("type", "unknown")
            type_counts[ntype] = type_counts.get(ntype, 0) + 1
            total_conf += n.get("confidence_score", 1.0)
        avg_conf = total_conf / len(nodes) if nodes else 0

        edge_type_counts: dict[str, int] = {}
        for e in edges:
            etype = e.get("type", "unknown")
            edge_type_counts[etype] = edge_type_counts.get(etype, 0) + 1

        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append(f"\\caption{{{_sanitize_latex(caption_prefix)} — Summary Statistics}}")
        lines.append("\\label{tab:graph-stats}")
        lines.append("\\begin{tabular}{lr}")
        lines.append(top)
        lines.append(r"\textbf{Metric} & \textbf{Value} \\")
        lines.append(mid)
        lines.append(f"Total Nodes & {len(nodes)} \\\\")
        lines.append(f"Total Edges & {len(edges)} \\\\")
        lines.append(f"Avg. Confidence & {avg_conf:.2f} \\\\")
        lines.append(mid)
        for ntype, count in sorted(type_counts.items()):
            lines.append(f"\\quad {_sanitize_latex(ntype.title())} nodes & {count} \\\\")
        lines.append(mid)
        for etype, count in sorted(edge_type_counts.items()):
            lines.append(f"\\quad {_sanitize_latex(etype.replace('_', ' ').title())} edges & {count} \\\\")
        lines.append(bot)
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
        lines.append("")

    # ── Node table ───────────────────────────
    if include_nodes:
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append(f"\\caption{{{_sanitize_latex(caption_prefix)} — Node Inventory}}")
        lines.append("\\label{tab:graph-nodes}")
        lines.append("\\begin{tabular}{llccc}")
        lines.append(top)
        lines.append(
            r"\textbf{Label} & \textbf{Type} & \textbf{Confidence} "
            r"& \textbf{Decay Rate} & \textbf{Source} \\"
        )
        lines.append(mid)

        # Sort by type then label
        sorted_nodes = sorted(nodes, key=lambda n: (n.get("type", ""), n.get("label", "")))
        for n in sorted_nodes:
            label = _sanitize_latex(n.get("label", "—"))
            ntype = _sanitize_latex(n.get("type", "—"))
            conf = n.get("confidence_score", 1.0)
            decay = n.get("decay_rate", 0)
            source = _sanitize_latex(n.get("source", "—") or "—")
            lines.append(f"{label} & {ntype} & {conf:.2f} & {decay:.4f} & {source} \\\\")

        lines.append(bot)
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
        lines.append("")

    # ── Edge table ───────────────────────────
    if include_edges:
        node_map = {n["id"]: n.get("label", n["id"]) for n in nodes}

        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append(f"\\caption{{{_sanitize_latex(caption_prefix)} — Edge Relations}}")
        lines.append("\\label{tab:graph-edges}")
        lines.append("\\begin{tabular}{llll}")
        lines.append(top)
        lines.append(
            r"\textbf{Source} & \textbf{Relation} & \textbf{Target} "
            r"& \textbf{Confidence} \\"
        )
        lines.append(mid)

        sorted_edges = sorted(edges, key=lambda e: e.get("type", ""))
        for e in sorted_edges:
            src = _sanitize_latex(node_map.get(e["source_id"], e["source_id"][:8]))
            tgt = _sanitize_latex(node_map.get(e["target_id"], e["target_id"][:8]))
            etype = _sanitize_latex(e.get("type", "—").replace("_", " "))
            conf = e.get("confidence_score", 1.0)
            lines.append(f"{src} & {etype} & {tgt} & {conf:.2f} \\\\")

        lines.append(bot)
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
        lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# DOT (Graphviz) Export
# ════════════════════════════════════════════════════════════

DOT_NODE_COLORS: dict[str, str] = {
    "entity":     "#3a7ebf",
    "concept":    "#9b6ec4",
    "event":      "#c88520",
    "preference": "#2f9e42",
    "goal":       "#c9443a",
}

DOT_NODE_SHAPES: dict[str, str] = {
    "entity":     "ellipse",
    "concept":    "diamond",
    "event":      "star",
    "preference": "triangle",
    "goal":       "hexagon",
}


def export_dot(
    data: dict[str, Any],
    *,
    graph_name: str = "DagestanGraph",
    rankdir: str = "LR",
    show_confidence: bool = True,
    show_edge_labels: bool = True,
    monochrome: bool = False,
) -> str:
    """
    Export graph in DOT (Graphviz) format.

    Can be compiled with:
        dot -Tpdf graph.dot -o graph.pdf
        dot -Tsvg graph.dot -o graph.svg

    Or used with dot2tex for native LaTeX rendering:
        dot2tex --figonly graph.dot > graph.tex

    Args:
        data: Graph snapshot dict.
        graph_name: Name for the digraph.
        rankdir: Layout direction (LR, TB, BT, RL).
        show_confidence: Show confidence in labels.
        show_edge_labels: Show edge type labels.
        monochrome: Use grayscale (better for B&W printing).
    """
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_map = {n["id"]: n for n in nodes}

    lines: list[str] = []
    lines.append(f'digraph {graph_name} {{')
    lines.append(f'    rankdir={rankdir};')
    lines.append('    bgcolor="transparent";')
    lines.append('    node [fontname="Helvetica", fontsize=10, style="filled"];')
    lines.append('    edge [fontname="Helvetica", fontsize=8];')
    lines.append('    pad=0.5;')
    lines.append('    nodesep=0.6;')
    lines.append('    ranksep=0.8;')
    lines.append('')

    # Group nodes by type using subgraphs
    nodes_by_type: dict[str, list[dict]] = {}
    for n in nodes:
        ntype = n.get("type", "entity")
        nodes_by_type.setdefault(ntype, []).append(n)

    for ntype, type_nodes in sorted(nodes_by_type.items()):
        lines.append(f'    // {ntype.upper()} nodes')

        if monochrome:
            fill = "#e0e0e0"
            border = "#404040"
        else:
            fill = DOT_NODE_COLORS.get(ntype, "#888888") + "30"
            border = DOT_NODE_COLORS.get(ntype, "#888888")

        shape = DOT_NODE_SHAPES.get(ntype, "ellipse")

        for n in type_nodes:
            nid = _short_id(n["id"])
            label = n.get("label", n["id"]).replace('"', '\\"')
            conf = n.get("confidence_score", 1.0)

            if show_confidence:
                label_text = f'{label}\\n({conf:.0%})'
            else:
                label_text = label

            penwidth = max(0.5, conf * 2.0)
            lines.append(
                f'    {nid} [label="{label_text}", shape={shape}, '
                f'fillcolor="{fill}", color="{border}", penwidth={penwidth:.1f}];'
            )
        lines.append('')

    # Edges
    lines.append('    // Edges')
    for e in edges:
        if e["source_id"] not in node_map or e["target_id"] not in node_map:
            continue

        src = _short_id(e["source_id"])
        tgt = _short_id(e["target_id"])
        etype = e.get("type", "relates_to")
        conf = e.get("confidence_score", 1.0)

        attrs: list[str] = []

        if show_edge_labels:
            elabel = etype.replace("_", " ")
            attrs.append(f'label="{elabel}"')

        if monochrome:
            attrs.append('color="#404040"')
        else:
            ecolor = {
                "relates_to": "#888888",
                "caused": "#c88520",
                "contradicts": "#c9443a",
                "happened_before": "#aaaaaa",
                "has_preference": "#2f9e42",
                "wants": "#c9443a",
            }.get(etype, "#888888")
            attrs.append(f'color="{ecolor}"')

        penwidth = max(0.5, conf * 1.5)
        attrs.append(f'penwidth={penwidth:.1f}')

        if etype == "contradicts":
            attrs.append('style=dashed')

        attr_str = ", ".join(attrs)
        lines.append(f'    {src} -> {tgt} [{attr_str}];')

    lines.append('}')

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# CSV Export
# ════════════════════════════════════════════════════════════

def export_csv_nodes(data: dict[str, Any]) -> str:
    """Export nodes as CSV (for pgfplots or data appendices)."""
    nodes = data.get("nodes", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "label", "type", "confidence", "decay_rate", "created_at", "source"])
    for n in sorted(nodes, key=lambda x: (x.get("type", ""), x.get("label", ""))):
        writer.writerow([
            n["id"],
            n.get("label", ""),
            n.get("type", ""),
            f'{n.get("confidence_score", 1.0):.4f}',
            f'{n.get("decay_rate", 0):.4f}',
            n.get("created_at", ""),
            n.get("source", ""),
        ])
    return output.getvalue()


def export_csv_edges(data: dict[str, Any]) -> str:
    """Export edges as CSV."""
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_map = {n["id"]: n.get("label", n["id"]) for n in nodes}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "source_id", "source_label", "target_id", "target_label", "type", "confidence", "created_at"])
    for e in sorted(edges, key=lambda x: x.get("type", "")):
        writer.writerow([
            e["id"],
            e["source_id"],
            node_map.get(e["source_id"], ""),
            e["target_id"],
            node_map.get(e["target_id"], ""),
            e.get("type", ""),
            f'{e.get("confidence_score", 1.0):.4f}',
            e.get("created_at", ""),
        ])
    return output.getvalue()


# ════════════════════════════════════════════════════════════
# Layout Computation  (for TikZ positioning)
# ════════════════════════════════════════════════════════════

def _compute_layout(
    nodes: list[dict],
    edges: list[dict],
    layout: str,
    scale: float,
) -> dict[str, tuple[float, float]]:
    """Compute 2D positions for nodes."""
    if layout == "circular":
        return _circular_layout(nodes, scale)
    elif layout == "layered":
        return _layered_layout(nodes, edges, scale)
    else:  # spring
        return _spring_layout(nodes, edges, scale)


def _circular_layout(
    nodes: list[dict], scale: float
) -> dict[str, tuple[float, float]]:
    """Place nodes in a circle, grouped by type."""
    positions: dict[str, tuple[float, float]] = {}
    n = len(nodes)
    if n == 0:
        return positions

    # Sort by type for visual grouping
    sorted_nodes = sorted(nodes, key=lambda x: x.get("type", ""))
    for i, node in enumerate(sorted_nodes):
        angle = 2 * math.pi * i / n
        x = scale * math.cos(angle)
        y = scale * math.sin(angle)
        positions[node["id"]] = (round(x, 2), round(y, 2))

    return positions


def _layered_layout(
    nodes: list[dict], edges: list[dict], scale: float
) -> dict[str, tuple[float, float]]:
    """Layer nodes by type vertically."""
    positions: dict[str, tuple[float, float]] = {}
    type_order = ["entity", "concept", "event", "preference", "goal"]

    by_type: dict[str, list[dict]] = {}
    for n in nodes:
        ntype = n.get("type", "entity")
        by_type.setdefault(ntype, []).append(n)

    for layer_idx, ntype in enumerate(type_order):
        type_nodes = by_type.get(ntype, [])
        y = -layer_idx * scale * 0.8
        n = len(type_nodes)
        for i, node in enumerate(type_nodes):
            x = (i - (n - 1) / 2) * scale * 0.7
            positions[node["id"]] = (round(x, 2), round(y, 2))

    # Catch any types not in type_order
    extra_layer = len(type_order)
    for ntype, type_nodes in by_type.items():
        if ntype in type_order:
            continue
        y = -extra_layer * scale * 0.8
        n = len(type_nodes)
        for i, node in enumerate(type_nodes):
            x = (i - (n - 1) / 2) * scale * 0.7
            positions[node["id"]] = (round(x, 2), round(y, 2))
        extra_layer += 1

    return positions


def _spring_layout(
    nodes: list[dict],
    edges: list[dict],
    scale: float,
    iterations: int = 80,
) -> dict[str, tuple[float, float]]:
    """Simple force-directed layout (Fruchterman-Reingold inspired)."""
    import random
    random.seed(42)  # Deterministic layout

    n = len(nodes)
    if n == 0:
        return {}

    # Initialize with random positions
    pos: dict[str, list[float]] = {}
    for node in nodes:
        pos[node["id"]] = [random.uniform(-scale, scale), random.uniform(-scale, scale)]

    # Build adjacency
    adj: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    for e in edges:
        if e["source_id"] in adj and e["target_id"] in adj:
            adj[e["source_id"]].add(e["target_id"])
            adj[e["target_id"]].add(e["source_id"])

    area = (2 * scale) ** 2
    k = math.sqrt(area / max(n, 1))  # Optimal distance
    temp = scale  # Temperature for simulated annealing

    node_ids = [node["id"] for node in nodes]

    for iteration in range(iterations):
        # Repulsive forces
        disp: dict[str, list[float]] = {nid: [0.0, 0.0] for nid in node_ids}

        for i, u in enumerate(node_ids):
            for j in range(i + 1, len(node_ids)):
                v = node_ids[j]
                dx = pos[u][0] - pos[v][0]
                dy = pos[u][1] - pos[v][1]
                dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
                force = k * k / dist
                fx = dx / dist * force
                fy = dy / dist * force
                disp[u][0] += fx
                disp[u][1] += fy
                disp[v][0] -= fx
                disp[v][1] -= fy

        # Attractive forces
        for e in edges:
            u, v = e["source_id"], e["target_id"]
            if u not in pos or v not in pos:
                continue
            dx = pos[u][0] - pos[v][0]
            dy = pos[u][1] - pos[v][1]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
            force = dist * dist / k
            fx = dx / dist * force
            fy = dy / dist * force
            disp[u][0] -= fx
            disp[u][1] -= fy
            disp[v][0] += fx
            disp[v][1] += fy

        # Apply displacements (limited by temperature)
        for nid in node_ids:
            dx, dy = disp[nid]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
            clamp = min(dist, temp)
            pos[nid][0] += dx / dist * clamp
            pos[nid][1] += dy / dist * clamp
            # Keep within bounds
            pos[nid][0] = max(-scale * 1.5, min(scale * 1.5, pos[nid][0]))
            pos[nid][1] = max(-scale * 1.5, min(scale * 1.5, pos[nid][1]))

        temp *= 0.95  # Cool down

    return {nid: (round(p[0], 2), round(p[1], 2)) for nid, p in pos.items()}


# ════════════════════════════════════════════════════════════
# Unified Export Dispatcher
# ════════════════════════════════════════════════════════════

EXPORT_FORMATS = {
    "tikz": {
        "name": "TikZ/PGF",
        "ext": ".tex",
        "mime": "application/x-tex",
        "desc": "Native LaTeX graph — \\input{graph.tex}",
    },
    "latex_tables": {
        "name": "LaTeX Tables",
        "ext": ".tex",
        "mime": "application/x-tex",
        "desc": "booktabs tables for node/edge data",
    },
    "dot": {
        "name": "DOT (Graphviz)",
        "ext": ".dot",
        "mime": "text/vnd.graphviz",
        "desc": "Compile with dot or use dot2tex",
    },
    "csv_nodes": {
        "name": "CSV (Nodes)",
        "ext": ".csv",
        "mime": "text/csv",
        "desc": "Node data for pgfplots / appendices",
    },
    "csv_edges": {
        "name": "CSV (Edges)",
        "ext": ".csv",
        "mime": "text/csv",
        "desc": "Edge data for pgfplots / appendices",
    },
}


def export_graph(
    data: dict[str, Any],
    fmt: str,
    **kwargs: Any,
) -> tuple[str, str, str]:
    """
    Export graph in the specified format.

    Returns:
        (content, filename, content_type)
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")

    if fmt == "tikz":
        content = export_tikz(data, **kwargs)
        return content, f"dagestan_graph_{timestamp}.tex", "application/x-tex"

    elif fmt == "latex_tables":
        content = export_latex_tables(data, **kwargs)
        return content, f"dagestan_tables_{timestamp}.tex", "application/x-tex"

    elif fmt == "dot":
        content = export_dot(data, **kwargs)
        return content, f"dagestan_graph_{timestamp}.dot", "text/vnd.graphviz"

    elif fmt == "csv_nodes":
        content = export_csv_nodes(data)
        return content, f"dagestan_nodes_{timestamp}.csv", "text/csv"

    elif fmt == "csv_edges":
        content = export_csv_edges(data)
        return content, f"dagestan_edges_{timestamp}.csv", "text/csv"

    else:
        raise ValueError(f"Unknown export format: {fmt!r}")
