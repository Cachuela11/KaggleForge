from __future__ import annotations

from db import ResearchDB
from stages import IntakeStage


class Orchestrator:
    """Runs the MLforge pipeline.

    For now, only IntakeStage is active. Research and Write will be aligned next.
    """

    def __init__(self) -> None:
        self.db = ResearchDB()
        self.stages = [
            IntakeStage(self.db),
        ]

    async def start(self, source: str) -> str:
        self.db.create_session(source)
        self.db.save_source(source)

        for stage in self.stages:
            print(f"[{stage.name}] running")
            await stage.run()
            print(f"[{stage.name}] completed")

        return str(self.db.session_dir)

    def status(self) -> list[dict[str, str | int]]:
        return [stage.status() for stage in self.stages]
