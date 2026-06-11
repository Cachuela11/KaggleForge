from __future__ import annotations

from db import ResearchDB
from stages import RefineStage


class Orchestrator:
    """Runs the MLforge pipeline.

    For now, only RefineStage is active. Research and Write will be aligned next.
    """

    def __init__(self) -> None:
        self.db = ResearchDB()
        self.stages = [
            RefineStage(self.db),
        ]

    async def start(self, idea: str) -> str:
        self.db.create_session(idea)
        self.db.save_idea(idea)

        for stage in self.stages:
            print(f"[{stage.name}] running")
            await stage.run()
            print(f"[{stage.name}] completed")

        return str(self.db.session_dir)

    def status(self) -> list[dict[str, str | int]]:
        return [stage.status() for stage in self.stages]
