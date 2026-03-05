
from dagestan import Dagestan, Node, Edge, NodeType, EdgeType
import os


def main():
    print("=== Dagestan Demo ===\n")

    # Remove previous demo DB if exists
    db_path = "./demo_memory.json"
    if os.path.exists(db_path):
        os.remove(db_path)

    # Initialize Dagestan (no LLM for demo)
    mem = Dagestan(db_path=db_path, auto_save=True)

    # Manual graph building
    print("Adding nodes and edges manually...")
    alice = Node(type=NodeType.ENTITY, label="Alice")
    python = Node(type=NodeType.CONCEPT, label="Python Programming")
    startup = Node(type=NodeType.GOAL, label="Build a startup")
    mem.add_node(alice)
    mem.add_node(python)
    mem.add_node(startup)
    mem.add_edge(Edge(source_id=alice.id, target_id=python.id, type=EdgeType.HAS_PREFERENCE))
    mem.add_edge(Edge(source_id=alice.id, target_id=startup.id, type=EdgeType.WANTS))

    print(f"Nodes: {mem.node_count}, Edges: {mem.edge_count}")

    # Retrieve context
    print("\nRetrieving context for: 'What does Alice care about?'")
    context = mem.retrieve("What does Alice care about?")
    print(context)

    # Run curation (decay, contradictions, gaps)
    print("\nRunning curation...")
    report = mem.curate()
    print(f"Contradictions found: {getattr(report, 'contradictions_found', 'N/A')}")

    # Generate strategy summary
    print("\nStrategy summary:")
    strategy = mem.strategy()
    print(strategy)

    # Show snapshot
    print("\nGraph snapshot:")
    snapshot = mem.snapshot()
    print(snapshot)

    print("\nDemo complete.")


if __name__ == "__main__":
    main()
