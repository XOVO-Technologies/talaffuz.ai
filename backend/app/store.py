"""JSON-file backed project store (single user, single process)."""
from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import Project, ProcessingSettings


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._projects: dict[str, Project] = {}
        self._load_all()

    # ---- paths -------------------------------------------------------
    def project_dir(self, pid: str) -> Path:
        return self.root / pid

    # ---- persistence -------------------------------------------------
    def _load_all(self) -> None:
        for pj in self.root.glob("*/project.json"):
            try:
                project = Project.model_validate_json(pj.read_text(encoding="utf-8"))
            except Exception:
                continue  # skip corrupt project files rather than failing startup
            for src in project.sources:
                if src.status == "analyzing":  # server stopped mid-analysis
                    src.status = "uploaded"
            if self._reset_legacy_numbering(project):
                self._write(project)
            self._projects[project.id] = project

    @staticmethod
    def _reset_legacy_numbering(project: Project) -> bool:
        """Early builds defaulted every project to files 31 to 500. Move projects that still carry exactly that
        range, and have not been exported yet, to the generic defaults (numbering from 1, no upper limit)."""
        s = project.settings
        if (s.start_index, s.end_index) == (31, 500) and project.last_export is None:
            s.start_index, s.end_index = 1, None
            return True
        return False

    def _write(self, project: Project) -> None:
        pdir = self.project_dir(project.id)
        pdir.mkdir(parents=True, exist_ok=True)
        tmp = pdir / "project.json.tmp"
        tmp.write_text(project.model_dump_json(indent=1), encoding="utf-8")
        os.replace(tmp, pdir / "project.json")

    # ---- CRUD --------------------------------------------------------
    def create(self, name: str, settings: ProcessingSettings | None) -> Project:
        with self._lock:
            project = Project(
                id=uuid.uuid4().hex[:10],
                name=name.strip() or "Urdu dataset",
                created_at=time.time(),
                settings=settings or ProcessingSettings(),
            )
            self._projects[project.id] = project
            self._write(project)
            return project.model_copy(deep=True)

    def get(self, pid: str) -> Project:
        """Return a snapshot (safe to read while a job thread mutates the live object)."""
        with self._lock:
            return self._projects[pid].model_copy(deep=True)

    def list(self) -> list[Project]:
        with self._lock:
            projects = sorted(self._projects.values(), key=lambda p: p.created_at, reverse=True)
            return [p.model_copy(deep=True) for p in projects]

    def delete(self, pid: str) -> None:
        with self._lock:
            self._projects.pop(pid, None)
            shutil.rmtree(self.project_dir(pid), ignore_errors=True)

    @contextmanager
    def edit(self, pid: str) -> Iterator[Project]:
        """Mutate the live project under the lock; it is saved when the block exits."""
        with self._lock:
            project = self._projects[pid]
            yield project
            self._write(project)

