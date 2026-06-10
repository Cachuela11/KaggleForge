from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


class ResearchDB:
    """File-based storage for one research session."""

    def __init__(self, base_dir: str = "results") -> None:
        root = Path(__file__).resolve().parent
        self.base_dir = Path(base_dir)
        if not self.base_dir.is_absolute():
            self.base_dir = root / self.base_dir
        self.research_id = ""
        self._root: Path | None = None

    @property
    def session_dir(self) -> Path:
        if self._root is None:
            raise RuntimeError("No active session. Call create_session() first.")
        return self._root

    def create_session(self, idea: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        words = re.sub(r"[^a-zA-Z0-9\s]", "", idea).lower().split()[:6]
        slug = "-".join(words) or "research"
        self.research_id = f"{timestamp}-{slug}"
        self._root = self.base_dir / self.research_id
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "tasks").mkdir(exist_ok=True)
        return self.research_id

    def save_text(self, relative_path: str, text: str) -> None:
        path = self.session_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read_text(self, relative_path: str) -> str:
        path = self.session_dir / relative_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def save_json(self, relative_path: str, data: Any) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False)
        self.save_text(relative_path, text)

    def read_json(self, relative_path: str, default: Any) -> Any:
        text = self.read_text(relative_path)
        if not text:
            return default
        return json.loads(text)

    def save_idea(self, text: str) -> None:
        self.save_text("idea.md", text)

    def get_idea(self) -> str:
        return self.read_text("idea.md")

    def save_refined_idea(self, text: str) -> None:
        self.save_text("refined_idea.md", text)

    def get_refined_idea(self) -> str:
        return self.read_text("refined_idea.md")

    def save_plan(self, tasks: list[dict[str, str]]) -> None:
        self.save_json("plan_list.json", tasks)

    def get_plan(self) -> list[dict[str, str]]:
        return self.read_json("plan_list.json", [])

    def save_task_output(self, task_id: str, text: str) -> None:
        safe_id = task_id.replace("/", "_")
        self.save_text(f"tasks/{safe_id}.md", text)

    def get_task_output(self, task_id: str) -> str:
        safe_id = task_id.replace("/", "_")
        return self.read_text(f"tasks/{safe_id}.md")

    def save_paper(self, text: str) -> None:
        self.save_text("paper.md", text)
