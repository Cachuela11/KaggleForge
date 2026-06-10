# MLforge

A minimal, runnable skeleton inspired by MAARS.

It keeps the core architecture:

```text
idea -> refine -> research -> write -> results/<session_id>/
```

No web UI, no LangGraph, and no external Python dependencies yet. The default
runtime is simulated so the whole pipeline can run locally first. You can also
switch the same skeleton to Codex CLI.

## Run

```bash
python main.py "Study whether small learning-rate warmups improve toy model stability"
```

Or run it interactively:

```bash
python main.py
```

Outputs are written under `results/<session_id>/`.

## Run With Codex CLI

Install and authenticate Codex CLI first, then run:

```bash
MLFORGE_RUNTIME=codex python main.py "Study whether small learning-rate warmups improve toy model stability"
```

On PowerShell:

```powershell
$env:MLFORGE_RUNTIME="codex"
python main.py "Study whether small learning-rate warmups improve toy model stability"
```

Optional configuration:

- `MLFORGE_CODEX_BIN`: Codex executable, default `codex`
- `MLFORGE_CODEX_MODEL`: model override, default empty
- `MLFORGE_CODEX_REASONING_EFFORT`: e.g. `low`, `medium`, `high`, `xhigh`
- `MLFORGE_CODEX_SANDBOX`: default `workspace-write`
- `MLFORGE_CODEX_TIMEOUT`: seconds, default `1800`

You can put these values in `.env`; see `.env.example`.

## Files

- `db.py`: file-based session storage
- `stage.py`: stage lifecycle and status
- `stages.py`: refine, research, and write stages
- `orchestrator.py`: runs stages in order
- `agent_runtime.py`: chooses mock or Codex CLI for one workflow node
- `codex_runtime.py`: small non-interactive Codex CLI wrapper
- `config.py`: minimal `.env` and environment-variable settings loader
- `main.py`: CLI entry point
