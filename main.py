from __future__ import annotations

import asyncio
import sys

from orchestrator import Orchestrator


async def main() -> None:
    idea = " ".join(sys.argv[1:]).strip()
    if not idea:
        idea = input("Research idea: ").strip()
    if not idea:
        raise SystemExit("Research idea cannot be empty.")

    orchestrator = Orchestrator()
    session_dir = await orchestrator.start(idea)
    print(f"\nDone. Results saved to: {session_dir}")


if __name__ == "__main__":
    asyncio.run(main())
