"""In-memory job tracker for batch analysis.

Jobs are not persisted — if the server restarts, in-flight jobs are lost.
This is acceptable for a local single-user tool.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class FileResult:
    """Result of analyzing a single file within a batch job."""
    path: str
    filename: str
    fingerprint: str = ""
    status: str = "pending"  # pending | done | error
    error: str | None = None


@dataclass
class AnalysisJob:
    """Tracks progress of a batch analysis operation."""
    job_id: str
    status: str = "pending"  # pending | running | complete | failed
    total: int = 0
    completed: int = 0
    failed: int = 0
    current_file: str | None = None
    current_step: int = 0           # current analysis step within current file
    current_step_name: str = ""     # human-readable step name
    total_steps: int = 10           # total steps per file
    results: list[FileResult] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


_jobs: dict[str, AnalysisJob] = {}


def create_job(paths: list[str]) -> AnalysisJob:
    """Create a new analysis job for the given file paths."""
    job_id = uuid.uuid4().hex[:12]
    results = [
        FileResult(path=p, filename=p.rsplit("/", 1)[-1])
        for p in paths
    ]
    job = AnalysisJob(
        job_id=job_id,
        total=len(paths),
        results=results,
    )
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> AnalysisJob | None:
    """Get a job by ID, or None if not found."""
    return _jobs.get(job_id)


def job_to_dict(job: AnalysisJob) -> dict:
    """Serialize a job to a JSON-safe dict."""
    return {
        "job_id": job.job_id,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "failed": job.failed,
        "current_file": job.current_file,
        "current_step": job.current_step,
        "current_step_name": job.current_step_name,
        "total_steps": job.total_steps,
        "results": [
            {
                "path": r.path,
                "filename": r.filename,
                "fingerprint": r.fingerprint,
                "status": r.status,
                "error": r.error,
            }
            for r in job.results
        ],
    }
