from __future__ import annotations

from pathlib import Path

from config import settings
from codex_runtime import CodexCliRuntime


async def agent(system_prompt: str, user_text: str, *, cwd: Path) -> str:
    """Run one workflow node as an agent call.

    Stages call this function instead of talking to Codex directly.

    In mock mode, it returns deterministic fake text so the pipeline can be
    tested cheaply.

    In codex mode, it creates a CodexCliRuntime and delegates this single node to
    `codex exec`. The stage receives only the final text result and decides where
    to save it.
    """

    runtime = settings.runtime.lower()
    if runtime == "codex":
        codex = CodexCliRuntime(
            codex_bin=settings.codex_bin,
            model=settings.codex_model,
            reasoning_effort=settings.codex_reasoning_effort,
            verbosity=settings.codex_verbosity,
            sandbox=settings.codex_sandbox,
            timeout=settings.codex_timeout,
            inherit_proxy=settings.codex_inherit_proxy,
        )
        return await codex.run(
            instruction=system_prompt,
            user_text=user_text,
            cwd=cwd,
        )

    return (
        f"{system_prompt.strip()}\n\n"
        "Generated from input:\n"
        f"{user_text.strip()}\n"
    )


def codex_status() -> dict[str, str | bool]:
    codex = CodexCliRuntime(
        codex_bin=settings.codex_bin,
        model=settings.codex_model,
        reasoning_effort=settings.codex_reasoning_effort,
        verbosity=settings.codex_verbosity,
        sandbox=settings.codex_sandbox,
        timeout=settings.codex_timeout,
        inherit_proxy=settings.codex_inherit_proxy,
    )
    return codex.status()
