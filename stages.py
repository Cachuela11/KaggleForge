from __future__ import annotations

from db import ResearchDB
from agent_runtime import agent
from stage import Stage


class RefineStage(Stage):
    def __init__(self, db: ResearchDB) -> None:
        super().__init__("refine")
        self.db = db

    async def execute(self) -> str:
        idea = self.db.get_idea()
        refined = await agent(
            "Refine the rough research idea into a clear research proposal.",
            idea,
            cwd=self.db.session_dir,
        )
        self.db.save_refined_idea(refined)
        return refined


class ResearchStage(Stage):
    def __init__(self, db: ResearchDB) -> None:
        super().__init__("research")
        self.db = db

    async def execute(self) -> str:
        refined = self.db.get_refined_idea()
        tasks = [
            {
                "id": "1",
                "title": "Clarify hypothesis",
                "summary": "State the main hypothesis and measurable outcome.",
            },
            {
                "id": "2",
                "title": "Design experiment",
                "summary": "Sketch a minimal experiment or analysis plan.",
            },
            {
                "id": "3",
                "title": "Interpret expected results",
                "summary": "Describe what success or failure would imply.",
            },
        ]
        self.db.save_plan(tasks)

        outputs: list[str] = []
        for task in tasks:
            result = await agent(
                f"Execute research task: {task['title']}.",
                f"{refined}\n\nTask summary: {task['summary']}",
                cwd=self.db.session_dir,
            )
            self.db.save_task_output(task["id"], result)
            outputs.append(f"## Task {task['id']}: {task['title']}\n\n{result}")

        return "\n\n".join(outputs)


class WriteStage(Stage):
    def __init__(self, db: ResearchDB) -> None:
        super().__init__("write")
        self.db = db

    async def execute(self) -> str:
        refined = self.db.get_refined_idea()
        tasks = self.db.get_plan()
        task_sections = []
        for task in tasks:
            output = self.db.get_task_output(task["id"])
            task_sections.append(f"### {task['title']}\n\n{output}")

        paper = await agent(
            "Write a concise research report in Markdown from the proposal and task outputs.",
            f"# Refined Idea\n\n{refined}\n\n# Task Outputs\n\n" + "\n\n".join(task_sections),
            cwd=self.db.session_dir,
        )
        self.db.save_paper(paper)
        return paper
