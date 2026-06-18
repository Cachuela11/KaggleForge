from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent_runtime import codex_status
from config import PROJECT_ROOT
from orchestrator import Orchestrator
from stage import describe_exception


class StartRequest(BaseModel):
    input: str


app = FastAPI(title="KaggleForge", version="0.1.0")
orchestrator = Orchestrator()
pipeline_task: asyncio.Task | None = None
runtime_status_cache: dict[str, Any] = {"at": 0.0, "data": None}


def _session_required():
    if not orchestrator.db.research_id:
        raise HTTPException(status_code=404, detail="No active session.")
    return orchestrator.db


def _resolve_session_path(relative_path: str) -> Path:
    db = _session_required()
    candidate = (db.session_dir / relative_path).resolve()
    root = db.session_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session path.") from exc
    return candidate


@app.post("/api/pipeline/start")
async def start_pipeline(req: StartRequest) -> dict[str, Any]:
    global pipeline_task
    source = req.input.strip()
    if not source:
        raise HTTPException(status_code=400, detail="Input cannot be empty.")
    if pipeline_task and not pipeline_task.done():
        raise HTTPException(status_code=409, detail="Pipeline is already running.")

    async def runner() -> None:
        await orchestrator.start(source)

    pipeline_task = asyncio.create_task(runner())
    return {"status": "started", "input": source}


@app.get("/api/pipeline/status")
async def pipeline_status() -> dict[str, Any]:
    status = orchestrator.pipeline_status()
    status["task_done"] = bool(pipeline_task.done()) if pipeline_task else True
    if pipeline_task and pipeline_task.done() and pipeline_task.exception():
        status["error"] = describe_exception(pipeline_task.exception())
    return status


@app.get("/api/runtime/status")
async def runtime_status() -> dict[str, Any]:
    now = time.monotonic()
    cached = runtime_status_cache.get("data")
    if cached is not None and now - float(runtime_status_cache["at"]) < 30:
        return cached
    data = codex_status()
    runtime_status_cache["at"] = now
    runtime_status_cache["data"] = data
    return data


@app.get("/api/events")
async def events(request: Request):
    queue = orchestrator.subscribe()

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            orchestrator.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/session/documents")
async def list_documents() -> list[dict[str, Any]]:
    db = _session_required()
    names = [
        "source.md",
        "competition.json",
        "task.md",
        "calibration.md",
        "strategy.md",
        "evaluation.json",
        "results_summary.md",
        "report_context.md",
        "paper.md",
        "report_review.json",
        "paper_polished.md",
    ]
    items = []
    for name in names:
        path = _resolve_session_path(name)
        exists = path.exists() and path.is_file()
        items.append({
            "name": name,
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else 0,
            "path": path.relative_to(db.session_dir).as_posix() if exists else name,
        })
    return items


@app.get("/api/session/files")
async def list_session_files() -> list[dict[str, Any]]:
    db = _session_required()
    return _session_files(db)


def _session_files(db) -> list[dict[str, Any]]:
    root = db.session_dir
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        files.append({
            "path": relative,
            "name": path.name,
            "directory": path.parent.relative_to(root).as_posix() if path.parent != root else "",
            "size_bytes": path.stat().st_size,
            "kind": _file_kind(relative),
            "extension": path.suffix.lower().lstrip("."),
        })
    return files


@app.get("/api/session/task-runs")
async def list_task_runs() -> list[dict[str, Any]]:
    db = _session_required()
    files = _session_files(db)
    file_paths = {item["path"] for item in files}
    plan = db.get_plan()
    runs = []
    for task in plan:
        task_id = str(task.get("id", ""))
        safe_id = db.safe_id(task_id)
        output_path = f"tasks/{safe_id}.md"
        verification_path = f"verifications/{safe_id}.json"
        output_attempts = [
            item for item in files
            if item["path"].startswith(f"tasks/{safe_id}.attempt_")
        ]
        verification_attempts = [
            item for item in files
            if item["path"].startswith(f"verifications/{safe_id}.attempt_")
        ]
        artifacts = [
            item for item in files
            if item["path"].startswith(f"artifacts/{safe_id}/")
        ]
        verification = db.get_verification(task_id)
        workspace = db.session_dir / "workspaces" / safe_id
        children = [
            str(item.get("id"))
            for item in plan
            if str(item.get("parent", "")) == task_id
        ]
        runs.append({
            "task_id": task_id,
            "safe_id": safe_id,
            "title": task.get("title", ""),
            "description": task.get("description", ""),
            "status": task.get("status", "pending"),
            "dependencies": task.get("dependencies", []),
            "parent": task.get("parent", ""),
            "artifact": task.get("artifact", ""),
            "workspace": workspace.relative_to(db.session_dir).as_posix() if workspace.exists() else "",
            "attempt_count": max(len(output_attempts), len(verification_attempts)),
            "verification": verification,
            "redecompose_children": children,
            "files": {
                "output": output_path if output_path in file_paths else "",
                "output_attempts": output_attempts,
                "verification": verification_path if verification_path in file_paths else "",
                "verification_attempts": verification_attempts,
                "artifacts": artifacts,
                "expected_artifact": task.get("artifact", ""),
            },
        })
    return runs


def _file_kind(relative_path: str) -> str:
    first = relative_path.split("/", 1)[0]
    if first == "tasks":
        return "task"
    if first == "verifications":
        return "verification"
    if first == "artifacts":
        return "artifact"
    if first == "workspaces":
        return "workspace"
    if relative_path.startswith("paper") or relative_path.startswith("report_"):
        return "report"
    return "document"


@app.get("/api/session/documents/{name:path}")
async def get_document(name: str) -> dict[str, str]:
    path = _resolve_session_path(name)
    if not path.suffix:
        path = path.with_suffix(".md")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Document not found: {name}")
    return {"name": name, "content": path.read_text(encoding="utf-8", errors="replace")}


@app.get("/api/session/plan/tree")
async def get_plan_tree() -> dict[str, Any]:
    return _session_required().get_plan_tree()


@app.get("/api/session/plan/list")
async def get_plan_list() -> list[dict[str, Any]]:
    return _session_required().get_plan()


@app.get("/api/session/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, str]:
    content = _session_required().get_task_output(task_id)
    if not content:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return {"task_id": task_id, "content": content}


@app.get("/api/session/verifications/{task_id}")
async def get_verification(task_id: str) -> dict[str, Any]:
    data = _session_required().get_verification(task_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Verification not found: {task_id}")
    return data


@app.get("/api/session/artifacts")
async def list_artifacts() -> list[dict[str, Any]]:
    return _session_required().list_artifacts()


@app.get("/api/session/artifacts/{artifact_path:path}")
async def get_artifact(artifact_path: str):
    path = _resolve_session_path(f"artifacts/{artifact_path}")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_path}")
    return FileResponse(path)


frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
