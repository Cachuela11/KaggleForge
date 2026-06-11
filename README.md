## Files

- `db.py`: file-based session storage
- `stage.py`: stage lifecycle and status
- `stages.py`: refine, research, and write stages
- `orchestrator.py`: runs stages in order
- `agent_runtime.py`: chooses mock or Codex CLI for one workflow node
- `codex_runtime.py`: small non-interactive Codex CLI wrapper
- `kaggle_integration.py`: Kaggle competition URL parsing, metadata, and data download
- `config.py`: minimal `.env` and environment-variable settings loader
- `main.py`: CLI entry point

## Current Scope

MLforge currently implements the Kaggle-first refine path:

```text
Kaggle competition URL -> download/read competition metadata -> refined_idea.md
```

Run:

```bash
python main.py "https://www.kaggle.com/competitions/titanic"
```

The Kaggle API must be installed and authenticated. Data is downloaded under
`data/<competition-id>/`, and the refined brief is saved in the session as
`refined_idea.md`.

For Kaggle 2.x, put the API token in `.env`:

```env
MLFORGE_KAGGLE_API_TOKEN=your_kaggle_api_token
```

Older username/key style variables are still present for compatibility, but the
current Kaggle SDK authenticates with `KAGGLE_API_TOKEN`.
