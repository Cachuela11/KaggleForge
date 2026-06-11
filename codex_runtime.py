from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class CodexCliRuntime:
    """Small non-interactive Codex CLI runtime.

    MLforge owns the pipeline, while Codex executes each stage inside the
    current session directory.
    """

    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        model: str = "",
        reasoning_effort: str = "",
        verbosity: str = "",
        sandbox: str = "workspace-write",
        timeout: int = 1800,
        inherit_proxy: bool = True,
    ) -> None:
        self.codex_bin = codex_bin
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.sandbox = sandbox
        self.timeout = timeout
        self.inherit_proxy = inherit_proxy

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
            stdin=subprocess.DEVNULL,
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
        codex_executable = shutil.which(self.codex_bin) or self.codex_bin
        if not Path(codex_executable).exists() and not shutil.which(codex_executable):
            raise RuntimeError(
                f"Codex executable not found: {self.codex_bin}. "
                "Set MLFORGE_CODEX_BIN in .env to the absolute codex.EXE path."
            )
        cmd = [
            codex_executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            self.sandbox,
            "--cd",
            str(cwd),
            "-c",
            'shell_environment_policy.inherit="none"',
            "-c",
            'shell_environment_policy.include_only=["PATH","HOME","TMPDIR"]',
            "--output-last-message",
            str(output_path),
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.reasoning_effort:
            cmd.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        if self.verbosity:
            cmd.extend(["-c", f'model_verbosity="{self.verbosity}"'])
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
                "Legacy in-process tool calling is not available.",
                "Use the current working directory as the research session directory.",
                "Useful files may include idea.md, competition.json, refined_idea.md, plan_list.json, tasks/, artifacts/, and paper.md.",
                "Use shell/Python commands and file inspection when useful, then produce a concise final answer.",
                "Do not ask for human input. Complete the requested node directly.",
                "# User Task",
                user_text.strip(),
            ]
        )

    def _build_env(self) -> dict[str, str]:
        allowed = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "SystemRoot",
            "COMSPEC",
            "ComSpec",
            "HOME",
            "USER",
            "LOGNAME",
            "SHELL",
            "USERPROFILE",
            "TMP",
            "TEMP",
            "TMPDIR",
            "CODEX_HOME",
            "CODEX_API_KEY",
            "OPENAI_API_KEY",
            "CODEX_CA_CERTIFICATE",
            "SSL_CERT_FILE",
        }
        if self.inherit_proxy:
            allowed.update({
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "no_proxy",
            })
        return {key: value for key, value in os.environ.items() if key in allowed and value}

    def status(self) -> dict[str, str | bool]:
        codex_path = shutil.which(self.codex_bin) or ""
        version = ""
        error = ""
        connected = False
        if not codex_path:
            error = f"Codex binary not found: {self.codex_bin}"
        else:
            try:
                result = subprocess.run(
                    [self.codex_bin, "--version"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=self._build_env(),
                )
                connected = result.returncode == 0
                version = result.stdout.strip() or result.stderr.strip()
                if not connected:
                    error = result.stderr.strip()
            except Exception as exc:
                error = str(exc)
        return {
            "connected": connected,
            "codex_bin": self.codex_bin,
            "path": codex_path,
            "version": version,
            "sandbox": self.sandbox,
            "model": self.model or "Codex default",
            "reasoning_effort": self.reasoning_effort or "Codex default",
            "verbosity": self.verbosity or "Codex default",
            "inherit_proxy": self.inherit_proxy,
            "error": error,
        }

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
