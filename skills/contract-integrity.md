# Contract Integrity — SCUE

## When This Applies
Load this skill when your task is tagged with `Interface Scope: PRODUCER` or `CONSUMER`.

## Stack Context
- **Backend:** Python dataclasses, FastAPI endpoints, WebSocket message handlers
- **Frontend:** TypeScript interfaces in `frontend/src/types/`, Zustand stores, WebSocket message consumers
- **Contract files:** `docs/CONTRACTS.md`, `docs/interfaces.md`, type definitions in both layers

## Field Preservation Checklist
Before declaring COMPLETE on a PRODUCER or CONSUMER task:
1. Open the field inventory from the CONTRACT_ONLY task (or `docs/interfaces.md`).
2. For each field in the inventory:
   - PRODUCER: verify your code emits this field with the correct name, type, and required/optional status.
   - CONSUMER: verify your code reads and uses this field. Check default handling for optional fields.
3. If you added or removed a field not in the inventory, STOP — flag `[INTERFACE IMPACT]`.

## Common Patterns
- WebSocket payloads: Python dataclass → `asdict()` → JSON → TypeScript type. Field names must match exactly (Python snake_case converted at serialization boundary).
- REST responses: FastAPI Pydantic model → JSON → TypeScript type.
- Zustand stores consume WebSocket messages — check store update handlers match payload shape.

## Known Gotchas
- [TODO: Fill from project experience — e.g., fields that were silently dropped in past sessions]
- Python `Optional[T]` fields default to `None` but TypeScript `T | undefined` behaves differently at runtime.
- `asdict()` on nested dataclasses produces nested dicts, not flat — consumer must handle nesting.

## Anti-Patterns
- Changing a dataclass field without updating the corresponding TypeScript type (or vice versa).
- Adding a field to the producer without updating test fixtures in `tests/fixtures/`.
- Assuming a field rename in one layer will be caught by type checking in the other layer (cross-language boundary is not type-checked).
