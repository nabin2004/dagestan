
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

    # Core entity
    alice = Node(type=NodeType.ENTITY, label="Alice")

    # Concepts
    python = Node(type=NodeType.CONCEPT, label="Python")
    ai = Node(type=NodeType.CONCEPT, label="Artificial Intelligence")
    coffee = Node(type=NodeType.CONCEPT, label="Coffee")

    # Goals
    startup = Node(type=NodeType.GOAL, label="Build a startup")
    learn_ai = Node(type=NodeType.GOAL, label="Learn AI")

    # Preferences
    likes_python = Node(type=NodeType.PREFERENCE, label="likes python")
    likes_coffee = Node(type=NodeType.PREFERENCE, label="likes coffee")

    # Add nodes
    for n in [alice, python, ai, coffee, startup, learn_ai, likes_python, likes_coffee]:
        mem.add_node(n)

    # Edges
    mem.add_edge(Edge(alice.id, python.id, EdgeType.HAS_PREFERENCE))
    mem.add_edge(Edge(alice.id, coffee.id, EdgeType.HAS_PREFERENCE))

    mem.add_edge(Edge(alice.id, startup.id, EdgeType.WANTS))
    mem.add_edge(Edge(alice.id, learn_ai.id, EdgeType.WANTS))

    mem.add_edge(Edge(learn_ai.id, ai.id, EdgeType.RELATES_TO))
    mem.add_edge(Edge(startup.id, ai.id, EdgeType.RELATES_TO))    
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
