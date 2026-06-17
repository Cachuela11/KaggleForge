from __future__ import annotations

import asyncio
import queue
from typing import Any

from db import ResearchDB
from stage import describe_exception
from stages import IntakeStage, ReportStage, ResearchStage


class Orchestrator:
    """Runs the KaggleForge pipeline.

    IntakeStage builds the task context, ResearchStage produces artifacts, and
    ReportStage synthesizes the final technical report.
    """

    def __init__(self) -> None:
        self.db = ResearchDB()
        self.stages = [
            IntakeStage(self.db),
            ResearchStage(self.db),
            ReportStage(self.db),
        ]
        self._subscribers: set[Any] = set()
        self._running = False
        self._source = ""
        for stage in self.stages:
            stage.event_sink = self.broadcast

    async def start(self, source: str) -> str:
        if self._running:
            raise RuntimeError("Pipeline is already running.")
        self._running = True
        self._source = source
        self.db.create_session(source)
        self.db.save_source(source)
        self.broadcast({
            "type": "pipeline.started",
            "source": source,
            "session_id": self.db.research_id,
            "session_dir": str(self.db.session_dir),
        })

        try:
            for stage in self.stages:
                print(f"[{stage.name}] running")
                await stage.run()
                print(f"[{stage.name}] completed")
        except Exception as exc:
            self.broadcast({"type": "pipeline.failed", "error": describe_exception(exc)})
            raise
        finally:
            self._running = False

        self.broadcast({
            "type": "pipeline.completed",
            "session_id": self.db.research_id,
            "session_dir": str(self.db.session_dir),
        })
        return str(self.db.session_dir)

    def status(self) -> list[dict[str, str | int]]:
        return [stage.status() for stage in self.stages]

    def pipeline_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "source": self._source,
            "session_id": self.db.research_id,
            "session_dir": str(self.db.session_dir) if self.db.research_id else "",
            "stages": self.status(),
        }

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def subscribe_threaded(self) -> queue.Queue[dict[str, Any]]:
        threaded_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        self._subscribers.add(threaded_queue)
        return threaded_queue

    def unsubscribe(self, subscriber: Any) -> None:
        self._subscribers.discard(subscriber)

    def broadcast(self, event: dict[str, Any]) -> None:
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(event)
            except (asyncio.QueueFull, queue.Full):
                pass
