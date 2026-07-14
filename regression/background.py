"""
Background-thread trigger for the compliance loop, started from the staff
dashboard's "Run" buttons. Same pattern already used in this codebase for
opportunity/ai_search.py: a lock-guarded singleton thread, DB row created
before the thread starts (so the page has something to poll immediately),
transaction.on_commit so the thread never reads a row that isn't committed
yet, and close_old_connections() around the worker since a new thread needs
its own DB connection.
"""

from __future__ import annotations

import threading

from django.db import close_old_connections, transaction
from django.utils import timezone

from . import compliance_runner
from .models import SFRComplianceLoopRun

# A stale "running" row (e.g. the process was killed mid-run by a deploy)
# would otherwise block new runs forever -- treat anything older than this
# as abandoned and let a new run start.
STALE_RUN_MINUTES = 30

_RUN_LOCK = threading.Lock()
_RUN_IN_PROGRESS = False


def is_run_in_progress() -> SFRComplianceLoopRun | None:
    """Returns the currently-running SFRComplianceLoopRun row, if any (and not stale)."""
    running = SFRComplianceLoopRun.objects.filter(status=SFRComplianceLoopRun.STATUS_RUNNING).order_by("-started_at").first()
    if running is None:
        return None
    age_minutes = (timezone.now() - running.started_at).total_seconds() / 60
    if age_minutes > STALE_RUN_MINUTES:
        running.status = SFRComplianceLoopRun.STATUS_FAILED
        running.finished_at = timezone.now()
        running.error = f"Marked failed automatically -- no update for over {STALE_RUN_MINUTES} minutes (likely killed by a deploy)."
        running.save()
        return None
    return running


def start_compliance_loop_run(segment_scope: str | None = None) -> SFRComplianceLoopRun | None:
    """
    Creates a SFRComplianceLoopRun row (status=running) and starts the loop
    in a background thread. Returns None (starts nothing) if a run is
    already in progress -- the caller should check is_run_in_progress()
    first and show that instead of calling this again.
    """
    if is_run_in_progress() is not None:
        return None

    with _RUN_LOCK:
        global _RUN_IN_PROGRESS
        if _RUN_IN_PROGRESS:
            return None
        _RUN_IN_PROGRESS = True

    run = SFRComplianceLoopRun.objects.create(
        started_at=timezone.now(),
        status=SFRComplianceLoopRun.STATUS_RUNNING,
        segment_scope=segment_scope or "",
    )
    transaction.on_commit(lambda: _start_worker_thread(run.pk, segment_scope))
    return run


def _start_worker_thread(run_id: int, segment_scope: str | None) -> None:
    worker = threading.Thread(target=_run_worker, args=(run_id, segment_scope), daemon=True)
    worker.start()


def _run_worker(run_id: int, segment_scope: str | None) -> None:
    close_old_connections()
    try:
        run = SFRComplianceLoopRun.objects.get(pk=run_id)
        compliance_runner.run_compliance_loop(run, segment_scope=segment_scope)
    except Exception:
        # run_compliance_loop already records the failure onto the row
        # itself (status/error/finished_at) before re-raising -- nothing
        # further to persist here, just don't let the thread crash loudly.
        pass
    finally:
        close_old_connections()
        with _RUN_LOCK:
            global _RUN_IN_PROGRESS
            _RUN_IN_PROGRESS = False
