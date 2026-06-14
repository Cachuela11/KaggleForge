# MLforge

## 总目标

MLforge 目标是构建一个面向 Kaggle / 机器学习竞赛的多阶段 agent 系统。

用户输入 Kaggle competition URL 后，系统自动完成：

```text
Kaggle URL
-> 读取竞赛信息与数据文件
-> 生成 task.md
-> calibration
-> strategy / decompose / execute / verify / evaluate
-> 保存 artifacts
-> 生成最终 report
```

MLforge 自己负责 workflow 编排、文件状态管理、前端展示和阶段推进；具体 agent 节点通过一次 Codex CLI 调用完成，并把结果写回当前 session 目录。

## 核心结构

- `main.py`: CLI 入口。
- `server.py`: FastAPI 后端，提供 API、SSE 和前端静态页面服务。
- `orchestrator.py`: pipeline 调度器。
- `stage.py`: stage 生命周期与事件发送。
- `stages/intake.py`: Kaggle 读取、`task.md`、`calibration.md`。
- `stages/research.py`: strategy、decompose、execute、verify、evaluate。
- `db.py`: 文件型 session 存储，结果写入 `results/<date>-<competition>/`。
- `agent_runtime.py`: agent 调用入口。
- `codex_runtime.py`: Codex CLI 调用封装。
- `frontend/`: 原生 HTML / CSS / JS 前端。

## 2026-06-14 进展

今天主要完成了前端接入和前后端通信闭环。

新增前端：

- `frontend/index.html`: 页面结构。
- `frontend/styles.css`: 页面样式。
- `frontend/app.js`: 前端交互逻辑。

前端目前可以输入 Kaggle URL、启动 pipeline、查看运行日志、查看 session 文件、plan、tasks 和 artifacts。

后端新增 `server.py`，使用 FastAPI + Uvicorn 提供服务：

```text
frontend/app.js
-> POST /api/pipeline/start
-> server.py
-> Orchestrator.start()
-> Stage.run()
-> stage.emit()
-> Orchestrator.broadcast()
-> GET /api/events
-> frontend/app.js 更新页面状态
```

前端不直接调用 Codex，也不直接读写文件。前端只和 FastAPI 通信；FastAPI 调 orchestrator；orchestrator 调 stage；stage 再通过 agent runtime 调 Codex CLI。

今天也确认了 Codex 运行方式：

- Docker provider 会受容器网络影响，当前不适合作为默认调试方式。
- Local provider 更适合当前开发，使用宿主机 Codex CLI，并保留 `workspace-write` sandbox。
- 如果 Codex CLI 网络超时，需要在当前 PowerShell 设置代理后再运行。

当前推荐配置：

```env
MLFORGE_RUNTIME=codex
MLFORGE_CODEX_SANDBOX_PROVIDER=local
MLFORGE_CODEX_SANDBOX=workspace-write
```

另外修复了 Windows + Uvicorn 下调用 Codex 子进程的问题：将 `asyncio.create_subprocess_exec` 改为 `asyncio.to_thread(subprocess.run, ...)`，避免前端运行时报 `NotImplementedError`。
