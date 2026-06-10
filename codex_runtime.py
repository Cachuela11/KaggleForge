from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path


class CodexCliRuntime:
    """Small non-interactive Codex CLI runtime.

    This mirrors the important part of MAARS: MLforge owns the pipeline, while
    Codex executes each stage inside the current session directory.
    """

    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        model: str = "",
        reasoning_effort: str = "",
        sandbox: str = "workspace-write",
        timeout: int = 1800,
    ) -> None:
        self.codex_bin = codex_bin
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.sandbox = sandbox
        self.timeout = timeout

    async def run(self, *, instruction: str, user_text: str, cwd: Path) -> str:
        cwd.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(instruction, user_text)

        with tempfile.NamedTemporaryFile(
            prefix="mlforge_codex_",
            suffix=".md",
            delete=False,
        ) as tmp:
            output_path = Path(tmp.name)

        cmd = self._build_command(cwd=cwd, prompt=prompt, output_path=output_path)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_env(),
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            output_path.unlink(missing_ok=True)
            raise TimeoutError("Codex call timed out")

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        self._print_codex_events(stdout)

        result = ""
        if output_path.exists():
            result = output_path.read_text(encoding="utf-8", errors="replace")
            output_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            detail = stderr.strip() or self._tail(stdout)
            raise RuntimeError(f"Codex failed with exit code {proc.returncode}: {detail}")

        return result.strip()

    def _build_command(self, *, cwd: Path, prompt: str, output_path: Path) -> list[str]:
        cmd = [
            self.codex_bin,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            self.sandbox,
            "--cd",
            str(cwd),
            "--output-last-message",
            str(output_path),
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.reasoning_effort:
            cmd.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        cmd.append(prompt)
        return cmd

    @staticmethod
    def _build_prompt(instruction: str, user_text: str) -> str:
        return "\n\n".join(
            [
                "# System Instructions",
                instruction.strip(),
                "# MLforge Runtime",
                "You are running through the Codex CLI.",
                "Use the current working directory as the research session directory.",
                "Read and write files when useful, then produce a concise final answer.",
                "# User Task",
                user_text.strip(),
            ]
        )

    @staticmethod
    def _build_env() -> dict[str, str]:
        allowed = {
            "PATH",
            "HOME",
            "USERPROFILE",
            "TMP",
            "TEMP",
            "CODEX_HOME",
            "CODEX_API_KEY",
            "OPENAI_API_KEY",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        }
        return {key: value for key, value in os.environ.items() if key in allowed and value}

    @staticmethod
    def _print_codex_events(stdout: str) -> None:
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message") or event.get("text") or ""
            item = event.get("item")
            if not message and isinstance(item, dict):
                message = item.get("text") or item.get("command") or ""
            if message:
                print(f"  codex: {message}")

    @staticmethod
    def _tail(text: str, max_lines: int = 10) -> str:
        lines = [line for line in text.splitlines() if line.strip()]
        return "\n".join(lines[-max_lines:])
