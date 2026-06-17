# KaggleForge Codex Docker Image

Build the local image:

```powershell
docker build -t kaggleforge-codex:latest -f docker/codex/Dockerfile .
```

Check that Codex exists inside the image:

```powershell
docker run --rm kaggleforge-codex:latest codex --version
```

Then set `.env`:

```env
KAGGLEFORGE_CODEX_SANDBOX_PROVIDER=docker
KAGGLEFORGE_CODEX_DOCKER_IMAGE=kaggleforge-codex:latest
KAGGLEFORGE_CODEX_DOCKER_CODEX_BIN=codex
```

The image installs Python ML dependencies plus Codex CLI. If Codex changes its
official install command, override the build arg:

```powershell
docker build -t kaggleforge-codex:latest -f docker/codex/Dockerfile --build-arg CODEX_INSTALL_COMMAND="your install command" .
```
