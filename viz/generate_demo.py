#!/usr/bin/env python3
"""
Generate a rich demo graph for the visualizer.

Usage:
    python -m viz.generate_demo [--output FILE] [--nodes N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dagestan.graph.schema import Node, Edge, NodeType, EdgeType
from dagestan.graph.temporal_graph import TemporalGraph


def build_demo_graph(node_count: int = 20) -> TemporalGraph:
    """Build a realistic demo knowledge graph."""
    g = TemporalGraph()

    # ── Entities ─────────────────────────────────────────
    alice = g.add_node(Node(type=NodeType.ENTITY, label="Alice", attributes={"role": "engineer"}))
    bob = g.add_node(Node(type=NodeType.ENTITY, label="Bob", attributes={"role": "designer"}))
    startup = g.add_node(Node(type=NodeType.ENTITY, label="TechCorp", attributes={"industry": "AI"}))
    python = g.add_node(Node(type=NodeType.ENTITY, label="Python", attributes={"category": "language"}))
    rust = g.add_node(Node(type=NodeType.ENTITY, label="Rust", attributes={"category": "language"}))
    sf = g.add_node(Node(type=NodeType.ENTITY, label="San Francisco", attributes={"type": "city"}))

    # ── Concepts ─────────────────────────────────────────
    ml = g.add_node(Node(type=NodeType.CONCEPT, label="Machine Learning", attributes={"domain": "AI"}))
    graphs = g.add_node(Node(type=NodeType.CONCEPT, label="Knowledge Graphs", attributes={"domain": "AI"}))
    memory = g.add_node(Node(type=NodeType.CONCEPT, label="LLM Memory Systems", attributes={"domain": "AI"}))
    ux = g.add_node(Node(type=NodeType.CONCEPT, label="User Experience Design"))
    distributed = g.add_node(Node(type=NodeType.CONCEPT, label="Distributed Systems"))
    temporal = g.add_node(Node(type=NodeType.CONCEPT, label="Temporal Reasoning"))

    # ── Events ───────────────────────────────────────────
    launch = g.add_node(Node(type=NodeType.EVENT, label="Product Launch v1.0", confidence_score=0.9))
    meeting = g.add_node(Node(type=NodeType.EVENT, label="Team Planning Meeting", confidence_score=0.7))
    hackathon = g.add_node(Node(type=NodeType.EVENT, label="AI Hackathon 2026", confidence_score=0.85))
    bug_fix = g.add_node(Node(type=NodeType.EVENT, label="Critical Bug Fix", confidence_score=0.6))

    # ── Preferences ──────────────────────────────────────
    pref_coffee = g.add_node(Node(type=NodeType.PREFERENCE, label="Loves coffee", confidence_score=0.95))
    pref_dark_mode = g.add_node(Node(type=NodeType.PREFERENCE, label="Prefers dark mode", confidence_score=0.8))
    pref_tea = g.add_node(Node(type=NodeType.PREFERENCE, label="Switched to tea", confidence_score=0.3))
    pref_vim = g.add_node(Node(type=NodeType.PREFERENCE, label="Uses Vim", confidence_score=0.75))

    # ── Goals ────────────────────────────────────────────
    goal_launch = g.add_node(Node(type=NodeType.GOAL, label="Launch by Q2 2026", confidence_score=0.85))
    goal_funding = g.add_node(Node(type=NodeType.GOAL, label="Raise Series A", confidence_score=0.6))
    goal_scale = g.add_node(Node(type=NodeType.GOAL, label="Scale to 1M users", confidence_score=0.4))
    goal_learn = g.add_node(Node(type=NodeType.GOAL, label="Learn Rust deeply", confidence_score=0.7))

    # ── Edges ────────────────────────────────────────────
    # Alice's world
    g.add_edge(Edge(source_id=alice.id, target_id=python.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=alice.id, target_id=ml.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=alice.id, target_id=startup.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=alice.id, target_id=pref_coffee.id, type=EdgeType.HAS_PREFERENCE))
    g.add_edge(Edge(source_id=alice.id, target_id=pref_tea.id, type=EdgeType.HAS_PREFERENCE))
    g.add_edge(Edge(source_id=alice.id, target_id=pref_dark_mode.id, type=EdgeType.HAS_PREFERENCE))
    g.add_edge(Edge(source_id=alice.id, target_id=goal_launch.id, type=EdgeType.WANTS))
    g.add_edge(Edge(source_id=alice.id, target_id=goal_learn.id, type=EdgeType.WANTS))
    g.add_edge(Edge(source_id=alice.id, target_id=sf.id, type=EdgeType.RELATES_TO))

    # Bob's world
    g.add_edge(Edge(source_id=bob.id, target_id=ux.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=bob.id, target_id=startup.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=bob.id, target_id=pref_vim.id, type=EdgeType.HAS_PREFERENCE))
    g.add_edge(Edge(source_id=bob.id, target_id=goal_funding.id, type=EdgeType.WANTS))

    # Concept relationships
    g.add_edge(Edge(source_id=ml.id, target_id=graphs.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=graphs.id, target_id=memory.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=memory.id, target_id=temporal.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=distributed.id, target_id=rust.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=python.id, target_id=ml.id, type=EdgeType.RELATES_TO))

    # Event relationships
    g.add_edge(Edge(source_id=meeting.id, target_id=launch.id, type=EdgeType.HAPPENED_BEFORE))
    g.add_edge(Edge(source_id=launch.id, target_id=goal_launch.id, type=EdgeType.CAUSED))
    g.add_edge(Edge(source_id=hackathon.id, target_id=graphs.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=bug_fix.id, target_id=launch.id, type=EdgeType.HAPPENED_BEFORE))

    # Contradiction: loves coffee vs switched to tea
    g.add_edge(Edge(source_id=pref_coffee.id, target_id=pref_tea.id, type=EdgeType.CONTRADICTS))

    # Goal chain
    g.add_edge(Edge(source_id=goal_launch.id, target_id=goal_funding.id, type=EdgeType.HAPPENED_BEFORE))
    g.add_edge(Edge(source_id=goal_funding.id, target_id=goal_scale.id, type=EdgeType.HAPPENED_BEFORE))

    # Company context
    g.add_edge(Edge(source_id=startup.id, target_id=sf.id, type=EdgeType.RELATES_TO))
    g.add_edge(Edge(source_id=startup.id, target_id=memory.id, type=EdgeType.RELATES_TO))

    return g


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo graph for visualizer")
    parser.add_argument("--output", "-o", default="viz_demo_graph.json", help="Output file")
    parser.add_argument("--nodes", "-n", type=int, default=20, help="Approx number of nodes")
    args = parser.parse_args()

    g = build_demo_graph(args.nodes)
    output_path = Path(args.output)
    g.save_to_file(output_path)

    print(f"✓ Generated demo graph: {output_path}")
    print(f"  Nodes: {g.node_count}")
    print(f"  Edges: {g.edge_count}")
    print(f"\n  Run:  python -m viz.server --file {output_path}")


if __name__ == "__main__":
    main()
