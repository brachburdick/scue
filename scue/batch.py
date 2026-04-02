"""Reusable batch processing utility.

Provides ``run_batch()`` — a single function that wraps any per-item
processor with progress reporting, cancellation, per-item error isolation,
and optional GC.  Callsites supply a ``processor`` callback; the utility
handles the cross-cutting concerns that otherwise get re-implemented (or
forgotten) in every batch loop.
"""

from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

ProgressFn = Callable[[int, int, str], None]  # (current, total, message)
CancelCheckFn = Callable[[], bool]
ProcessorFn = Callable[[T, int], "str | None"]  # (item, index) -> skip reason or None


@dataclass
class BatchItemError:
    """Details of a single item failure within a batch run."""

    index: int
    item: object
    error: str  # "{TypeName}: {message}"
    exception: Exception


@dataclass
class BatchResult:
    """Outcome of a ``run_batch()`` call."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False
    errors: list[BatchItemError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def run_batch(
    items: list[T],
    processor: ProcessorFn,
    *,
    progress: ProgressFn | None = None,
    progress_every: int = 1,
    progress_message: str = "Processing",
    cancel_check: CancelCheckFn | None = None,
    gc_every: int = 0,
    gil_yield_every: int = 0,
    stop_on_error: bool = False,
) -> BatchResult:
    """Process *items* one at a time with uniform cross-cutting concerns.

    Parameters
    ----------
    items:
        The batch to process.  Materialised once for ``len()``.
    processor:
        ``(item, index) -> str | None``.  Return ``None`` on success,
        a non-empty string to skip the item (counted in ``skipped``),
        or raise an exception to record a failure.
    progress:
        Optional ``(current, total, message)`` callback.
    progress_every:
        Emit progress every *N* items (1 = every item).
    progress_message:
        Static label passed to the progress callback.
    cancel_check:
        ``() -> bool``.  Checked **before** each item.  When it returns
        ``True`` the loop breaks and ``result.cancelled`` is set.
    gc_every:
        Call ``gc.collect()`` every *N* items (0 = disabled).
    gil_yield_every:
        Call ``time.sleep(0.001)`` every *N* items to explicitly yield the GIL.
        Useful when a CPU-heavy thread-pool batch needs the asyncio event loop
        to keep servicing WebSocket broadcasts or other callbacks.
    stop_on_error:
        If ``True``, break on the first failure instead of continuing.

    Returns
    -------
    BatchResult
        Accumulated counts and error details.  Inspect
        ``result.cancelled`` to decide whether to raise a
        domain-specific exception.
    """
    result = BatchResult(total=len(items))

    for i, item in enumerate(items):
        # --- cancellation ---
        if cancel_check is not None and cancel_check():
            result.cancelled = True
            break

        # --- progress ---
        if progress is not None and i % progress_every == 0:
            progress(i, result.total, progress_message)

        # --- explicit GIL yield ---
        if gil_yield_every > 0 and i > 0 and i % gil_yield_every == 0:
            time.sleep(0.001)

        # --- process ---
        try:
            skip_reason = processor(item, i)
            if skip_reason is not None:
                result.skipped += 1
            else:
                result.succeeded += 1
        except Exception as exc:
            err = BatchItemError(
                index=i,
                item=item,
                error=f"{type(exc).__name__}: {exc}",
                exception=exc,
            )
            result.errors.append(err)
            result.failed += 1
            logger.warning(
                "Batch [%d/%d] failed: %s",
                i + 1,
                result.total,
                err.error,
            )
            if stop_on_error:
                break

        # --- gc ---
        if gc_every > 0 and (i + 1) % gc_every == 0:
            gc.collect()

    # Always emit a final progress tick so UIs never freeze at "95%".
    if progress is not None:
        count = result.succeeded + result.failed + result.skipped
        progress(count, result.total, progress_message)

    return result


# ---------------------------------------------------------------------------
# Async convenience wrapper
# ---------------------------------------------------------------------------


async def run_batch_async(
    items: list[T],
    processor: ProcessorFn,
    **kwargs,
) -> BatchResult:
    """Run :func:`run_batch` in a thread-pool executor."""
    import asyncio

    return await asyncio.to_thread(run_batch, items, processor, **kwargs)
