from __future__ import annotations

from agent_runtime import agent
from db import ResearchDB
from stage import Stage


class ReportStage(Stage):
    def __init__(self, db: ResearchDB) -> None:
        super().__init__("report")
        self.db = db

    async def execute(self) -> str:
        task = self.db.get_task()
        calibration = self.db.get_calibration()
        strategy = self.db.get_strategy()
        results_summary = self.db.read_text("results_summary.md")
        tasks = self.db.get_plan()
        task_sections = []
        for task_item in tasks:
            output = self.db.get_task_output(task_item["id"])
            task_sections.append(f"### {task_item['title']}\n\n{output}")

        paper = await agent(
            "Write a concise Chinese technical report in Markdown from the task brief, strategy, calibration, and research outputs.",
            "# Task\n\n"
            f"{task}\n\n"
            "# Calibration\n\n"
            f"{calibration}\n\n"
            "# Strategy\n\n"
            f"{strategy}\n\n"
            "# Results Summary\n\n"
            f"{results_summary}\n\n"
            "# Task Outputs\n\n"
            + "\n\n".join(task_sections),
            cwd=self.db.session_dir,
        )
        self.db.save_paper(paper)
        return paper


WriteStage = ReportStage
