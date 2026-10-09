"""Single-worker background job runner with a per-project event log for SSE."""
from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .pipeline import process
from .store import ProjectStore

log = logging.getLogger("jobs")


class JobManager:
    def __init__(self, store: ProjectStore):
        self.store = store
        # One worker: the pipeline is CPU/RAM heavy and two parallel jobs would just fight over cores.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job")
        self._lock = threading.Lock()
        self._active: dict[str, tuple[str, threading.Event]] = {}
        self._events: dict[str, deque] = {}
        self._seq: dict[str, int] = {}

    # ---- events ------------------------------------------------------
    def emit(self, pid: str, stage: str, message: str | None = None, progress: float | None = None, **extra) -> None:
        with self._lock:
            seq = self._seq.get(pid, 0) + 1
            self._seq[pid] = seq
            event = {"seq": seq, "stage": stage, "message": message, "progress": progress, **extra}
            self._events.setdefault(pid, deque(maxlen=2000)).append(event)

    def latest_seq(self, pid: str) -> int:
        with self._lock:
            return self._seq.get(pid, 0)

    def events_after(self, pid: str, last_seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self._events.get(pid, ()) if e["seq"] > last_seq]

    # ---- control -----------------------------------------------------
    def running(self, pid: str) -> str | None:
        with self._lock:
            return self._active[pid][0] if pid in self._active else None

    def start(self, pid: str, kind: str, **kwargs) -> bool:
        with self._lock:
            if pid in self._active:
                return False
            cancel = threading.Event()
            self._active[pid] = (kind, cancel)
        self.emit(pid, "started", f"{kind} queued", kind=kind)
        self._pool.submit(self._run, pid, kind, kwargs, cancel)
        return True

    def cancel(self, pid: str) -> bool:
        with self._lock:
            job = self._active.get(pid)
        if job:
            job[1].set()
        return bool(job)

    def _run(self, pid: str, kind: str, kwargs: dict, cancel: threading.Event) -> None:
        def emit(stage, message=None, progress=None, **extra):
            self.emit(pid, stage, message, progress, **extra)

        try:
            if kind == "process":
                process.run_process(self.store, pid, emit, cancel, **kwargs)
            elif kind == "romanize":
                process.run_romanize(self.store, pid, emit, cancel, **kwargs)
        except InterruptedError:
            emit("cancelled", "Stopped. Work done so far is kept.")
        except Exception as exc:  # surface the reason in the UI instead of dying silently
            log.exception("job failed")
            emit("error", str(exc))
        finally:
            with self._lock:
                self._active.pop(pid, None)
