# AgenticFix

给定 GitHub 仓库与 Issue，逐步构建能够读取代码、定位问题、修改代码、运行测试、根据反馈继续修复并生成 Patch 的 Agent。

**当前已完成 Milestone 1：基础设施、Git worktree、仓库工具和可信示例验证。** 当前演示是预先编排的工具调用，没有 LLM，没有自主定位能力，也不是独立隐藏测试评测。完整架构见 [Agent.md](Agent.md)，实施记录见 [第一阶段构建记录](docs/milestone-1.md)。

## 架构

```text
宿主机配置 / 脚本（后续替换为 Agent Runtime）
    ├── AgentState：代码版本、测试状态、停止原因
    ├── ToolRegistry：参数校验、串行执行、错误处理、Trace
    │     ├── list_files / read_file / search_code / edit_file
    │     ├── run_tests → LocalSandbox（只运行可信示例）
    │     └── git_diff → WorkspaceManager
    └── WorkspaceManager
          仓库缓存 → 每次运行的 detached worktree → 候选 Patch
                                                        │
                                   干净 worktree ← 应用并验证
```

每次运行固定 `base_commit`，不带入源仓库未提交修改。工作文件与 index 按 worktree 隔离，Git 对象共享。元数据操作使用文件锁；Patch 导出使用临时 index，避免修改任务的暂存状态。

## 验证与失败分析

工程测试覆盖工作区隔离、并发创建、路径与链接限制、精确编辑、异常处理、测试反馈、进程超时、Patch 新增/删除/二进制/文件权限及干净应用。

Calculator 包含五个公开测试：原始实现有两个失败，工具修改后五个通过，在另一份干净 worktree 应用 Patch 后五个通过。原始示例保留缺陷，每次演示从它创建新的 Git 仓库。

这只验证工具链路。后续真实 Issue 的成功标准是：独立 Issue 验证测试通过，并且选定的原始回归测试没有新增失败。有限测试不能证明绝对没有新问题。

每次工具调用追加记录开始、结束、参数、结果、耗时和错误。预期错误返回结构化结果；内部错误、隔离失效或 Trace 无法保存会停止运行。演示失败时保留工作区和尽可能导出的 Patch，记录 `result.json`。

## 快速开始

要求：macOS 或 Linux、Git、uv、Python 3.12+。当前进程组清理使用 POSIX API，不支持 Windows。执行下面命令的位置是本仓库根目录。

```bash
uv sync --locked --python 3.12
uv run python main.py demo
```

无需模型 API Key，无需 Docker。演示只执行项目内置的可信 Calculator，不接受外部仓库执行请求。

保留成功演示的两个 worktree 以便检查：

```bash
uv run python main.py demo --keep-worktrees
```

成功运行默认清理任务和验证 worktree；失败运行自动保留现场。仓库缓存、fixture 源仓库和运行产物保留到人工清理，没有后台过期删除。不要在任务运行中手工删除共享缓存。清理 worktree 应调用 `WorkspaceManager.cleanup_workspace()` 或对应 Git worktree 管理命令。

终端输出 JSON，包括基准版本、三次测试结果、Patch 和 Trace 的绝对路径。产物示例：

```text
runs/calculator-<id>/
├── fixture-source/       # 本次演示的初始 Git 仓库
├── events.jsonl          # 追加式工具事件
├── state.json            # 最新状态
├── test-5.json           # 修改前公开测试
├── test-7.json           # 修改后公开测试
├── final.patch
└── result.json           # 演示结果及清理/保留状态

runs/calculator-<id>-verify/
├── events.jsonl
├── state.json
└── test-1.json           # 干净工作区应用 Patch 后的测试
```

内部还有 Trace 锁文件和工作区快照 Patch。所有运行产物均在任务 worktree 外保存，并被本项目 `.gitignore` 排除。

## 开发检查

```bash
uv run pytest -q
uv run ruff check agent tools tracing workspace sandbox scripts tests examples config.py main.py
uv run ruff format --check agent tools tracing workspace sandbox scripts tests examples config.py main.py
uv run mypy
uv build
```

默认 pytest 只收集 `tests/`。直接运行 `examples/calculator` 的原始测试出现失败是示例设计，不是工程测试被跳过；集成测试会断言它在修复前失败、修复后成功。

## 配置

复制 `.env.example` 为 `.env` 后按需调整。未配置时使用以下默认值，目录相对执行命令时的工作目录解析。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| AGENTICFIX_CACHE_DIR | .cache/repositories | Git 仓库缓存及元数据锁 |
| AGENTICFIX_WORKTREE_DIR | .worktrees | 任务与验证 worktree |
| AGENTICFIX_RUNS_DIR | runs | Trace、结果和 Patch |
| AGENTICFIX_MAX_FILE_BYTES | 1048576 | 文本读取及编辑后的文件大小上限 |
| AGENTICFIX_MAX_READ_LINES | 400 | 单次读取行数上限 |
| AGENTICFIX_MAX_TEST_TIMEOUT | 60 | 单次测试时间上限（秒） |
| AGENTICFIX_MAX_OUTPUT_BYTES | 1048576 | 每个测试输出流和 Diff 预览的字节上限 |
| AGENTICFIX_MAX_ENTRIES | 2000 | 列目录与搜索返回数量上限 |
| AGENTICFIX_MAX_SCAN_ENTRIES | 20000 | 单次文件遍历的条目上限 |

搜索使用字面字符串匹配与文件 glob，不执行用户提供的正则或 shell。总扫描文本限制为 `MAX_FILE_BYTES × 20`，单条匹配片段最多 400 字符，截断或跳过文件时返回提示。

## 工具接口

工具通过 `ToolRegistry.call(name, arguments)` 调用。参数使用 Pydantic 严格校验，拒绝未知字段；`registry.schemas()` 返回六个工具的 JSON Schema。

所有结果统一包含 `success`、`data`、`error_code`、`error`、`truncated`、`fatal`。工作区、执行器与权限由宿主机提供的 `ToolContext` 持有，不能通过工具参数替换。

| 工具 | 参数 | 主要输出 |
| --- | --- | --- |
| list_files | path="."、max_depth=3（0～20） | files；深度 0 只列当前目录文件 |
| read_file | path、start_line=1、end_line=null | 带行号 content、SHA-256 version、total_lines |
| search_code | query、file_pattern="*"、max_results=50（1～1000） | matches：file、line、snippet；skipped_files |
| edit_file | path、old_text、new_text、version | path、workspace_revision |
| run_tests | target="default"、timeout=60 | stdout、stderr、exit_code、duration、status、tested_revision、artifact |
| git_diff | 无参数 | base_commit、patch_path、有界 preview |

编辑前必须读取对应文件，并传回该次读取的 `version`。只支持 UTF-8 已有文件的唯一精确替换；保持文件权限和原有换行。缺失匹配、多处匹配、过期读取、无变化替换和超限修改均拒绝。

测试目标是宿主机预配置的 argv 元组，不接受自由 shell。退出码语义按 pytest 定义：0 通过、1 断言失败、2 中断、3 pytest 内部错误、4 使用错误、5 未收集测试。断言失败与未收集测试属于有效工具结果，但不等于验证成功。超时或启动失败返回工具失败。

测试前后比较 Patch 摘要，测试执行期间源码发生变化会标记 `workspace_changed`。工具编辑或导出时发现公开测试之后又发生修改，会使旧结论失效。此检查不是对恶意并发写入的安全保证。

## 边界与限制

- **LocalSandbox 不是安全隔离环境。** 仅限可信测试代码；worktree 也不能阻止进程访问宿主机。真实项目执行等待 Docker 阶段。
- 测试子进程仅继承少量运行环境变量，不继承模型密钥；输出超过上限会截断，日志不保证包含完整超大输出。
- 文件工具拒绝越界、符号链接、硬链接、Git 元数据和环境文件。运行假设任务目录由 Runtime 独占；不提供抵御恶意并发文件替换的内核级保证。
- 仓库工具尚不支持子模块、LFS 内容处理、复杂 Git filter 和容器内 Git 元数据映射。避免把它用于这些仓库。
- Patch 包含所有已跟踪文件变更（即使路径匹配缓存目录）；未跟踪文件遵守 Git ignore，并额外排除 `.venv`、`__pycache__`、`.pytest_cache`、`.ruff_cache`、`.mypy_cache`、`node_modules`、`.DS_Store`。
- 第一版编辑工具不创建、删除文件；Patch 对新增和删除的支持通过独立夹具测试。
- Trace 遮盖敏感字段及显式传入的已知密钥，但不是通用秘密扫描器；不要把含密钥的仓库作为示例输入。
- 目前没有 Agent Loop、模型预算、隐藏评测、自动 PR 或 API 服务；不应把演示结果当成真实 Issue 修复率。

## 下一阶段

Milestone 2 在现有工具之上接入模型适配器、结构化 Tool Calling、手写 Loop、预算和测试反馈重试。同时准备首批真实历史 Issue 的复现环境和独立验收条件。
