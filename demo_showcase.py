"""
Dagestan Feature Showcase Script

This script demonstrates the main features of the Dagestan project:
- LLM-based extraction (if LLM is configured)
- Manual graph building
- Hybrid retrieval (graph + vector)
- Curation (decay, contradiction detection)
- Strategy/context summary
- Graph snapshot/export

Run this script after installing dependencies and (optionally) configuring LLM API keys.
"""

from dagestan import Dagestan, Node, Edge, NodeType, EdgeType
import os
import time

# --- Config ---
DB_PATH = "./demo_memory.json"

# Remove previous demo DB if exists
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

print("\n=== Dagestan Feature Showcase ===\n")

# --- 1. Initialize Dagestan (no LLM for demo, set provider="openai" for extraction) ---
mem = Dagestan(db_path=DB_PATH, auto_save=True)

# --- 2. Manual Graph Building ---
print("Adding nodes and edges manually...")
alice = mem.add_node(Node(type=NodeType.ENTITY, label="Alice"))
python = mem.add_node(Node(type=NodeType.CONCEPT, label="Python Programming"))
goal = mem.add_node(Node(type=NodeType.GOAL, label="Build a startup"))
pref = mem.add_node(Node(type=NodeType.PREFERENCE, label="Prefers coffee"))
mem.add_edge(Edge(source_id=alice.id, target_id=python.id, type=EdgeType.HAS_PREFERENCE))
mem.add_edge(Edge(source_id=alice.id, target_id=goal.id, type=EdgeType.WANTS))
mem.add_edge(Edge(source_id=alice.id, target_id=pref.id, type=EdgeType.HAS_PREFERENCE))

print(f"Nodes: {mem.node_count}, Edges: {mem.edge_count}")

# --- 3. Hybrid Retrieval (graph + vector) ---
print("\nHybrid retrieval for: 'What does Alice care about?'")
context = mem.retrieve("What does Alice care about?", as_text=True)
print(context)

# --- 4. Curation (decay, contradiction detection) ---
print("\nRunning curation pipeline...")
report = mem.curate()
print(f"Nodes decayed: {report.nodes_decayed}")
print(f"Contradictions found: {report.contradictions_found}")
print(f"Gaps found: {report.gaps_found}")
print(f"Bridges found: {report.bridges_found}")

# --- 5. Strategy/Context Summary ---
print("\nStrategy summary:")
strategy = mem.strategy(as_text=True)
print(strategy)

# --- 6. Graph Snapshot/Export ---
print("\nGraph snapshot:")
snapshot = mem.snapshot()
print(snapshot)

print("\n=== Demo complete. ===\n")
