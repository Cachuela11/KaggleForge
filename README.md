## Files

- `db.py`: file-based session storage
- `stage.py`: stage lifecycle and status
- `stages.py`: intake, research, and report stages
- `orchestrator.py`: runs stages in order
- `agent_runtime.py`: chooses mock or Codex CLI for one workflow node
- `codex_runtime.py`: small non-interactive Codex CLI wrapper
- `kaggle_integration.py`: Kaggle competition URL parsing, metadata, and data download
- `config.py`: minimal `.env` and environment-variable settings loader
- `main.py`: CLI entry point
