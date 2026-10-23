from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .models import Profile
from .service import AssignmentService
from .source import SourceError

KEY = "assignment"


class EditRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    sentence: int | None = Field(None, ge=0, le=500)
    urdu: str = Field(max_length=20000)
    roman: str = Field(max_length=20000)


class TimingRequest(BaseModel):
    redo: bool = False


def make_router(service: AssignmentService, jobs, event_stream: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/assignment")

    def snapshot() -> dict:
        return service.state(jobs.running(KEY))

    def start(kind: str, **kwargs) -> dict:
        if not jobs.start(KEY, kind, **kwargs):
            raise HTTPException(409, "Another Assignment 2 job is already running.")
        return {"started": True}

    @router.get("/state")
    async def get_state():
        return await run_in_threadpool(snapshot)

    @router.put("/profile")
    async def put_profile(profile: Profile):
        if jobs.running(KEY):
            raise HTTPException(409, "Your details are locked while a job is running.")
        await run_in_threadpool(service.save_profile, profile)
        return await run_in_threadpool(snapshot)

    @router.post("/scan")
    async def scan():
        if jobs.running(KEY):
            raise HTTPException(409, "Wait for the running job to finish.")
        try:
            await run_in_threadpool(service.rescan)
        except SourceError:
            pass
        return await run_in_threadpool(snapshot)

    @router.get("/problems")
    async def problems(kind: str = "bad", offset: int = 0, limit: int = 10):
        if kind not in ("bad", "check"):
            raise HTTPException(400, "kind must be bad or check")
        try:
            return await run_in_threadpool(service.problems, kind, max(0, offset), max(1, min(limit, 50)))
        except SourceError as exc:
            raise HTTPException(400, str(exc))

    @router.put("/edit")
    async def edit(body: EditRequest):
        if jobs.running(KEY):
            raise HTTPException(409, "Wait for the running job to finish.")
        try:
            return await run_in_threadpool(service.edit, body.key, body.sentence, body.urdu, body.roman)
        except KeyError:
            raise HTTPException(404, "That recording is not part of the dataset.")
        except SourceError as exc:
            raise HTTPException(400, str(exc))

    @router.post("/timing")
    def timing(body: TimingRequest | None = None):
        return start("assignment_timing", redo=bool(body and body.redo))

    @router.post("/build")
    def build():
        return start("assignment_build")

    @router.post("/check")
    def check():
        return start("assignment_check")

    @router.post("/cancel")
    def cancel():
        return {"cancelled": jobs.cancel(KEY)}

    @router.get("/events")
    async def events(request: Request):
        return event_stream(KEY, request)

    @router.get("/download")
    def download():
        profile = service.profile()
        if profile.roll_no is None:
            raise HTTPException(404, "Nothing built yet.")
        path = service.output_dir / f"{profile.sid}.zip"
        if not path.is_file():
            raise HTTPException(404, "Nothing built yet.")
        return FileResponse(path, media_type="application/zip", filename=path.name)

    return router
