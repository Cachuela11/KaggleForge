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

    def create_session(self, source: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = self._source_slug(source)
        self.research_id = f"{timestamp}-{slug}"
        self._root = self.base_dir / self.research_id
        self._root.mkdir(parents=True, exist_ok=True)
        return self.research_id

    @staticmethod
    def _source_slug(source: str) -> str:
        competition = re.search(
            r"(?:https?://)?(?:www\.)?kaggle\.com/competitions/([a-zA-Z0-9_-]+)",
            source.strip(),
        )
        if competition:
            return competition.group(1).lower()

        words = re.sub(r"[^a-zA-Z0-9\s_-]", "", source).lower().split()[:6]
        slug = "-".join(words)
        return slug or "research"

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

    def save_source(self, text: str) -> None:
        self.save_text("source.md", text)

    def get_source(self) -> str:
        return self.read_text("source.md")

    def save_task(self, text: str) -> None:
        self.save_text("task.md", text)

    def get_task(self) -> str:
        return self.read_text("task.md")

    def save_calibration(self, text: str) -> None:
        self.save_text("calibration.md", text)

    def get_calibration(self) -> str:
        return self.read_text("calibration.md")

    def save_strategy(self, text: str) -> None:
        self.save_text("strategy.md", text)

    def get_strategy(self) -> str:
        return self.read_text("strategy.md")

    def save_competition_info(self, data: dict[str, Any]) -> None:
        self.save_json("competition.json", data)

    def get_competition_info(self) -> dict[str, Any]:
        return self.read_json("competition.json", {})

    def save_plan_tree(self, tree: dict[str, Any]) -> None:
        self.save_json("plan_tree.json", tree)

    def get_plan_tree(self) -> dict[str, Any]:
        return self.read_json("plan_tree.json", {})

    def save_plan(self, tasks: list[dict[str, Any]]) -> None:
        self.save_json("plan_list.json", tasks)

    def get_plan(self) -> list[dict[str, Any]]:
        return self.read_json("plan_list.json", [])

    def save_task_output(self, task_id: str, text: str) -> None:
        safe_id = task_id.replace("/", "_")
        self.save_text(f"tasks/{safe_id}.md", text)

    def get_task_output(self, task_id: str) -> str:
        safe_id = task_id.replace("/", "_")
        return self.read_text(f"tasks/{safe_id}.md")

    def save_verification(self, task_id: str, data: dict[str, Any]) -> None:
        safe_id = task_id.replace("/", "_")
        self.save_json(f"verifications/{safe_id}.json", data)

    def get_verification(self, task_id: str) -> dict[str, Any]:
        safe_id = task_id.replace("/", "_")
        return self.read_json(f"verifications/{safe_id}.json", {})

    def save_evaluation(self, data: dict[str, Any]) -> None:
        self.save_json("evaluation.json", data)

    def get_evaluation(self) -> dict[str, Any]:
        return self.read_json("evaluation.json", {})

    def artifacts_dir(self) -> Path:
        path = self.session_dir / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_artifacts(self) -> list[dict[str, Any]]:
        root = self.session_dir
        artifacts = root / "artifacts"
        if not artifacts.exists():
            return []
        items = []
        for path in sorted(artifacts.rglob("*")):
            if path.is_file():
                items.append({
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                })
        return items

    def save_results_summary(self, data: dict[str, Any], markdown: str) -> None:
        self.save_json("results_summary.json", data)
        self.save_text("results_summary.md", markdown)

    def save_paper(self, text: str) -> None:
        self.save_text("paper.md", text)

    def save_paper_polished(self, text: str) -> None:
        self.save_text("paper_polished.md", text)
