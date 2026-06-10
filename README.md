## Files

- `db.py`: file-based session storage
- `stage.py`: stage lifecycle and status
- `stages.py`: refine, research, and write stages
- `orchestrator.py`: runs stages in order
- `agent_runtime.py`: chooses mock or Codex CLI for one workflow node
- `codex_runtime.py`: small non-interactive Codex CLI wrapper
- `config.py`: minimal `.env` and environment-variable settings loader
- `main.py`: CLI entry point
