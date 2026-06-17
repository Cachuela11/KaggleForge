# KaggleForge

## 总目标

KaggleForge 目标是构建一个面向 Kaggle / 机器学习竞赛的多阶段 agent 系统。

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

KaggleForge 自己负责 workflow 编排、文件状态管理、前端展示和阶段推进；具体 agent 节点通过一次 Codex CLI 调用完成，并把结果写回当前 session 目录。

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
KAGGLEFORGE_RUNTIME=codex
KAGGLEFORGE_CODEX_SANDBOX_PROVIDER=local
KAGGLEFORGE_CODEX_SANDBOX=workspace-write
```

另外修复了 Windows + Uvicorn 下调用 Codex 子进程的问题：将 `asyncio.create_subprocess_exec` 改为 `asyncio.to_thread(subprocess.run, ...)`，避免前端运行时报 `NotImplementedError`。

## 2026-06-15 进展

今天主要补齐了最终 `report stage`：

- 将主流程扩展为 `intake -> research -> report`。
- `report stage` 会汇总 research 产物，生成 `report_context.json` 和 `report_context.md` 作为最终报告的事实包。
- 新增 Writer / Reviewer / Polish 三步：先写 `paper.md`，再审查生成 `report_review.json`，最后润色输出 `paper_polished.md`。
- 最终报告会追加 KaggleForge 执行记录，包含 session、任务数、验证通过数、artifact 数和关键文件清单。
- 前端 Docs 列表新增 report 相关文件，方便在网页中查看最终报告和审查结果。

Windows对Codex cli的适配太差了，windows sandbox有问题，codex启动本地powershell进程也有问题，只能在wsl的linux环境中启动，太麻烦了，目前准备换Mac电脑。

## 2026-06-16 进展

今天补齐了 research stage 中 execute agent 的 DAG 并行能力：

- 根据 `plan_list.json` 中的 `dependencies` 做拓扑分批。
- 同一批无依赖冲突的 execute task 会并行运行。
- 每个 task 使用独立 `workspaces/<task_id>/` 执行，避免并行写文件互相污染。
- task 的 `workspace/artifacts/` 会同步回 session 的 `artifacts/<task_id>/`，供 verify、report 和前端查看。后期考虑单次agent执行的衍生文件是不是要销毁，但销毁会失去可追溯性。
- 新增 `KAGGLEFORGE_API_CONCURRENCY` 控制最大并行数，默认 `3`。

## 2026-06-17 进展

今天主要完善了前端运行状态展示和配置可靠性：

- 前端新增 Stage / Agent 状态面板，展示 `intake / research / report` 和各 agent 节点的运行状态。
- SSE 事件现在会驱动前端实时更新 running / completed / failed，以及 execute 的 task、batch、attempt 信息。
- Session Docs 增加文件生成状态灯，已生成文件会高亮显示。
- 修复新一轮 pipeline 复用上一轮 completed 状态的问题。
- 修复 `.env` 带 BOM 导致 `KAGGLEFORGE_RUNTIME=codex` 读取失败、实际回退到 mock 的问题。
- 后端 runtime 状态现在会明确显示当前是 `codex` 还是 `mock`。
