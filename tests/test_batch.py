"""Tests for scue.batch — the reusable batch processing utility."""

import asyncio
import gc
from unittest.mock import MagicMock, patch

import pytest

from scue.batch import BatchItemError, BatchResult, run_batch, run_batch_async


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identity_processor(item, index):
    """Success for every item."""
    return None


def _skip_even(item, index):
    """Skip even-indexed items."""
    if index % 2 == 0:
        return "even index"
    return None


def _fail_on_third(item, index):
    """Raise on the third item (index 2)."""
    if index == 2:
        raise ValueError(f"bad item: {item}")
    return None


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


class TestBasicSuccess:
    def test_all_succeed(self):
        result = run_batch([1, 2, 3, 4, 5], _identity_processor)
        assert result.total == 5
        assert result.succeeded == 5
        assert result.failed == 0
        assert result.skipped == 0
        assert result.cancelled is False
        assert result.errors == []

    def test_empty_list(self):
        result = run_batch([], _identity_processor)
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0


class TestPerItemErrorHandling:
    def test_error_recorded_and_continues(self):
        result = run_batch([10, 20, 30, 40, 50], _fail_on_third)
        assert result.succeeded == 4
        assert result.failed == 1
        assert len(result.errors) == 1

        err = result.errors[0]
        assert err.index == 2
        assert err.item == 30
        assert "ValueError" in err.error
        assert "bad item: 30" in err.error
        assert isinstance(err.exception, ValueError)

    def test_stop_on_error(self):
        result = run_batch(
            [10, 20, 30, 40, 50],
            _fail_on_third,
            stop_on_error=True,
        )
        assert result.succeeded == 2
        assert result.failed == 1
        # Items 40 and 50 were never reached
        assert result.succeeded + result.failed == 3


class TestSkipItems:
    def test_skip_counted(self):
        result = run_batch([0, 1, 2, 3, 4, 5], _skip_even)
        # Indices 0, 2, 4 skipped; 1, 3, 5 succeeded
        assert result.skipped == 3
        assert result.succeeded == 3
        assert result.failed == 0


class TestCancellation:
    def test_cancel_after_three(self):
        call_count = 0

        def cancel_after_3():
            return call_count >= 3

        def counting_processor(item, index):
            nonlocal call_count
            call_count += 1
            return None

        result = run_batch(
            list(range(10)),
            counting_processor,
            cancel_check=cancel_after_3,
        )
        assert result.cancelled is True
        assert result.succeeded == 3
        assert result.total == 10  # original list size preserved


class TestProgress:
    def test_progress_every(self):
        cb = MagicMock()
        run_batch(
            list(range(10)),
            _identity_processor,
            progress=cb,
            progress_every=3,
            progress_message="Testing",
        )
        # Called at indices 0, 3, 6, 9, plus final tick
        calls = cb.call_args_list
        # First four are the loop ticks
        assert calls[0].args == (0, 10, "Testing")
        assert calls[1].args == (3, 10, "Testing")
        assert calls[2].args == (6, 10, "Testing")
        assert calls[3].args == (9, 10, "Testing")
        # Final tick
        assert calls[-1].args == (10, 10, "Testing")

    def test_progress_on_empty(self):
        cb = MagicMock()
        run_batch([], _identity_processor, progress=cb, progress_message="Empty")
        # Final tick only
        assert cb.call_count == 1
        assert cb.call_args.args == (0, 0, "Empty")


class TestGC:
    def test_gc_every_two(self):
        with patch.object(gc, "collect") as mock_gc:
            run_batch(
                list(range(6)),
                _identity_processor,
                gc_every=2,
            )
            # After items at index 1, 3, 5 → (i+1) % 2 == 0
            assert mock_gc.call_count == 3

    def test_gc_disabled_by_default(self):
        with patch.object(gc, "collect") as mock_gc:
            run_batch(list(range(10)), _identity_processor)
            assert mock_gc.call_count == 0


class TestErrorDetails:
    def test_exception_preserved(self):
        def raise_type_error(item, index):
            raise TypeError("wrong type")

        result = run_batch(["a"], raise_type_error)
        assert result.failed == 1
        err = result.errors[0]
        assert isinstance(err.exception, TypeError)
        assert err.error == "TypeError: wrong type"


class TestAsync:
    def test_run_batch_async(self):
        async def _run():
            return await run_batch_async(
                [1, 2, 3],
                _identity_processor,
            )

        result = asyncio.run(_run())
        assert result.total == 3
        assert result.succeeded == 3
