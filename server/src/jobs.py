"""Background analysis jobs, so a slow model run never holds an HTTP request open.

POST /api/analyses validates the upload, queues the run here and answers 202 at once; the dashboard then polls
GET /api/analyses/jobs/{job_id}. Proxies (nginx default 60 s) can no longer time a long analysis out.
Jobs are kept in memory (they are short-lived); the finished run itself is saved in the run store.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import engine
from .models import AnalysisJob, AnalysisRecord

log = logging.getLogger("uvicorn.error")
ISO = "%Y-%m-%dT%H:%M:%SZ"


def _now() -> str:
    return datetime.now(timezone.utc).strftime(ISO)


class JobRunner:
    """Runs analyses one at a time (CPU / memory heavy) on a single worker thread."""

    def __init__(self, keep: int = 50) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
        self._jobs: OrderedDict[str, AnalysisJob] = OrderedDict()
        self._lock = threading.Lock()
        self._keep = keep

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            self._jobs[job_id] = self._jobs[job_id].model_copy(update=changes)

    def submit(self, label: str | None, work: Callable[[], AnalysisRecord]) -> AnalysisJob:
        job = AnalysisJob(job_id=uuid.uuid4().hex, status="queued", created_utc=_now(), label=label)
        with self._lock:
            self._jobs[job.job_id] = job
            while len(self._jobs) > self._keep:            # forget the oldest finished jobs
                oldest = next(iter(self._jobs))
                if self._jobs[oldest].status in ("queued", "running"):
                    break
                self._jobs.popitem(last=False)
        self._executor.submit(self._run, job.job_id, work)
        return job

    def _run(self, job_id: str, work: Callable[[], AnalysisRecord]) -> None:
        self._update(job_id, status="running", started_utc=_now())
        try:
            record = work()
        except engine.EngineUnavailableError as exc:
            self._fail(job_id, 503, f"model engine unavailable: {exc}")
        except ValueError as exc:                          # bad input: tell the user what is wrong
            self._fail(job_id, 422, str(exc))
        except KeyError as exc:
            self._fail(job_id, 422, f"the uploaded data is missing a column the model needs: {exc}")
        except Exception as exc:  # noqa: BLE001 - a crashed job must report, not vanish
            log.exception("Analysis job %s failed", job_id)
            self._fail(job_id, 500, f"analysis failed: {type(exc).__name__}: {exc}")
        else:
            s = record.summary
            self._update(job_id, status="completed", finished_utc=_now(), run=s)
            log.info("Analysis %s: %d pumps, %d alerts in %.1fs", s.run_id, s.pumps, s.alerts, s.processing_seconds)

    def _fail(self, job_id: str, code: int, message: str) -> None:
        self._update(job_id, status="failed", finished_utc=_now(), error=message, error_status=code)

    def get(self, job_id: str) -> AnalysisJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
