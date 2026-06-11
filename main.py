from __future__ import annotations

import asyncio
import sys

from agent_runtime import codex_status
from codex_runtime import CodexCliRuntime
from config import PROJECT_ROOT, settings
from orchestrator import Orchestrator


async def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--check-codex":
        for key, value in codex_status().items():
            print(f"{key}: {value}")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--smoke-codex":
        codex = CodexCliRuntime(
            codex_bin=settings.codex_bin,
            model=settings.codex_model,
            reasoning_effort=settings.codex_reasoning_effort,
            verbosity=settings.codex_verbosity,
            sandbox=settings.codex_sandbox,
            timeout=settings.codex_timeout,
            inherit_proxy=settings.codex_inherit_proxy,
        )
        result = await codex.run(
            instruction="You are a health-check agent. Return exactly one short line.",
            user_text="Return exactly: MLFORGE_CODEX_OK",
            cwd=PROJECT_ROOT,
        )
        print(result)
        return

    idea = " ".join(sys.argv[1:]).strip()
    if not idea:
        idea = input("Research idea: ").strip()
    if not idea:
        raise SystemExit("Research idea cannot be empty.")

    orchestrator = Orchestrator()
    try:
        session_dir = await orchestrator.start(idea)
    except Exception as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(f"\nDone. Results saved to: {session_dir}")


if __name__ == "__main__":
    asyncio.run(main())
