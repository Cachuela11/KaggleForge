from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path


class CodexCliRuntime:
    """Small non-interactive Codex CLI runtime.

    KaggleForge owns the pipeline, while Codex executes each stage inside the
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
        sandbox_provider: str = "docker",
        docker_image: str = "",
        docker_bin: str = "docker",
        docker_codex_bin: str = "codex",
        docker_gpus: str = "",
    ) -> None:
        self.codex_bin = codex_bin
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.sandbox = sandbox
        self.timeout = timeout
        self.inherit_proxy = inherit_proxy
        self.sandbox_provider = sandbox_provider.strip().lower() or "docker"
        self.docker_image = docker_image.strip()
        self.docker_bin = docker_bin
        self.docker_codex_bin = docker_codex_bin
        self.docker_gpus = docker_gpus.strip()

    async def run(self, *, instruction: str, user_text: str, cwd: Path) -> str:
        cwd.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(instruction, user_text)

        output_path = cwd / f".kaggleforge_codex_{uuid.uuid4().hex}.md"
        cmd = self._build_command(cwd=cwd, prompt=prompt, output_path=output_path)
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                env=self._build_env(),
            )
        except subprocess.TimeoutExpired as exc:
            output_path.unlink(missing_ok=True)
            raise TimeoutError("Codex call timed out") from exc

        stdout = completed.stdout
        stderr = completed.stderr
        self._print_codex_events(stdout)

        result = ""
        if output_path.exists():
            result = output_path.read_text(encoding="utf-8", errors="replace")
            output_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            detail = stderr.strip() or self._tail(stdout)
            raise RuntimeError(f"Codex failed with exit code {completed.returncode}: {detail}")

        return result.strip()

    def _build_command(self, *, cwd: Path, prompt: str, output_path: Path) -> list[str]:
        if self.sandbox_provider == "docker":
            return self._build_docker_command(cwd=cwd, prompt=prompt, output_path=output_path)
        if self.sandbox_provider != "local":
            raise RuntimeError(f"Unsupported Codex sandbox provider: {self.sandbox_provider}")
        return self._build_local_command(cwd=cwd, prompt=prompt, output_path=output_path)

    def _build_local_command(self, *, cwd: Path, prompt: str, output_path: Path) -> list[str]:
        codex_executable = shutil.which(self.codex_bin) or self.codex_bin
        if not Path(codex_executable).exists() and not shutil.which(codex_executable):
            raise RuntimeError(
                f"Codex executable not found: {self.codex_bin}. "
                "Set KAGGLEFORGE_CODEX_BIN in .env to the absolute codex.EXE path."
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

    def _build_docker_command(self, *, cwd: Path, prompt: str, output_path: Path) -> list[str]:
        if not self.docker_image:
            raise RuntimeError(
                "KAGGLEFORGE_CODEX_SANDBOX_PROVIDER=docker requires KAGGLEFORGE_CODEX_DOCKER_IMAGE in .env. "
                "The image must include an authenticated or API-key-configured Codex CLI."
            )
        docker_executable = shutil.which(self.docker_bin) or self.docker_bin
        if not shutil.which(docker_executable) and not Path(docker_executable).exists():
            raise RuntimeError(f"Docker executable not found: {self.docker_bin}")

        container_workspace = "/workspace"
        output_arg = f"{container_workspace}/{output_path.name}"
        codex_cmd = self._base_codex_command(
            codex_executable=self.docker_codex_bin,
            cwd_arg=container_workspace,
            output_arg=output_arg,
            prompt=prompt,
        )

        cmd = [
            docker_executable,
            "run",
            "--rm",
            "-v",
            f"{cwd.resolve()}:{container_workspace}",
            "-w",
            container_workspace,
        ]
        if self.docker_gpus:
            cmd.extend(["--gpus", self.docker_gpus])
        for name in self._docker_env_names():
            if os.environ.get(name):
                cmd.extend(["-e", name])
        cmd.append(self.docker_image)
        cmd.extend(codex_cmd)
        return cmd

    def _base_codex_command(
        self,
        *,
        codex_executable: str,
        cwd_arg: str,
        output_arg: str,
        prompt: str,
    ) -> list[str]:
        cmd = [
            codex_executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            self.sandbox,
            "--cd",
            cwd_arg,
            "-c",
            'shell_environment_policy.inherit="none"',
            "-c",
            'shell_environment_policy.include_only=["PATH","HOME","TMPDIR"]',
            "--output-last-message",
            output_arg,
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
                "# KaggleForge Runtime",
                "You are running through the Codex CLI.",
                "Legacy in-process tool calling is not available.",
                "Use the current working directory as the research session directory.",
                "Useful files may include source.md, competition.json, task.md, calibration.md, strategy.md, plan_tree.json, plan_list.json, tasks/, verifications/, artifacts/, evaluation.json, results_summary.md, and paper.md.",
                "Use shell/Python commands and file inspection when useful, then produce a concise final answer.",
                "Do not ask for human input. Complete the requested node directly.",
                "# User Task",
                user_text.strip(),
            ]
        )

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        helper_dir = self._find_windows_sandbox_helper_dir()
        if helper_dir:
            current_path = env.get("PATH") or env.get("Path") or ""
            path_key = "Path" if "Path" in env else "PATH"
            helper_path = str(helper_dir)
            parts = [part for part in current_path.split(os.pathsep) if part]
            if helper_path.lower() not in {part.lower() for part in parts}:
                env[path_key] = os.pathsep.join([helper_path, *parts])
        if not self.inherit_proxy:
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "no_proxy",
            ):
                env.pop(key, None)
        return env

    @staticmethod
    def _find_windows_sandbox_helper_dir() -> Path | None:
        if os.name != "nt":
            return None

        candidates: list[Path] = []
        user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
        vscode_extensions = user_profile / ".vscode" / "extensions"
        if vscode_extensions.exists():
            candidates.extend(
                sorted(
                    vscode_extensions.glob(
                        "openai.chatgpt-*/bin/windows-x86_64/codex-windows-sandbox-setup.exe"
                    ),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )
            candidates.extend(
                sorted(
                    vscode_extensions.glob(
                        "openai.chatgpt-*/bin/windows-x86_64/codex-resources/codex-windows-sandbox-setup.exe"
                    ),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )

        for helper in candidates:
            if helper.exists():
                return helper.parent
        return None

    def _docker_env_names(self) -> list[str]:
        names = [
            "CODEX_API_KEY",
            "OPENAI_API_KEY",
            "CODEX_HOME",
            "CODEX_CA_CERTIFICATE",
            "SSL_CERT_FILE",
        ]
        if self.inherit_proxy:
            names.extend([
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "no_proxy",
            ])
        return names

    def status(self) -> dict[str, str | bool]:
        if self.sandbox_provider == "docker":
            return self._docker_status()

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
                    encoding="utf-8",
                    errors="replace",
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
            "sandbox_provider": self.sandbox_provider,
            "model": self.model or "Codex default",
            "reasoning_effort": self.reasoning_effort or "Codex default",
            "verbosity": self.verbosity or "Codex default",
            "inherit_proxy": self.inherit_proxy,
            "error": error,
        }

    def _docker_status(self) -> dict[str, str | bool]:
        docker_path = shutil.which(self.docker_bin) or ""
        error = ""
        connected = False
        version = ""
        if not docker_path:
            error = f"Docker binary not found: {self.docker_bin}"
        elif not self.docker_image:
            error = "KAGGLEFORGE_CODEX_DOCKER_IMAGE is not set"
        else:
            try:
                result = subprocess.run(
                    [self.docker_bin, "run", "--rm", self.docker_image, self.docker_codex_bin, "--version"],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    env=self._build_env(),
                )
                connected = result.returncode == 0
                version = result.stdout.strip() or result.stderr.strip()
                if not connected:
                    error = result.stderr.strip() or result.stdout.strip()
            except Exception as exc:
                error = str(exc)
        return {
            "connected": connected,
            "codex_bin": self.docker_codex_bin,
            "path": docker_path,
            "version": version,
            "sandbox": self.sandbox,
            "sandbox_provider": self.sandbox_provider,
            "docker_image": self.docker_image,
            "model": self.model or "Codex default",
            "reasoning_effort": self.reasoning_effort or "Codex default",
            "verbosity": self.verbosity or "Codex default",
            "inherit_proxy": self.inherit_proxy,
            "error": error,
        }

    @staticmethod
    def _print_codex_events(stdout: str) -> None:
        for line in stdout.splitlines():
            CodexCliRuntime._print_codex_event_line(line)

    @staticmethod
    def _print_codex_event_line(line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
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
