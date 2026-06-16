from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from agent_runtime import agent
from config import settings
from db import ResearchDB
from prompts import (
    DECOMPOSE_SYSTEM,
    EVALUATE_SYSTEM,
    EXECUTE_SYSTEM,
    STRATEGY_SYSTEM,
    VERIFY_SYSTEM,
)
from stage import Stage
from utils import parse_json_fenced


class ResearchStage(Stage):
    def __init__(self, db: ResearchDB) -> None:
        super().__init__("research")
        self.db = db

    async def execute(self) -> str:
        self.db.artifacts_dir()

        print("[research] strategy")
        self.emit(phase="strategy", status="running")
        strategy = await self._strategy()
        self.emit(phase="strategy", status="completed")
        print("[research] decompose")
        self.emit(phase="decompose", status="running")
        plan = await self._decompose(strategy)
        self.emit(phase="decompose", status="completed")
        print("[research] execute + verify")
        self.emit(phase="execute", status="running")
        completed = await self._execute_and_verify(plan)
        self.emit(phase="execute", status="completed")
        print("[research] evaluate")
        self.emit(phase="evaluate", status="running")
        evaluation = await self._evaluate(strategy, plan, completed)
        self.emit(phase="evaluate", status="completed")
        summary = self._build_results_summary(strategy, plan, completed, evaluation)
        self.db.save_results_summary(summary["data"], summary["markdown"])
        return summary["markdown"]

    async def _strategy(self) -> str:
        existing = self.db.get_strategy()
        if existing:
            return existing

        strategy = await agent(
            STRATEGY_SYSTEM,
            self._build_strategy_user(),
            cwd=self.db.session_dir,
        )
        self.db.save_strategy(strategy)
        return strategy

    async def _decompose(self, strategy: str) -> list[dict[str, Any]]:
        existing = self.db.get_plan()
        if existing:
            return existing

        response = await agent(
            DECOMPOSE_SYSTEM,
            self._build_decompose_user(strategy),
            cwd=self.db.session_dir,
        )
        data = parse_json_fenced(response, default={})
        tasks = self._normalize_tasks(data.get("tasks", []))
        if not tasks:
            tasks = self._fallback_plan()

        tree = {
            "id": "0",
            "description": "Research stage root",
            "children": tasks,
        }
        self.db.save_plan_tree(tree)
        self.db.save_plan(tasks)
        return tasks

    async def _execute_and_verify(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        completed: dict[str, dict[str, Any]] = {}
        semaphore = asyncio.Semaphore(max(1, settings.api_concurrency))
        for batch_index, batch in enumerate(self._topological_batches(tasks), start=1):
            self.emit(
                phase="execute",
                status="batch_running",
                batch=batch_index,
                task_ids=[task["id"] for task in batch],
            )
            dependency_snapshot = dict(completed)
            results = await asyncio.gather(
                *[
                    self._execute_one_task(task, dependency_snapshot, semaphore)
                    for task in batch
                ],
                return_exceptions=True,
            )

            for task, result in zip(batch, results):
                task_id = task["id"]
                if isinstance(result, Exception):
                    task["status"] = "failed"
                    self.db.save_plan(tasks)
                    self.emit(
                        phase="execute",
                        status="failed",
                        task_id=task_id,
                        error=str(result),
                    )
                    raise result

                completed[task_id] = result
                task["status"] = "completed"
                task["summary"] = result.get("summary", "")
                self.emit(phase="execute", status="completed", task_id=task_id)

            self.db.save_plan(tasks)
            self.emit(
                phase="execute",
                status="batch_completed",
                batch=batch_index,
                task_ids=[task["id"] for task in batch],
            )

        return list(completed.values())

    async def _execute_one_task(
        self,
        task: dict[str, Any],
        completed: dict[str, dict[str, Any]],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with semaphore:
            task_id = task["id"]
            workspace = self._prepare_task_workspace(task, completed)
            print(f"[research] execute task {task_id}: {task.get('title', '')}")
            self.emit(
                phase="execute",
                status="running",
                task_id=task_id,
                task=task,
                workspace=str(workspace),
            )

            output = self.db.get_task_output(task_id)
            if not output:
                output = await agent(
                    EXECUTE_SYSTEM,
                    self._build_workspace_execute_user(task, completed, workspace),
                    cwd=workspace,
                )
                self.db.save_task_output(task_id, output)

            self._sync_task_artifacts(task_id, workspace)

            verification = self.db.get_verification(task_id)
            if not verification:
                print(f"[research] verify task {task_id}")
                self.emit(phase="verify", status="running", task_id=task_id, task=task)
                verification = await self._verify(task, output)
                self.db.save_verification(task_id, verification)
                self.emit(
                    phase="verify",
                    status="completed",
                    task_id=task_id,
                    verification=verification,
                )

            return {
                "task": task,
                "output": output,
                "verification": verification,
                "summary": self._extract_summary(output),
            }

    async def _verify(self, task: dict[str, Any], output: str) -> dict[str, Any]:
        response = await agent(
            VERIFY_SYSTEM,
            self._build_verify_user(task, output),
            cwd=self.db.session_dir,
        )
        data = parse_json_fenced(response, default={})
        if "pass" not in data:
            return {
                "pass": False,
                "review": "Verify agent did not return valid JSON.",
            }
        return {
            "pass": bool(data.get("pass")),
            "review": str(data.get("review", "")),
        }

    async def _evaluate(
        self,
        strategy: str,
        plan: list[dict[str, Any]],
        completed: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing = self.db.get_evaluation()
        if existing:
            return existing

        response = await agent(
            EVALUATE_SYSTEM,
            self._build_evaluate_user(strategy, plan, completed),
            cwd=self.db.session_dir,
        )
        data = parse_json_fenced(response, default={})
        evaluation = {
            "feedback": str(data.get("feedback", "")),
            "suggestions": data.get("suggestions", []),
            "ready_for_report": bool(data.get("ready_for_report", True)),
        }
        if not isinstance(evaluation["suggestions"], list):
            evaluation["suggestions"] = [str(evaluation["suggestions"])]
        self.db.save_evaluation(evaluation)
        return evaluation

    def _build_strategy_user(self) -> str:
        return "\n\n".join(
            [
                "# Task",
                self.db.get_task(),
                "# Competition metadata",
                self._format_jsonish(self.db.get_competition_info()),
                "# Calibration",
                self.db.get_calibration(),
                "# Request",
                "请制定 research stage 的技术策略。输出中文。",
            ]
        )

    def _build_decompose_user(self, strategy: str) -> str:
        return "\n\n".join(
            [
                "# Task",
                self.db.get_task(),
                "# Competition metadata",
                self._format_jsonish(self.db.get_competition_info()),
                "# Calibration",
                self.db.get_calibration(),
                "# Strategy",
                strategy,
                "# Request",
                "请拆成原子任务 DAG。只输出 JSON。",
            ]
        )

    def _build_execute_user(
        self,
        task: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> str:
        dependency_summaries = []
        for dep_id in task.get("dependencies", []):
            dep = completed.get(dep_id)
            if dep:
                dependency_summaries.append(f"- [{dep_id}] {dep.get('summary') or '(no summary)'}")

        artifact = task.get("artifact") or f"artifacts/{task['id']}/result.md"
        return "\n\n".join(
            [
                "# Task brief",
                self.db.get_task(),
                "# Competition metadata",
                self._format_jsonish(self.db.get_competition_info()),
                "# Strategy",
                self.db.get_strategy(),
                "# Current atomic task",
                self._format_jsonish(task),
                "# Dependency summaries",
                "\n".join(dependency_summaries) or "(none)",
                "# Artifact requirement",
                f"请把本任务持久产物写到 `{artifact}`。"
                "如果需要额外文件，也放在同一个 task artifact 目录下。",
            ]
        )

    def _build_workspace_execute_user(
        self,
        task: dict[str, Any],
        completed: dict[str, dict[str, Any]],
        workspace: Path,
    ) -> str:
        artifact = task.get("artifact") or f"artifacts/{task['id']}/result.md"
        workspace_artifact = self._workspace_artifact_path(task)
        contract = "\n".join(
            [
                "# Workspace contract",
                f"- Current task workspace: `{workspace}`",
                f"- Session directory: `{self.db.session_dir}`",
                f"- Kaggle data directory: `{settings.dataset_dir}`",
                "- Execute this task in the current workspace.",
                "- Read copied files in this workspace first: `task.md`, `competition.json`, `strategy.md`, `plan_list.json`, `current_task.json`, and `dependencies.md`.",
                "- Write durable outputs under `./artifacts/` in the current workspace.",
                f"- MLforge will sync `./artifacts/` back to session `artifacts/{self.db.safe_id(task['id'])}/` after this agent call.",
                f"- The decompose-requested artifact path is `{artifact}`.",
                f"- In this workspace, prefer writing the primary artifact as `{workspace_artifact}`.",
                "- Do not rely on conversation memory from other tasks. Use dependency summaries and persisted files only.",
            ]
        )
        return contract + "\n\n" + self._build_execute_user(task, completed)

    def _workspace_artifact_path(self, task: dict[str, Any]) -> str:
        task_id = str(task["id"])
        artifact = str(task.get("artifact") or f"artifacts/{task_id}/result.md").replace("\\", "/")
        prefix = f"artifacts/{task_id}/"
        safe_prefix = f"artifacts/{self.db.safe_id(task_id)}/"
        if artifact.startswith(prefix):
            return f"artifacts/{artifact[len(prefix):]}"
        if artifact.startswith(safe_prefix):
            return f"artifacts/{artifact[len(safe_prefix):]}"
        if artifact.startswith("artifacts/"):
            return artifact
        return f"artifacts/{artifact}"

    def _prepare_task_workspace(
        self,
        task: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> Path:
        task_id = task["id"]
        workspace = self.db.task_workspace_dir(task_id)
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)

        for name in (
            "source.md",
            "task.md",
            "competition.json",
            "calibration.md",
            "strategy.md",
            "plan_list.json",
            "plan_tree.json",
            "results_summary.md",
            "results_summary.json",
        ):
            src = self.db.session_dir / name
            if src.exists() and src.is_file():
                shutil.copy2(src, workspace / name)

        current_task = dict(task)
        current_task["workspace"] = str(workspace)
        current_task["session_dir"] = str(self.db.session_dir)
        current_task["dataset_dir"] = str(settings.dataset_dir)
        (workspace / "current_task.json").write_text(
            json.dumps(current_task, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        dependency_lines = []
        for dep_id in task.get("dependencies", []):
            dep = completed.get(dep_id)
            if not dep:
                continue
            dependency_lines.extend(
                [
                    f"## Dependency {dep_id}",
                    "",
                    f"- Summary: {dep.get('summary') or '(no summary)'}",
                    f"- Verification pass: {dep.get('verification', {}).get('pass')}",
                    f"- Task output: `../../tasks/{self.db.safe_id(dep_id)}.md`",
                    "",
                ]
            )
        (workspace / "dependencies.md").write_text(
            "\n".join(dependency_lines) or "(none)\n",
            encoding="utf-8",
        )
        return workspace

    def _sync_task_artifacts(self, task_id: str, workspace: Path) -> None:
        source = workspace / "artifacts"
        if not source.exists():
            return
        target = self.db.task_artifacts_dir(task_id)
        safe_id = self.db.safe_id(task_id)
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(source)
            parts = rel.parts
            if parts and parts[0] in {safe_id, str(task_id)}:
                rel = Path(*parts[1:]) if len(parts) > 1 else Path(path.name)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

    @staticmethod
    def _build_verify_user(task: dict[str, Any], output: str) -> str:
        return "\n\n".join(
            [
                "# Atomic task",
                ResearchStage._format_jsonish(task),
                "# Execute output",
                output,
                "# Request",
                "请判断该任务是否通过。只输出 JSON。",
            ]
        )

    def _build_evaluate_user(
        self,
        strategy: str,
        plan: list[dict[str, Any]],
        completed: list[dict[str, Any]],
    ) -> str:
        task_lines = []
        for item in completed:
            task = item["task"]
            verification = item["verification"]
            task_lines.append(
                f"- [{task['id']}] {task.get('title', '')}: "
                f"{item.get('summary') or '(no summary)'} | pass={verification.get('pass')}"
            )
        return "\n\n".join(
            [
                "# Task",
                self.db.get_task(),
                "# Strategy",
                strategy,
                "# Plan",
                self._format_jsonish(plan),
                "# Completed task summaries",
                "\n".join(task_lines),
                "# Artifacts",
                self._format_jsonish(self.db.list_artifacts()),
                "# Request",
                "请评估本轮 research 结果是否足够进入 report stage。只输出 JSON。",
            ]
        )

    @staticmethod
    def _normalize_tasks(raw_tasks: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_tasks, list):
            return []

        normalized = []
        seen = set()
        for index, raw in enumerate(raw_tasks, start=1):
            if not isinstance(raw, dict):
                continue
            task_id = str(raw.get("id") or index)
            if task_id in seen:
                continue
            seen.add(task_id)
            dependencies = raw.get("dependencies", [])
            if not isinstance(dependencies, list):
                dependencies = []
            dependencies = [str(dep) for dep in dependencies if str(dep) in seen]
            artifact = str(raw.get("artifact") or f"artifacts/{task_id}/result.md")
            normalized.append(
                {
                    "id": task_id,
                    "title": str(raw.get("title") or f"Task {task_id}"),
                    "description": str(raw.get("description") or raw.get("title") or ""),
                    "dependencies": dependencies,
                    "artifact": artifact,
                    "status": "pending",
                }
            )
        return normalized

    @staticmethod
    def _topological_order(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        remaining = {task["id"]: task for task in tasks}
        completed: set[str] = set()
        ordered: list[dict[str, Any]] = []
        while remaining:
            ready = [
                task_id for task_id, task in remaining.items()
                if all(dep in completed for dep in task.get("dependencies", []))
            ]
            if not ready:
                ready = list(remaining.keys())
            for task_id in ready:
                ordered.append(remaining.pop(task_id))
                completed.add(task_id)
        return ordered

    @staticmethod
    def _topological_batches(tasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        remaining = {task["id"]: task for task in tasks}
        completed: set[str] = set()
        batches: list[list[dict[str, Any]]] = []
        while remaining:
            ready = [
                task_id for task_id, task in remaining.items()
                if all(dep in completed for dep in task.get("dependencies", []))
            ]
            if not ready:
                ready = list(remaining.keys())
            batch = [remaining.pop(task_id) for task_id in ready]
            batches.append(batch)
            completed.update(ready)
        return batches

    @staticmethod
    def _extract_summary(output: str) -> str:
        for line in reversed(output.strip().splitlines()):
            stripped = line.strip()
            if stripped.upper().startswith("SUMMARY:"):
                return stripped[len("SUMMARY:"):].strip()
        return ""

    @staticmethod
    def _format_jsonish(data: Any) -> str:
        import json

        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def _fallback_plan() -> list[dict[str, Any]]:
        return [
            {
                "id": "1",
                "title": "数据概览",
                "description": "读取 competition.json 指定的数据目录，检查 train/test/sample_submission 的字段、行数、缺失值和提交格式，输出数据概览报告。",
                "dependencies": [],
                "artifact": "artifacts/1/profile.md",
                "status": "pending",
            },
            {
                "id": "2",
                "title": "Baseline 脚本",
                "description": "基于数据概览实现一个可复现 baseline 训练脚本，包含固定随机种子、简单预处理、本地验证和 submission 生成逻辑。",
                "dependencies": ["1"],
                "artifact": "artifacts/2/baseline.py",
                "status": "pending",
            },
            {
                "id": "3",
                "title": "验证结果总结",
                "description": "运行或检查 baseline 输出，记录验证指标、主要发现、潜在问题和下一步改进方向。",
                "dependencies": ["2"],
                "artifact": "artifacts/3/validation_report.md",
                "status": "pending",
            },
        ]

    def _build_results_summary(
        self,
        strategy: str,
        plan: list[dict[str, Any]],
        completed: list[dict[str, Any]],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        artifacts = self.db.list_artifacts()
        data = {
            "strategy_file": "strategy.md",
            "plan_file": "plan_list.json",
            "task_count": len(plan),
            "completed_count": len(completed),
            "artifacts": artifacts,
            "evaluation": evaluation,
        }

        lines = [
            "# Research Results Summary",
            "",
            "## Strategy",
            "",
            strategy.strip(),
            "",
            "## Completed Tasks",
            "",
        ]
        for item in completed:
            task = item["task"]
            verification = item["verification"]
            lines.extend(
                [
                    f"### [{task['id']}] {task.get('title', '')}",
                    "",
                    f"- Artifact: `{task.get('artifact', '')}`",
                    f"- Verified: `{verification.get('pass')}`",
                    f"- Summary: {item.get('summary') or '(no summary)'}",
                    "",
                ]
            )
        lines.extend(
            [
                "## Artifacts",
                "",
                *[f"- `{item['path']}` ({item['size_bytes']} bytes)" for item in artifacts],
                "",
                "## Evaluation",
                "",
                self._format_jsonish(evaluation),
                "",
            ]
        )
        return {"data": data, "markdown": "\n".join(lines)}
