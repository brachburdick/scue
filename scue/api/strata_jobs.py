"""In-memory job tracker for strata analysis.

Lightweight tracking for standard/deep tier analysis which runs in background.
Quick tier is synchronous and doesn't need job tracking.

Pattern mirrors scue/api/jobs.py but tailored for strata's stage-based progress.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class StrataJob:
    """Tracks progress of a single-track strata analysis."""
    job_id: str
    fingerprint: str
    tier: str
    status: str = "pending"  # pending | running | complete | failed
    current_step: int = 0
    current_step_name: str = ""
    total_steps: int = 5
    error: str | None = None
    cancelled: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class StrataBatchJob:
    """Tracks progress of a multi-track strata batch analysis."""
    batch_id: str
    jobs: list[StrataJob] = field(default_factory=list)
    status: str = "pending"  # pending | running | complete | failed
    created_at: float = field(default_factory=time.time)

    @property
    def completed(self) -> int:
        return sum(1 for j in self.jobs if j.status == "complete")

    @property
    def failed(self) -> int:
        return sum(1 for j in self.jobs if j.status == "failed")

    @property
    def total(self) -> int:
        return len(self.jobs)


_jobs: dict[str, StrataJob] = {}
_batches: dict[str, StrataBatchJob] = {}


def create_strata_job(fingerprint: str, tier: str) -> StrataJob:
    """Create a new strata analysis job."""
    job_id = uuid.uuid4().hex[:12]
    job = StrataJob(job_id=job_id, fingerprint=fingerprint, tier=tier)
    _jobs[job_id] = job
    return job


def get_strata_job(job_id: str) -> StrataJob | None:
    return _jobs.get(job_id)


def create_strata_batch(
    fingerprints: list[str], tiers: list[str],
) -> StrataBatchJob:
    """Create a batch job with one StrataJob per (fingerprint, tier) pair."""
    batch_id = uuid.uuid4().hex[:12]
    jobs: list[StrataJob] = []
    for fp in fingerprints:
        for tier in tiers:
            job = create_strata_job(fp, tier)
            jobs.append(job)
    batch = StrataBatchJob(batch_id=batch_id, jobs=jobs)
    _batches[batch_id] = batch
    return batch


def get_strata_batch(batch_id: str) -> StrataBatchJob | None:
    return _batches.get(batch_id)


def strata_job_to_dict(job: StrataJob) -> dict:
    return {
        "job_id": job.job_id,
        "fingerprint": job.fingerprint,
        "tier": job.tier,
        "status": job.status,
        "current_step": job.current_step,
        "current_step_name": job.current_step_name,
        "total_steps": job.total_steps,
        "error": job.error,
    }


def strata_batch_to_dict(batch: StrataBatchJob) -> dict:
    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "jobs": [strata_job_to_dict(j) for j in batch.jobs],
        "completed": batch.completed,
        "failed": batch.failed,
        "total": batch.total,
    }
