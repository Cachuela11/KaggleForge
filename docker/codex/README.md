# MLforge Codex Docker Image

Build the local image:

```powershell
docker build -t mlforge-codex:latest -f docker/codex/Dockerfile .
```

Check that Codex exists inside the image:

```powershell
docker run --rm mlforge-codex:latest codex --version
```

Then set `.env`:

```env
MLFORGE_CODEX_SANDBOX_PROVIDER=docker
MLFORGE_CODEX_DOCKER_IMAGE=mlforge-codex:latest
MLFORGE_CODEX_DOCKER_CODEX_BIN=codex
```

The image installs Python ML dependencies plus Codex CLI. If Codex changes its
official install command, override the build arg:

```powershell
docker build -t mlforge-codex:latest -f docker/codex/Dockerfile --build-arg CODEX_INSTALL_COMMAND="your install command" .
```
