from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any


def describe_exception(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{type(exc).__module__}.{type(exc).__name__}: {exc!r}"


class StageState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Stage:
    """Base lifecycle shared by all pipeline stages."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.state = StageState.IDLE
        self.output = ""
        self.error = ""
        self.event_sink: Callable[[dict[str, Any]], None] | None = None

    def reset(self) -> None:
        self.state = StageState.IDLE
        self.output = ""
        self.error = ""

    async def run(self) -> str:
        self.state = StageState.RUNNING
        self.error = ""
        self.emit(status="running")
        try:
            self.output = await self.execute()
            self.state = StageState.COMPLETED
            self.emit(status="completed")
            return self.output
        except Exception as exc:
            self.state = StageState.FAILED
            self.error = describe_exception(exc)
            self.emit(status="failed", error=self.error)
            raise

    async def execute(self) -> str:
        raise NotImplementedError

    def status(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "state": self.state.value,
            "output_length": len(self.output),
            "error": self.error,
        }

    def emit(self, **event: Any) -> None:
        if not self.event_sink:
            return
        payload = {"stage": self.name, **event}
        self.event_sink(payload)
