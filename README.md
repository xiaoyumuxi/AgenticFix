# AgenticFix

给定 GitHub 仓库与 Issue，逐步构建能够读取代码、定位问题、修改代码、运行测试、根据反馈继续修复并生成 Patch 的 Agent。

**已实现 worktree、模型 Loop、模型编写 Dockerfile 与首个真实历史 Issue 的独立验收。** `demo` 保留预先编排的工具验证，`run` 使用模型选择动作。首次真实 DeepSeek 示例修复与干净工作区验证已通过；更多真实任务效果仍待评测。完整架构见 [AGENTS.md](AGENTS.md)，实施记录见 [第一阶段构建记录](docs/milestone-1.md)。

## 架构

```text
宿主机配置 → Agent Runtime / 可信演示脚本
    ├── AgentState：代码版本、测试状态、停止原因
    ├── ToolRegistry：参数校验、串行执行、错误处理、Trace
    │     ├── list_files / read_file / search_code / edit_file
    │     ├── build_environment → DockerSandbox（模型编写 Dockerfile）
    │     ├── run_tests → DockerSandbox / LocalSandbox（后者只运行可信示例）
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

## 首个真实 Issue：环境也由模型构建

任务为 [more-itertools #1152](https://github.com/more-itertools/more-itertools/issues/1152)，固定修复前 commit，模型读取声明并编写 Dockerfile、安装 pytest、构建、修改源码。独立评测恢复原测试，加上运行前冻结的 14 项验收，验证 base、官方源码修复与候选 Patch。

| 运行 | 提示词 / 读取上限 | 服务报告 Token | 独立验证：base → 候选 | Agent 结果 |
| --- | --- | ---: | --- | --- |
| RUN-20260914-004 | v1 / 400 行 | 98,264 | 7失败/722通过 → 729通过 | token_budget，失败 |
| RUN-20260914-005 | v2 / 400 行 | 98,113 | 7失败/722通过 → 729通过 | token_budget，失败 |
| RUN-20260914-006 | v2 / 80 行 | 119,879 | 7失败/722通过 → 729通过 | token_budget，失败 |
| RUN-20260914-007 | 同006，成功构建摘要 | 110,356 | 7失败/722通过 → 729通过 | token_budget，失败 |
| RUN-20260914-008 | 同007，保留最近3次读取正文 | 118,525 | 7失败/722通过 → 7失败/722通过 | token_budget，未编辑 |

前四次 Patch 均修好独立验收覆盖的行为，第五次未编辑；五次 Runtime 均未正常完成，端到端结果仍计失败。这是同一个 Issue 的五次实验，不是五个任务的成功率。模型环境都构建成功，尚未测试复杂依赖安装与构建失败后的真实模型恢复。

启动 Docker 并配置 DeepSeek 后，在干净工作区运行：

```bash
gh repo clone more-itertools/more-itertools .cache/m3-upstream -- --no-checkout
AGENTICFIX_ENVIRONMENT_PROMPT_VERSION=environment-v1 uv run python -m scripts.run_real_issue
```

脚本固定任务与 150,000 Token 等预算；失败仍保存 Patch 和独立报告。提示词 v2 与 80 行上限可通过环境变量选择，尚未设为默认。成功构建摘要（AGENTICFIX_COMPACT_SUCCESSFUL_BUILD=true）和读取保留（AGENTICFIX_RETAINED_READ_RESULTS=3）也仅作为实验选项，默认关闭；新增对照没有改善完成结果。实现与范围见 [第三阶段记录](docs/milestone-3.md)。详细逐轮数据、14 项实际值、版本和失败原因见 [AgenticFix‐7：Docker没有启动时如何留证，环境构建如何验收？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%907%EF%BC%9ADocker%E6%B2%A1%E6%9C%89%E5%90%AF%E5%8A%A8%E6%97%B6%E5%A6%82%E4%BD%95%E7%95%99%E8%AF%81%EF%BC%8C%E7%8E%AF%E5%A2%83%E6%9E%84%E5%BB%BA%E5%A6%82%E4%BD%95%E9%AA%8C%E6%94%B6%EF%BC%9F)、[AgenticFix‐8：Patch通过729项验证，为什么三轮仍然没有完成任务？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)。

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

## 使用 DeepSeek 运行 Agent

在本地 `.env` 添加模型配置，保留已有目录设置：

```dotenv
AGENTICFIX_MODEL_PROVIDER=deepseek
AGENTICFIX_MODEL_NAME=deepseek-flash
AGENTICFIX_MODEL_API_KEY=在本地填写密钥
```

```bash
uv run python main.py run
```

默认使用可信 Calculator，但修复动作由模型决定。支持 DeepSeek、OpenAI、Gemini、Qwen、Claude 的兼容层预设，以及自定义 OpenAI-compatible 地址；切换时修改 provider、model_name、api_key，必要时覆盖 base_url。

详细设置、其他服务的兼容范围和预算说明见 [模型接入说明](docs/models.md)，本轮进度见 [第二阶段构建记录](docs/milestone-2.md)。DeepSeek 已完成首次真实示例联调，[实测记录](docs/validation/deepseek-calculator.md)包含具体结果；其他服务尚未线上验证。

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

工具通过 `ToolRegistry.call(name, arguments)` 调用。参数使用 Pydantic 严格校验，拒绝未知字段；`registry.schemas()` 返回工具的 JSON Schema；Docker 模式额外注册 build_environment。

所有结果统一包含 `success`、`data`、`error_code`、`error`、`truncated`、`fatal`。工作区、执行器与权限由宿主机提供的 `ToolContext` 持有，不能通过工具参数替换。

| 工具 | 参数 | 主要输出 |
| --- | --- | --- |
| list_files | path="."、max_depth=3（0～20） | files；深度 0 只列当前目录文件 |
| read_file | path、start_line=1、end_line=null | 带行号 content、SHA-256 version、total_lines |
| search_code | query、file_pattern="*"、max_results=50（1～1000） | matches：file、line、snippet；skipped_files |
| edit_file | path、old_text、new_text、version | path、workspace_revision |
| run_tests | target="default"、timeout=60 | stdout、stderr、exit_code、duration、status、tested_revision、artifact |
| git_diff | 无参数 | base_commit、patch_path、有界 preview |
| build_environment（Docker 模式） | dockerfile | 构建日志、退出码、镜像 ID、依赖环境 |

编辑前必须读取对应文件，并传回该次读取的 `version`。只支持 UTF-8 已有文件的唯一精确替换；保持文件权限和原有换行。缺失匹配、多处匹配、过期读取、无变化替换和超限修改均拒绝。

测试目标是宿主机预配置的 argv 元组，不接受自由 shell。退出码语义按 pytest 定义：0 通过、1 断言失败、2 中断、3 pytest 内部错误、4 使用错误、5 未收集测试。断言失败与未收集测试属于有效工具结果，但不等于验证成功。超时或启动失败返回工具失败。

测试前后比较 Patch 摘要，测试执行期间源码发生变化会标记 `workspace_changed`。工具编辑或导出时发现公开测试之后又发生修改，会使旧结论失效。此检查不是对恶意并发写入的安全保证。

## 边界与限制

- **LocalSandbox 不是安全隔离环境。** 仅限可信测试代码；worktree 也不能阻止进程访问宿主机。真实项目必须通过 DockerSandbox 执行。
- 测试子进程仅继承少量运行环境变量，不继承模型密钥；输出超过上限会截断，日志不保证包含完整超大输出。
- 文件工具拒绝越界、符号链接、硬链接、Git 元数据和环境文件。运行假设任务目录由 Runtime 独占；不提供抵御恶意并发文件替换的内核级保证。
- 仓库工具尚不支持子模块、LFS 内容处理、复杂 Git filter 和容器内 Git 元数据映射。避免把它用于这些仓库。
- Patch 包含所有已跟踪文件变更（即使路径匹配缓存目录）；未跟踪文件遵守 Git ignore，并额外排除 `.venv`、`__pycache__`、`.pytest_cache`、`.ruff_cache`、`.mypy_cache`、`node_modules`、`.DS_Store`。
- 第一版编辑工具不创建、删除文件；Patch 对新增和删除的支持通过独立夹具测试。
- Trace 遮盖敏感字段及显式传入的已知密钥，但不是通用秘密扫描器；不要把含密钥的仓库作为示例输入。
- 模型 Loop、预算和首个真实任务独立验收已实现；尚无自动 PR 或 API 服务。尚未建立多任务真实 Issue Benchmark。

## 下一阶段

接下来针对首个真实任务暴露的上下文累积和预算预留问题做单因素对照，再扩展带依赖安装的真实任务及构建失败恢复验证。


### 补充可信任务与运行证据

除 Calculator 外，已完成跨文件订单计价与区间边界处理两次真实 DeepSeek 运行，分别由 9 失败/4 通过变为 13 通过、11 失败/4 通过变为 15 通过。任务与独立测试均在运行前冻结，两次都是一次编辑成功。详见 [任务复现说明](docs/validation/trusted-tasks.md) 和 [AgenticFix-5：两件60元的商品为什么只算出68？DeepSeek的跨文件修复](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%905%EF%BC%9A%E4%B8%A4%E4%BB%B660%E5%85%83%E7%9A%84%E5%95%86%E5%93%81%E4%B8%BA%E4%BB%80%E4%B9%88%E5%8F%AA%E7%AE%97%E5%87%BA68%EF%BC%9FDeepSeek%E7%9A%84%E8%B7%A8%E6%96%87%E4%BB%B6%E4%BF%AE%E5%A4%8D)、[AgenticFix-6：区间合并的四处边界问题，DeepSeek一次修改修好了哪些？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%906%EF%BC%9A%E5%8C%BA%E9%97%B4%E5%90%88%E5%B9%B6%E7%9A%84%E5%9B%9B%E5%A4%84%E8%BE%B9%E7%95%8C%E9%97%AE%E9%A2%98%EF%BC%8CDeepSeek%E4%B8%80%E6%AC%A1%E4%BF%AE%E6%94%B9%E4%BF%AE%E5%A5%BD%E4%BA%86%E5%93%AA%E4%BA%9B%EF%BC%9F)。

运行开始自动保存版本/配置快照，结束保存测量摘要和产物 SHA-256；准备异常也会留存失败记录。已修复的记录缺陷见 [AgenticFix-3：仓库准备失败了，为什么没有留下错误记录？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%903%EF%BC%9A%E4%BB%93%E5%BA%93%E5%87%86%E5%A4%87%E5%A4%B1%E8%B4%A5%E4%BA%86%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E6%B2%A1%E6%9C%89%E7%95%99%E4%B8%8B%E9%94%99%E8%AF%AF%E8%AE%B0%E5%BD%95%EF%BC%9F)、[AgenticFix-4：服务返回了模型名称，为什么运行记录里没有？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%904%EF%BC%9A%E6%9C%8D%E5%8A%A1%E8%BF%94%E5%9B%9E%E4%BA%86%E6%A8%A1%E5%9E%8B%E5%90%8D%E7%A7%B0%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E8%BF%90%E8%A1%8C%E8%AE%B0%E5%BD%95%E9%87%8C%E6%B2%A1%E6%9C%89%EF%BC%9F)。这些可信示例不能代替真实 Issue Benchmark，也尚未观察到真实模型错误编辑后的恢复。

工程测试现为96通过、1跳过；已修复 pytest 导入安装副本配置的问题，证据见 [AgenticFix‐9：源码新增了配置，为什么pytest仍然说字段不存在？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%909%EF%BC%9A%E6%BA%90%E7%A0%81%E6%96%B0%E5%A2%9E%E4%BA%86%E9%85%8D%E7%BD%AE%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88pytest%E4%BB%8D%E7%84%B6%E8%AF%B4%E5%AD%97%E6%AE%B5%E4%B8%8D%E5%AD%98%E5%9C%A8%EF%BC%9F)。
