"""
dagestan.cli
~~~~~~~~~~~~

Command-line interface for inspecting and managing Dagestan graph state.

Usage:
    dagestan info [--db PATH]
    dagestan nodes [--type TYPE] [--db PATH]
    dagestan edges [--node NODE] [--db PATH]
    dagestan retrieve QUERY [--top-k K] [--db PATH]
    dagestan curate [--db PATH]
    dagestan strategy [--db PATH]
    dagestan export [--output PATH] [--db PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .graph.operations import compute_centrality
from .graph.schema import NodeType
from .graph.temporal_graph import TemporalGraph
from .retrieval.retriever import Retriever
from .storage.store import JSONStorage


def _load_graph(db_path: str) -> TemporalGraph:
    """Load graph from storage."""
    graph = TemporalGraph()
    storage = JSONStorage(path=db_path)
    if storage.exists():
        storage.load(graph)
    return graph


def cmd_info(args: argparse.Namespace) -> None:
    """Show graph summary."""
    graph = _load_graph(args.db)
    centrality = compute_centrality(graph)

    print(f"Dagestan Memory Graph")
    print(f"  Storage: {args.db}")
    print(f"  Nodes: {graph.node_count}")
    print(f"  Edges: {graph.edge_count}")
    print()

    if graph.node_count > 0:
        # Type breakdown
        type_counts: dict[str, int] = {}
        for node in graph.nodes:
            type_counts[node.type.value] = type_counts.get(node.type.value, 0) + 1
        print("  Node types:")
        for t, c in sorted(type_counts.items()):
            print(f"    {t}: {c}")
        print()

        # Top nodes by centrality
        top = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]
        if top:
            print("  Top nodes (by centrality):")
            for nid, score in top:
                node = graph.get_node(nid)
                if node:
                    print(
                        f"    [{node.type.value}] {node.label} "
                        f"(centrality={score:.3f}, confidence={node.confidence_score:.2f})"
                    )


def cmd_nodes(args: argparse.Namespace) -> None:
    """List nodes in the graph."""
    graph = _load_graph(args.db)
    nodes = graph.nodes

    if args.type:
        try:
            node_type = NodeType(args.type.lower())
            nodes = [n for n in nodes if n.type == node_type]
        except ValueError:
            print(f"Unknown node type: {args.type}")
            print(f"Valid types: {', '.join(t.value for t in NodeType)}")
            sys.exit(1)

    if not nodes:
        print("No nodes found.")
        return

    for node in sorted(nodes, key=lambda n: n.confidence_score, reverse=True):
        print(
            f"  [{node.type.value}] {node.label} "
            f"(id={node.id}, confidence={node.confidence_score:.2f})"
        )
        if node.attributes:
            for k, v in node.attributes.items():
                print(f"    {k}: {v}")


def cmd_edges(args: argparse.Namespace) -> None:
    """List edges in the graph."""
    graph = _load_graph(args.db)

    if args.node:
        # Find edges for a specific node
        matches = graph.get_nodes_by_label(args.node)
        if not matches:
            print(f"No node found matching: {args.node}")
            return
        edges = []
        for m in matches:
            edges.extend(graph.get_edges(node_id=m.id))
    else:
        edges = graph.edges

    if not edges:
        print("No edges found.")
        return

    for edge in edges:
        source = graph.get_node(edge.source_id)
        target = graph.get_node(edge.target_id)
        s_label = source.label if source else edge.source_id
        t_label = target.label if target else edge.target_id
        print(
            f"  {s_label} --[{edge.type.value}]--> {t_label} "
            f"(confidence={edge.confidence_score:.2f})"
        )


def cmd_retrieve(args: argparse.Namespace) -> None:
    """Retrieve context for a query."""
    graph = _load_graph(args.db)
    retriever = Retriever()
    text = retriever.retrieve_as_text(graph, args.query, top_k=args.top_k)
    print(text)


def cmd_curate(args: argparse.Namespace) -> None:
    """Run curation pipeline (no LLM — flag-only mode)."""
    from .curation.curator import Curator

    graph = _load_graph(args.db)
    curator = Curator(llm_client=None)
    report = curator.run_curation(graph)

    # Save back
    storage = JSONStorage(path=args.db)
    storage.save(graph)

    print(f"Curation complete:")
    print(f"  Nodes decayed: {report.nodes_decayed}")
    print(f"  Contradictions found: {report.contradictions_found}")
    print(f"  Gaps found: {report.gaps_found}")
    print(f"  Bridges found: {report.bridges_found}")

    if report.details:
        print()
        for detail in report.details:
            dtype = detail.get("type", "unknown")
            desc = detail.get("description", detail.get("reasoning", ""))
            print(f"  [{dtype}] {desc}")


def cmd_strategy(args: argparse.Namespace) -> None:
    """Generate context strategy."""
    from .curation.strategy import generate_strategy, strategy_to_prompt

    graph = _load_graph(args.db)
    strat = generate_strategy(graph)
    print(strategy_to_prompt(strat))


def cmd_export(args: argparse.Namespace) -> None:
    """Export graph as JSON."""
    graph = _load_graph(args.db)
    output = args.output or "-"

    data = graph.snapshot()

    if output == "-":
        print(json.dumps(data, indent=2))
    else:
        with open(output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Exported to {output}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="dagestan",
        description="Dagestan — Temporal Graph Memory Layer for LLMs",
    )
    parser.add_argument(
        "--db",
        default="./dagestan_memory.json",
        help="Path to the graph storage file (default: ./dagestan_memory.json)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # info
    subparsers.add_parser("info", help="Show graph summary")

    # nodes
    nodes_parser = subparsers.add_parser("nodes", help="List nodes")
    nodes_parser.add_argument("--type", help="Filter by node type")

    # edges
    edges_parser = subparsers.add_parser("edges", help="List edges")
    edges_parser.add_argument("--node", help="Filter by node label")

    # retrieve
    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve context")
    retrieve_parser.add_argument("query", help="Query string")
    retrieve_parser.add_argument("--top-k", type=int, default=10, help="Max results")

    # curate
    subparsers.add_parser("curate", help="Run curation pipeline")

    # strategy
    subparsers.add_parser("strategy", help="Generate context strategy")

    # export
    export_parser = subparsers.add_parser("export", help="Export graph as JSON")
    export_parser.add_argument("--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "info": cmd_info,
        "nodes": cmd_nodes,
        "edges": cmd_edges,
        "retrieve": cmd_retrieve,
        "curate": cmd_curate,
        "strategy": cmd_strategy,
        "export": cmd_export,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
