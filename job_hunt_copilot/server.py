"""FastAPI server for Job Hunt Copilot. Binds to 127.0.0.1 only."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__, ai
from .analysis import interview_questions, match_resume
from .config import SettingsError, data_dir, load_settings, update_settings, validate_changes
from .extract import SUPPORTED_EXTS, extract_text
from .llm import detect_ollama, get_provider

log = logging.getLogger("job_hunt_copilot")
ROOT = Path(__file__).parent
STATIC = ROOT / "static"
SAMPLES = ROOT.parent / "samples"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_TEXT = 40_000

app = FastAPI(title="Job Hunt Copilot", version=__version__, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def block_cross_site_writes(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin", "")
        sfs = request.headers.get("sec-fetch-site", "")
        host = (urlparse(origin).hostname or "") if origin else ""
        if (origin and host not in ("127.0.0.1", "localhost", "::1")) or (sfs and sfs not in ("same-origin", "none")):
            return JSONResponse(status_code=403, content={"detail": "Blocked a request from another website."})
    return await call_next(request)


def _provider_status(s, live: bool = True) -> dict:
    """live=False answers from saved settings alone (no network, no key sent anywhere)."""
    try:
        provider = get_provider(s)
    except Exception as exc:  # noqa: BLE001 - e.g. an unparsable saved URL must never take the UI down
        log.warning("provider init failed: %s", exc)
        return {"name": s.provider, "model": s.effective_model(), "local": True, "ok": False, "message": "The saved AI settings are invalid. Open Settings and fix the address, or pick No AI."}
    if not live and provider.name in ("openai", "gemini"):
        has_key = bool(s.openai_api_key if provider.name == "openai" else s.gemini_api_key) or provider.local
        return {"name": provider.name, "model": provider.model, "local": provider.local, "ok": has_key, "message": "Key saved. Click Test in Settings to verify it." if has_key else "No API key saved. Paste your key in Settings."}
    try:
        ok, message = provider.check()
    except Exception as exc:  # noqa: BLE001
        log.warning("provider check failed: %s", exc)
        ok, message = False, "Could not check the AI option. Open Settings and click Test."
    return {"name": provider.name, "model": provider.model, "local": provider.local, "ok": ok, "message": message}


# ---------------------------------------------------------------------------
# Local "applications" store: one JSON file per application in ~/.job_hunt_copilot/apps/
# ---------------------------------------------------------------------------
def _apps_dir() -> Path:
    d = data_dir() / "apps"
    d.mkdir(exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


_LOCK = threading.Lock()          # load -> mutate -> save must not interleave
_MEM: dict[str, dict] = {}        # applications kept only in memory when "save history" is off
_ID = re.compile(r"^[0-9a-f]{12}$")


def _valid_id(app_id: str) -> bool:
    return bool(_ID.fullmatch(app_id or ""))


def _save_app(doc: dict) -> None:
    if not load_settings().save_history:
        _MEM[doc["id"]] = doc
        return
    p = _apps_dir() / f"{doc['id']}.json"
    tmp = p.with_suffix(".json.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.replace(tmp, p)  # atomic


def _load_app(app_id: str) -> dict | None:
    if not _valid_id(app_id):
        return None
    if app_id in _MEM:
        return _MEM[app_id]
    p = _apps_dir() / f"{app_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _list_apps() -> list[dict]:
    out = [{"id": d["id"], "title": d.get("title") or "Untitled job", "company": d.get("company", ""), "score": d.get("match", {}).get("score", 0), "updated": d.get("updated", 0), "status": d.get("status", "draft"), "unsaved": True} for d in _MEM.values()]
    for p in _apps_dir().glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": d["id"], "title": d.get("title") or "Untitled job", "company": d.get("company", ""), "score": d.get("match", {}).get("score", 0), "updated": d.get("updated", 0), "status": d.get("status", "draft")})
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return sorted(out, key=lambda a: -a["updated"])


# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/status")
def status(probe: int = 0):
    s = load_settings()
    ollama = detect_ollama(s.ollama_host) if (s.provider == "ollama" or probe) else {"running": False, "models": [], "skipped": True}
    if s.provider == "ollama":
        provider = get_provider(s)
        if ollama.get("error"):
            pstat = {"ok": False, "message": ollama["error"]}
        elif not ollama["running"]:
            pstat = {"ok": False, "message": "Ollama isn't running (or isn't installed). See Settings for the install steps, or start it with: ollama serve"}
        elif not ollama["models"]:
            pstat = {"ok": False, "message": f"Ollama is running but has no models. Run: ollama pull {provider.model}"}
        elif not any(m == provider.model or m.split(":")[0] == provider.model.split(":")[0] for m in ollama["models"]):
            pstat = {"ok": False, "message": f"Model '{provider.model}' is not downloaded. Run: ollama pull {provider.model}"}
        else:
            pstat = {"ok": True, "message": f"Ollama is ready with {provider.model}"}
        pstat.update({"name": provider.name, "model": provider.model, "local": True})
    else:
        pstat = _provider_status(s, live=bool(probe))
    return {
        "settings": s.public_dict(), "provider": pstat, "ollama": ollama, "supported_files": sorted(SUPPORTED_EXTS),
        "apps": _list_apps(), "data_dir": str(data_dir()),
        "env_overrides": sorted(k for k in ("JOBHUNT_PROVIDER", "JOBHUNT_MODEL", "OLLAMA_HOST", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENAI_BASE_URL") if os.environ.get(k)),
        "saved_resume": (data_dir() / "resume.txt").exists(),
    }


class SettingsIn(BaseModel):
    provider: str | None = None
    model: str | None = None
    ollama_host: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    gemini_api_key: str | None = None
    save_history: bool | None = None
    setup_complete: bool | None = None


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        s = update_settings(changes)
    except SettingsError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"settings": s.public_dict(), "provider": _provider_status(s)}


@app.post("/api/test-connection")
def test_connection(body: SettingsIn):
    s = load_settings()
    try:
        changes = validate_changes({k: v for k, v in body.model_dump().items() if v is not None})
    except SettingsError as exc:
        return {"ok": False, "message": str(exc), "model": ""}
    for k, v in changes.items():
        if hasattr(s, k):
            if k in ("openai_api_key", "gemini_api_key") and "*" in str(v):
                continue
            setattr(s, k, v)
    st = _provider_status(s)
    return {"ok": st["ok"], "message": st["message"], "model": st["model"]}


# ---------------------------------------------------------------------------
# Resume: upload a file -> text; remember it locally so it's pre-filled next time
# ---------------------------------------------------------------------------
@app.post("/api/resume/file")
async def resume_file(file: UploadFile = File(...)):
    chunks, size = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "That file is bigger than 15 MB. A resume should be a small PDF or Word file.")
        chunks.append(chunk)
    data = b"".join(chunks)
    ext = await asyncio.to_thread(extract_text, file.filename or "resume", data)
    if not ext.ok:
        raise HTTPException(400, ext.error or "The file had no readable text.")
    return {"text": ext.text[:MAX_TEXT], "warnings": ext.warnings, "filename": file.filename}


class ResumeIn(BaseModel):
    text: str


@app.post("/api/resume/save")
def resume_save(body: ResumeIn):
    p = data_dir() / "resume.txt"
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body.text[:MAX_TEXT])
    return {"saved": True}


@app.get("/api/resume")
def resume_get():
    p = data_dir() / "resume.txt"
    return {"text": p.read_text(encoding="utf-8") if p.exists() else ""}


@app.get("/api/sample")
def sample():
    return {"resume": (SAMPLES / "resume.txt").read_text(encoding="utf-8"), "posting": (SAMPLES / "job_posting.txt").read_text(encoding="utf-8")}


# ---------------------------------------------------------------------------
# Match (instant, no AI)
# ---------------------------------------------------------------------------
class MatchIn(BaseModel):
    resume: str
    posting: str
    company: str = ""
    app_id: str = ""


def _match(body: MatchIn) -> dict:
    resume, posting = body.resume.strip()[:MAX_TEXT], body.posting.strip()[:MAX_TEXT]
    if len(resume) < 100:
        raise HTTPException(400, "Paste your whole resume first (it looks too short).")
    if len(posting) < 80:
        raise HTTPException(400, "Paste the full job posting — the description and requirements, not just the title.")
    match = match_resume(resume, posting)
    questions = interview_questions(posting, match)
    doc = _load_app(body.app_id) if body.app_id else None
    if not doc:
        doc = {"id": uuid.uuid4().hex[:12], "created": time.time(), "status": "draft", "answers": []}
    doc.update({"updated": time.time(), "title": match["title"] or "Untitled job", "company": body.company.strip()[:120], "resume": resume, "posting": posting, "match": match, "questions": questions})
    with _LOCK:
        _save_app(doc)  # goes to memory only when "save history" is off
    return {"id": doc["id"], "match": match, "questions": questions, "title": doc["title"], "company": doc["company"]}


@app.post("/api/match")
async def match(body: MatchIn):
    return await asyncio.to_thread(_match, body)


# ---------------------------------------------------------------------------
# AI steps (each may take a while; each has a no-AI fallback)
# ---------------------------------------------------------------------------
class AppIn(BaseModel):
    app_id: str
    details: str = ""
    tone: str = "warm"


def _need(app_id: str) -> dict:
    doc = _load_app(app_id)
    if not doc:
        raise HTTPException(404, "That application isn't saved anymore. Run the match again.")
    return doc


@app.post("/api/tailor")
async def tailor(body: AppIn):
    doc = _need(body.app_id)
    s = load_settings()
    out = await asyncio.to_thread(ai.tailor_resume, doc["resume"], doc["posting"], doc["match"], s)
    with _LOCK:
        fresh = _load_app(body.app_id) or doc
        fresh["tailored"] = out
        fresh["updated"] = time.time()
        _save_app(fresh)
    return out


@app.post("/api/cover-letter")
async def cover(body: AppIn):
    doc = _need(body.app_id)
    s = load_settings()
    out = await asyncio.to_thread(ai.cover_letter, doc["resume"], doc["posting"], doc["match"], body.details[:2000], body.tone, s)
    with _LOCK:
        fresh = _load_app(body.app_id) or doc
        fresh["cover_letter"] = out
        fresh["updated"] = time.time()
        _save_app(fresh)
    return out


class GradeIn(BaseModel):
    app_id: str
    question: str
    answer: str


@app.post("/api/grade")
async def grade(body: GradeIn):
    doc = _need(body.app_id)
    s = load_settings()
    out = await asyncio.to_thread(ai.grade_answer, body.question[:300], body.answer[:3000], doc.get("title", ""), s)
    with _LOCK:
        fresh = _load_app(body.app_id) or doc
        fresh.setdefault("answers", []).append({"q": body.question[:300], "a": body.answer[:3000], "score": out.get("score", 0), "when": time.time(), "result": {k: out.get(k) for k in ("score", "strengths", "improve", "missing_star", "better_answer_outline")}})
        fresh["answers"] = fresh["answers"][-50:]
        fresh["updated"] = time.time()
        _save_app(fresh)
    return out


# ---------------------------------------------------------------------------
# Applications list
# ---------------------------------------------------------------------------
@app.get("/api/apps")
def apps():
    return _list_apps()


@app.get("/api/apps/{app_id}")
def app_get(app_id: str):
    doc = _load_app(app_id)
    if not doc:
        raise HTTPException(404, "That application isn't saved.")
    return doc


class StatusIn(BaseModel):
    status: str


@app.post("/api/apps/{app_id}/status")
def app_status(app_id: str, body: StatusIn):
    if body.status not in ("draft", "applied", "interview", "offer", "rejected", "archived"):
        raise HTTPException(400, "Unknown status.")
    with _LOCK:
        doc = _need(app_id)
        doc["status"] = body.status
        doc["updated"] = time.time()
        _save_app(doc)
    return {"ok": True}


@app.delete("/api/apps/{app_id}")
def app_delete(app_id: str):
    if not _valid_id(app_id):
        raise HTTPException(400, "Bad id.")
    _MEM.pop(app_id, None)
    p = _apps_dir() / f"{app_id}.json"
    existed = p.exists()
    p.unlink(missing_ok=True)
    return {"deleted": existed}


@app.delete("/api/apps")
def apps_delete_all():
    n = len(_MEM)
    _MEM.clear()
    for p in _apps_dir().glob("*.json"):
        p.unlink(missing_ok=True)
        n += 1
    (data_dir() / "resume.txt").unlink(missing_ok=True)
    return {"deleted": n}


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": f"Something went wrong inside the app ({type(exc).__name__}). Try again. If it keeps happening, run: python scripts/selfcheck.py"})
