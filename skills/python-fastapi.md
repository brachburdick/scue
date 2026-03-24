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
- **`async def` vs `def` for CPU-bound work:** FastAPI runs `async def` endpoints on the main event loop. CPU-bound work (audio analysis, file parsing, batch processing) blocks the loop. Use plain `def` (FastAPI runs it in a threadpool) or wrap with `asyncio.to_thread()`. The batch analysis path does this correctly — follow that pattern.
- **Route registration order:** FastAPI matches routes top-to-bottom. Parameterized routes (`/{track_id}`) registered before specific routes (`/batch`, `/status`) will swallow the specific routes. Always register specific routes first, catch-all/parameterized routes last within a router.
- **Undeclared dependencies:** If you `import` a new package, add it to `pyproject.toml` immediately. Transitive deps that work in dev will crash in fresh venvs.

## Anti-Patterns

- Raw dicts instead of dataclasses for structured data
- `print()` instead of `logging`
- Synchronous I/O in async handlers
- `async def` for CPU-bound background tasks (blocks the event loop)
- Parameterized routes before specific routes in the same router
- Importing across layer boundaries without going through contracts
- Using a new dependency without adding it to `pyproject.toml`
