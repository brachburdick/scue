# Skill: Python / FastAPI / asyncio

> **When to use:** Any backend task involving Python source code, FastAPI endpoints, async patterns, or data models.

---

## Stack & Environment

- Python 3.11+ via `.venv/bin/python` (NEVER bare `python`)
- FastAPI for REST + WebSocket endpoints
- asyncio for all real-time paths
- Dataclasses for all data models (not raw dicts)
- Type hints required on all function signatures
- `logging` module only — no `print()`
- Tests: pytest, run with `.venv/bin/python -m pytest`

## Common Patterns

### Data Models
- All models are `@dataclass` classes in `models.py` within each layer
- Models that cross layer boundaries must be defined in `docs/CONTRACTS.md`
- Use `from __future__ import annotations` for forward references

### Async
- All real-time paths (bridge events, WebSocket handlers) are async
- Use `asyncio.create_task()` for fire-and-forget operations
- Never block the event loop with synchronous I/O

### API Endpoints
- Routers in `scue/api/` — one file per domain
- WebSocket for real-time data, REST for CRUD
- All FE/BE boundary types must match `frontend/src/types/`

## Known Gotchas

- `ModuleNotFoundError` usually means you're using system Python, not the venv
- JSON files in `tracks/` are the source of truth; SQLite in `cache/` is derived only
- [TODO: Fill from project experience]

## Anti-Patterns

- Raw dicts instead of dataclasses for structured data
- `print()` instead of `logging`
- Synchronous I/O in async handlers
- Importing across layer boundaries without going through contracts
- [TODO: Fill from project experience]
