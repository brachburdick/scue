# Spec: allin1-mlx Installation & Integration Hardening

## Summary

The `allin1-mlx` package (Apple Silicon ML model for music structure analysis) was missing from the venv, causing every analysis run to silently fall back to the much weaker librosa-only beat tracker. This spec addresses installation, dependency management, and the event loop blocking bug that affects all API-triggered analysis.

---

## Current State

### Problem 1: Package not installed

`allin1-mlx` was not installed in the venv and is not listed in `pyproject.toml` dependencies. Every call to `analyze_structure()` caught the `ImportError` and fell back to `_analyze_fallback()` (librosa-only).

**Impact:** Librosa fallback produces:
- Beat tracking only (no ML-based section segmentation)
- Downbeats estimated as every 4th beat (heuristic)
- One monolithic section covering the full track (ruptures then splits it)
- `source: "fallback"` instead of `source: "allin1"`

**Fix (done):** `pip install all-in-one-mlx` — now installed. Package name on PyPI is `all-in-one-mlx`, import name is `allin1_mlx`.

### Problem 2: Not in pyproject.toml

If the venv is recreated, allin1-mlx will be missing again.

### Problem 3: Event loop blocking (existing known bug)

Documented in `docs/bugs/layer1-analysis.md` (2026-03-20, HIGH severity). `_run_analysis_task()` runs `run_analysis()` synchronously via FastAPI `BackgroundTasks`, blocking the event loop. All WebSocket broadcasts, health checks, and async handlers stall during analysis.

This is separate from the missing package but affects the same code path.

---

## Implementation Tasks

### Task 1: Add to pyproject.toml optional dependencies

```toml
[project.optional-dependencies]
analysis = [
    "librosa>=0.10.0",
    "ruptures>=1.1.0",
    "all-in-one-mlx>=1.0.5",  # Apple Silicon only — structure analysis ML model
]
```

Note: `all-in-one-mlx` is macOS/Apple Silicon only. This aligns with the Windows compatibility plan in CLAUDE.md — the `allin1-mlx` dependency has a known platform limitation and will need a PyTorch/ONNX alternative for Windows (Phase 2 of the Windows compat plan).

### Task 2: Add startup availability check

In `scue/main.py` startup, log whether allin1-mlx is available:

```python
try:
    import allin1_mlx
    logger.info("allin1-mlx available (v%s) — ML structure analysis enabled",
                getattr(allin1_mlx, "__version__", "unknown"))
except ImportError:
    logger.warning("allin1-mlx not installed — falling back to librosa-only structure analysis")
```

This makes it immediately obvious on server start whether ML analysis is active.

### Task 3: MLX model weights management

`_find_weights_dir()` in `sections.py` searches upward for a `mlx-weights/` directory. Currently:
- If found, passed as `mlx_weights_dir` to `allin1_mlx.analyze()`
- If not found, allin1-mlx downloads from HuggingFace on first run

Decision needed: should we pre-download weights during setup, or let allin1-mlx handle it on first use? First-use download is simpler but adds a surprise ~500MB download on first analysis.

### Task 4: Improve error handling in analyze_structure

Currently only `ImportError` is caught. Other failures (OOM, Metal errors, corrupt weights) would crash the analysis pipeline. Broaden the catch:

```python
def analyze_structure(audio_path: str) -> StructureResult:
    try:
        return _analyze_with_allin1(audio_path)
    except ImportError:
        logger.warning("allin1-mlx not available, falling back to librosa-only analysis")
        return _analyze_fallback(audio_path)
    except Exception:
        logger.exception("allin1-mlx failed, falling back to librosa-only analysis")
        return _analyze_fallback(audio_path)
```

### Task 5: Fix event loop blocking (separate but related)

Convert `_run_analysis_task()` in `scue/api/tracks.py` from `BackgroundTasks` to explicit `asyncio.to_thread()`:

```python
# Before:
background_tasks.add_task(_run_analysis_task, audio_path, force, skip_waveform)

# After:
asyncio.create_task(asyncio.to_thread(_run_analysis_task, audio_path, force, skip_waveform))
```

This matches the pattern already used in `_run_batch_analysis()` at tracks.py and keeps the event loop responsive during CPU-heavy analysis.

---

## Key Files

| What | Where |
|------|-------|
| Structure analysis + fallback | `scue/layer1/detectors/sections.py` |
| Analysis pipeline orchestrator | `scue/layer1/analysis.py` |
| API analysis trigger | `scue/api/tracks.py` — `_run_analysis_task()` |
| Server startup | `scue/main.py` |
| Dependencies | `pyproject.toml` |
| Known bug log | `docs/bugs/layer1-analysis.md` |
| MLX weights search | `sections.py` — `_find_weights_dir()` |

---

## Acceptance Criteria

- [ ] `all-in-one-mlx` listed in pyproject.toml optional `analysis` deps
- [ ] Server startup log shows allin1-mlx availability status
- [ ] `analyze_structure()` catches all exceptions (not just ImportError)
- [ ] API-triggered analysis does not block the event loop
- [ ] Analysis with allin1-mlx produces `source: "allin1"` in StructureResult
- [ ] Analysis without allin1-mlx still works (graceful fallback)

---

## Platform Notes

- `all-in-one-mlx` requires Apple Silicon (M1+) and macOS
- MLX Metal backend won't work on Intel Macs or Linux/Windows
- Windows compatibility plan (CLAUDE.md) already identifies this as Phase 2 work
- The librosa fallback remains the cross-platform path
