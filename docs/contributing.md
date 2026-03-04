# Contributing to Dagestan

## Development Setup

```bash
git clone https://github.com/nabin/dagestan.git
cd dagestan
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/ -v
```

All tests should pass before submitting changes. Currently 63 tests covering schema, graph operations, extraction, and retrieval.

## Code Structure

- `dagestan/graph/` — Core graph data structures and algorithms
- `dagestan/extraction/` — LLM-based knowledge extraction
- `dagestan/curation/` — Graph maintenance pipeline
- `dagestan/retrieval/` — Query-driven retrieval
- `dagestan/storage/` — Persistence backends
- `tests/` — Unit tests

## Guidelines

- Keep dependencies minimal. Core functionality should work with stdlib only.
- LLM calls should be isolated in extraction and curation. Graph operations must never call an LLM.
- Write tests for new functionality.
- Use type hints consistently.
- Be honest in documentation. If something isn't benchmarked, say so.

## Areas Where Help Is Needed

- **SQLite storage backend** (v0.2) — replace JSON with proper persistence
- **Semantic matching in retrieval** — lightweight embedding support without heavy dependencies
- **Benchmark design** — tasks that meaningfully test temporal reasoning and contradiction handling
- **More node/edge types** — if real usage reveals gaps in the current ontology
- **Performance profiling** — how does the graph scale to 10k+ nodes?

## Reporting Issues

File issues on GitHub. Include:
- What you tried
- What happened
- What you expected
- Python version and OS
