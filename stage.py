from __future__ import annotations

from enum import Enum


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

    async def run(self) -> str:
        self.state = StageState.RUNNING
        self.error = ""
        try:
            self.output = await self.execute()
            self.state = StageState.COMPLETED
            return self.output
        except Exception as exc:
            self.state = StageState.FAILED
            self.error = str(exc)
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
