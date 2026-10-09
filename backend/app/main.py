"""FastAPI app: projects, streamed uploads, jobs (SSE progress), clip editing, export."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .jobs import JobManager
from .models import (ClipPatch, ExportRequest, ImportRequest, KeyRequest, ModelRequest, ProcessRequest, Project,
                     ProjectCreate, ProcessingSettings, RomanizeRequest, SourceFile)
from .pipeline import export, romanize, transcribe
from .pipeline.audio_io import ffmpeg_exe
from .pipeline.text_ur import assess_transcript, clean_roman, normalize_urdu
from .store import ProjectStore

app = FastAPI(title="Talaffuz.ai")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store = ProjectStore(config.PROJECTS_DIR)
jobs = JobManager(store)


def _project(pid: str) -> Project:
    try:
        return store.get(pid)
    except KeyError:
        raise HTTPException(404, "Project not found")


def _public(project: Project) -> dict:
    data = project.model_dump()
    data["running"] = jobs.running(project.id)
    data["exported"] = (store.project_dir(project.id) / "output" / "dataset.zip").exists()
    return data


# ---- health -------------------------------------------------------------
@app.get("/api/health")
def health():
    try:
        ffmpeg = bool(ffmpeg_exe())
    except Exception:
        ffmpeg = False
    return {"ok": True, "ffmpeg": ffmpeg, "romanize_available": romanize.is_available(),
            "romanize_model": config.ROMANIZE_MODEL, **transcribe.device_info()}


# ---- Anthropic API key (optional: Roman Urdu can also come from Claude Code or be typed) ------
@app.get("/api/anthropic-key")
def get_key_status():
    return config.key_status()


@app.put("/api/anthropic-key")
async def put_key(body: KeyRequest):
    key = body.key.strip()
    if not config.KEY_PATTERN.fullmatch(key):
        raise HTTPException(400, "That does not look like an Anthropic API key. It starts with sk-ant- and has no spaces.")
    verdict = await run_in_threadpool(romanize.verify_key, key)
    if verdict is False:
        raise HTTPException(400, "Anthropic rejected that key. Check that you copied all of it.")
    config.save_api_key(key, body.remember)
    return {**config.key_status(), "verified": verdict is True}


@app.delete("/api/anthropic-key")
def delete_key():
    config.clear_api_key()
    return config.key_status()


@app.get("/api/anthropic-models")
async def get_models():
    return await run_in_threadpool(romanize.list_models)


@app.put("/api/anthropic-model")
def put_model(body: ModelRequest):
    model = body.model.strip()
    if not romanize.MODEL_PATTERN.fullmatch(model):
        raise HTTPException(400, "Choose one of the listed models.")
    config.set_romanize_model(model, body.remember)
    return config.key_status()


# ---- projects -----------------------------------------------------------
@app.get("/api/projects")
def list_projects():
    return [{"id": p.id, "name": p.name, "created_at": p.created_at, "clips": len(p.clips),
             "sources": len(p.sources)} for p in store.list()]


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    return _public(store.create(body.name, body.settings))


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _public(_project(pid))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    if jobs.running(pid):
        raise HTTPException(409, "A job is running; stop it first.")
    store.delete(pid)
    return {"deleted": pid}


@app.put("/api/projects/{pid}/settings")
def put_settings(pid: str, settings: ProcessingSettings):
    _project(pid)
    if jobs.running(pid):
        raise HTTPException(409, "Settings are locked while a job is running.")
    with store.edit(pid) as live:
        live.settings = settings
    return _public(store.get(pid))


@app.post("/api/projects/{pid}/resegment")
def resegment(pid: str):
    """Throw away all clips and re-run speech detection (use after changing segmentation settings)."""
    _project(pid)
    if jobs.running(pid):
        raise HTTPException(409, "A job is running; stop it first.")
    with store.edit(pid) as live:
        live.clips = []
        for src in live.sources:
            src.status, src.error = "uploaded", None
    for f in (store.project_dir(pid) / "clips").glob("*.wav"):
        f.unlink(missing_ok=True)
    return _public(store.get(pid))


# ---- uploads (raw body, streamed to disk: no multipart, no RAM spike) -----
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".mp4", ".mkv", ".webm", ".mov"}


def _safe_filename(filename: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", Path(filename).name)[:120] or "audio"


@app.post("/api/projects/{pid}/sources/import")
async def import_sources(pid: str, body: ImportRequest):
    """Copy audio that is already on this machine (a file, or the audio files in a folder) into the project.

    Meant for Google Drive in Colab and for multi-GB files you would rather not push through the browser.
    The app is single-user and listens on localhost, so any readable path is allowed, but only audio/video
    extensions are copied.
    """
    _project(pid)
    target = Path(body.path.strip().strip('"').strip("'")).expanduser()
    if not target.exists():
        raise HTTPException(404, f"Path not found: {target}")
    if target.is_dir():
        files = sorted(p for p in target.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)
        if not files:
            raise HTTPException(400, "No audio files found in that folder.")
    elif target.suffix.lower() in AUDIO_EXTENSIONS:
        files = [target]
    else:
        raise HTTPException(400, f"Not an audio or video file: {target.name}")
    too_big = next((f for f in files if f.stat().st_size > config.MAX_UPLOAD_BYTES), None)
    if too_big:
        raise HTTPException(413, f"{too_big.name} is larger than {config.MAX_UPLOAD_BYTES / 1024**3:.0f} GB.")

    added: list[SourceFile] = []
    for src in files:
        safe, sid = _safe_filename(src.name), uuid.uuid4().hex[:8]
        rel = f"uploads/{sid}_{safe}"
        dest = store.project_dir(pid) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            await run_in_threadpool(shutil.copyfile, src, dest)
        except OSError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, f"Could not read {src.name}: {exc}")
        added.append(SourceFile(id=sid, name=safe, path=rel, size_bytes=dest.stat().st_size))
    with store.edit(pid) as live:
        live.sources.extend(added)
    return added


@app.put("/api/projects/{pid}/sources")
async def upload_source(pid: str, request: Request, filename: str):
    _project(pid)
    declared = request.headers.get("content-length")
    if declared and int(declared) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_BYTES / 1024**3:.0f} GB.")
    safe = _safe_filename(filename)
    sid = uuid.uuid4().hex[:8]
    rel = f"uploads/{sid}_{safe}"
    dest = store.project_dir(pid) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    size, buffer = 0, bytearray()
    try:
        with open(dest, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File is too large.")
                buffer += chunk
                if len(buffer) >= 4 * 1024 * 1024:
                    await run_in_threadpool(f.write, bytes(buffer))
                    buffer.clear()
            if buffer:
                await run_in_threadpool(f.write, bytes(buffer))
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Empty upload.")
    source = SourceFile(id=sid, name=safe, path=rel, size_bytes=size)
    with store.edit(pid) as live:
        live.sources.append(source)
    return source


@app.delete("/api/projects/{pid}/sources/{sid}")
def delete_source(pid: str, sid: str):
    _project(pid)
    if jobs.running(pid):
        raise HTTPException(409, "A job is running; stop it first.")
    pdir = store.project_dir(pid)
    with store.edit(pid) as live:
        src = next((s for s in live.sources if s.id == sid), None)
        if not src:
            raise HTTPException(404, "Source not found")
        for c in live.clips:
            if c.source_id == sid and c.wav:
                (pdir / c.wav).unlink(missing_ok=True)
        live.clips = [c for c in live.clips if c.source_id != sid]
        live.sources = [s for s in live.sources if s.id != sid]
    (pdir / src.path).unlink(missing_ok=True)
    (pdir / "work" / f"{sid}.wav").unlink(missing_ok=True)
    return _public(store.get(pid))


# ---- jobs ---------------------------------------------------------------
@app.post("/api/projects/{pid}/process")
def start_process(pid: str, body: ProcessRequest | None = None):
    project = _project(pid)
    if not project.sources:
        raise HTTPException(400, "Upload at least one audio file first.")
    if not jobs.start(pid, "process", extra=(body.extra if body else 0)):
        raise HTTPException(409, "A job is already running for this project.")
    return {"started": True}


@app.post("/api/projects/{pid}/romanize")
def start_romanize(pid: str, body: RomanizeRequest | None = None):
    _project(pid)
    if not romanize.is_available():
        raise HTTPException(400, "No Anthropic API key is configured. Use /romanize in Claude Code or $romanize in Codex instead.")
    if not jobs.start(pid, "romanize", only_missing=(body.only_missing if body else True)):
        raise HTTPException(409, "A job is already running for this project.")
    return {"started": True}


@app.get("/api/projects/{pid}/romanize-estimate")
def romanize_estimate(pid: str):
    """Rough token and cost estimate for the clips that still need Roman Urdu, using the selected model."""
    project = _project(pid)
    items = {c.id: c.urdu for c in project.clips
             if c.keep and c.status == "processed" and c.urdu.strip() and not c.roman.strip()}
    return romanize.estimate(items)


@app.post("/api/projects/{pid}/cancel")
def cancel_job(pid: str):
    _project(pid)
    return {"cancelled": jobs.cancel(pid)}


@app.get("/api/projects/{pid}/events")
async def events(pid: str, request: Request):
    _project(pid)
    # A fresh connection only gets new events; EventSource resends Last-Event-ID itself on reconnect.
    header = request.headers.get("last-event-id")
    last = int(header) if header and header.isdigit() else jobs.latest_seq(pid)

    async def stream():
        nonlocal last
        idle = 0
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            fresh = jobs.events_after(pid, last)
            for ev in fresh:
                last = ev["seq"]
                yield f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            idle = 0 if fresh else idle + 1
            if idle >= 30:  # keep proxies from closing a quiet connection
                yield ": keep-alive\n\n"
                idle = 0
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- clips --------------------------------------------------------------
def _apply_patch(c, patch: ClipPatch) -> None:
    if patch.urdu is not None:
        c.urdu, c.edited = normalize_urdu(patch.urdu, ensure_terminal=False), True
        # The ASR warnings described the old text; recompute them for the edited text.
        kept_flags = [f for f in c.flags if f in ("noisy", "clipping")]
        c.flags = kept_flags + assess_transcript(c.urdu, c.duration_s, None, None)[0]
    if patch.roman is not None:
        c.roman = clean_roman(patch.roman)
    if patch.keep is not None:
        c.keep = patch.keep


@app.patch("/api/projects/{pid}/clips/{cid}")
def patch_clip(pid: str, cid: str, patch: ClipPatch):
    _project(pid)
    with store.edit(pid) as live:
        clip = next((c for c in live.clips if c.id == cid), None)
        if not clip:
            raise HTTPException(404, "Clip not found")
        _apply_patch(clip, patch)
        return clip.model_copy(deep=True)


@app.post("/api/projects/{pid}/clips/bulk")
def bulk_patch(pid: str, patches: list[ClipPatch], fill_only: bool = False):
    """fill_only: never overwrite a Roman Urdu value that is already there (used by /romanize)."""
    _project(pid)
    changed = 0
    with store.edit(pid) as live:
        by_id = {c.id: c for c in live.clips}
        for patch in patches:
            clip = by_id.get(patch.id or "")
            if clip is None or (fill_only and clip.roman.strip()):
                continue
            _apply_patch(clip, patch)
            changed += 1
    return {"changed": changed}


@app.get("/api/projects/{pid}/clips/{cid}/audio")
def clip_audio(pid: str, cid: str):
    clip = next((c for c in _project(pid).clips if c.id == cid), None)
    if not clip or not clip.wav:
        raise HTTPException(404, "No audio for this clip")
    path = store.project_dir(pid) / clip.wav
    if not path.exists():
        raise HTTPException(404, "Audio file missing")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})


# ---- export -------------------------------------------------------------
@app.post("/api/projects/{pid}/export")
async def export_dataset(pid: str, body: ExportRequest | None = None):
    project = _project(pid)
    if jobs.running(pid):
        raise HTTPException(409, "Wait for the running job to finish before exporting.")
    report = await run_in_threadpool(
        export.build_dataset, project, store.project_dir(pid), bool(body and body.force))
    with store.edit(pid) as live:
        live.last_export = report
    return report


@app.get("/api/projects/{pid}/download/{kind}")
def download(pid: str, kind: str):
    _project(pid)
    out = store.project_dir(pid) / "output"
    files = {"zip": (out / "dataset.zip", "application/zip", "dataset.zip"),
             "csv": (out / "dataset" / "metadata.csv", "text/csv; charset=utf-8", "metadata.csv"),
             "xlsx": (out / "metadata.xlsx",
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "metadata.xlsx")}
    if kind not in files or not files[kind][0].exists():
        raise HTTPException(404, "Nothing exported yet.")
    path, media, name = files[kind]
    return FileResponse(path, media_type=media, filename=name)


# ---- built frontend (after `npm run build`) --------------------------------
if config.FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
