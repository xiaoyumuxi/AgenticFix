# 第一阶段构建记录

> 阶段：Milestone 1 — Foundation + Worktree + Repository Tools  
> 创建日期：2026-09-14  
> 当前状态：待实现，已完成架构规划与仓库初始化  
> 架构依据：[Agent.md](../Agent.md) 第 3、7、8、16、31、43 节

本文记录第一阶段的构建计划、实施进度、验证证据和遗留问题。计划项不代表已实现；每次开发后更新对应状态和实际结果。架构约束以 `Agent.md` 为准，调整范围时同步更新两份文档。

## 1. 阶段目标

建立一个不依赖 LLM、可以独立测试的仓库操作基础：

```text
准备可信示例 Git 仓库
→ 固定 base_commit
→ 创建独立 detached worktree
→ 通过工具浏览、搜索和读取代码
→ 精确修改文件
→ 在 LocalSandbox 运行测试
→ 导出候选 Patch
→ 在另一个干净 worktree 验证应用和测试
→ 保存 Trace、结果与 Patch
```

本阶段证明工作区、工具和产物链路正确；不宣称具备自主修复能力，也不以 Calculator 的结果代表真实 Issue 成功率。

## 2. 范围与约束

本阶段包括：

- Python 3.12+ 项目配置、依赖声明、pytest、ruff 和基础配置加载。
- AgentState、工具输入输出模型、BaseTool、ToolRegistry。
- 仓库缓存、固定 commit、任务 worktree 创建与清理。
- 六个工具：list_files、read_file、search_code、edit_file、run_tests、git_diff。
- 仅用于自有可信示例的 LocalSandbox。
- 追加写入的 events.jsonl、运行结果、测试日志和 final.patch。
- Calculator 示例、单元测试和完整工具链集成验证。

本阶段不包括 LLM 调用、自主 Loop、LangGraph、MCP、Embedding、FastAPI、UI 和正式隐藏测试评测。真实外部仓库代码执行必须等待 DockerSandbox；当前的干净 worktree 验证只是基础链路检查。

## 3. 已确定的设计

| 项目 | 约定 |
| --- | --- |
| 仓库组织 | 每个仓库一份缓存，每次运行一个 detached worktree |
| 版本基准 | 创建工作区前解析并记录不可变的 base_commit |
| 运行标识 | task_id 表示任务，run_id 表示一次尝试 |
| 用户文件 | 不带入用户原仓库未提交修改，不直接修改原工作目录 |
| Git 权限 | 工作区模块管理共享 Git 元数据，模型工具不直接操作它 |
| 路径边界 | Runtime 注入工作区根目录；检查绝对路径、父目录穿越和符号链接逃逸 |
| 修改方式 | 第一版只支持已有文件的唯一精确替换，检查已读取版本 |
| 测试配置 | 调用方选择预配置测试目标，Runtime 约束具体命令和最大超时 |
| 测试状态 | 成功编辑递增 workspace_revision，测试记录 tested_revision；旧测试不能验证新修改 |
| 错误语义 | 测试断言失败是测试结果，不能直接算作工具执行故障 |
| Patch | 相对 base_commit 导出，覆盖新增、修改、删除及必要的二进制变更 |
| 运行产物 | Trace、测试日志、结果和 Patch 保存在 worktree 外部 |
| 清理策略 | 使用 Git worktree 管理命令清理；保留失败现场时记录路径 |

Patch 导出的新增、删除及二进制能力由独立测试夹具验证，不意味着第一版 edit_file 已经支持创建、删除文件。产物排除规则应明确，不能静默丢弃源码变更。

## 4. 构建步骤与进度

按依赖顺序执行，每一步完成后记录实际改动、验证结果和提交。不要提前创建后续阶段的空模块。

| 步骤 | 工作内容 | 主要计划文件 | 状态 |
| --- | --- | --- | --- |
| 0 | 架构规划、Git 初始化、创建并推送 GitHub 仓库 | Agent.md、.gitignore | 已完成 |
| 1 | 项目配置、开发命令、配置模型与最小入口 | pyproject.toml、config.py、.env.example、main.py | 待实现 |
| 2 | 状态、工具协议、参数校验、注册与错误分发 | agent/state.py、tools/base.py、tools/registry.py | 待实现 |
| 3 | 最小事件 Trace 与运行产物目录 | tracing/models.py、tracing/tracer.py | 待实现 |
| 4 | 仓库准备、worktree 生命周期、Patch 导出 | workspace/repository.py | 待实现 |
| 5 | 列目录、按行读取、搜索与精确编辑 | tools/file_tools.py、tools/search_tools.py | 待实现 |
| 6 | LocalSandbox、测试工具、Diff 工具 | sandbox/base.py、sandbox/local.py、tools/test_tools.py、tools/git_tools.py | 待实现 |
| 7 | Calculator、完整链路验证和使用说明 | examples/calculator/、tests/、scripts/、README.md | 待实现 |

文件清单是实施计划，具体新增文件在每次开发前说明；保持 Agent.md 中的模块边界。

## 5. 接口落实清单

以下是待实现的接口约定，不是现有 API 文档。实现后补充准确类型、默认值、错误码和调用示例。

| 接口 | 输入要点 | 输出与行为 |
| --- | --- | --- |
| prepare_repository | 仓库来源、ref | 缓存位置、解析后的 base_commit |
| create_workspace | 缓存、base_commit、run_id | 独立工作区路径、运行身份 |
| export_patch | 工作区、base_commit、产物位置 | 完整 Patch、变更文件记录 |
| cleanup_workspace | 运行工作区、保留策略 | 清理或保留结果，不影响其他任务 |
| list_files | 相对目录、max_depth | 有界文件列表，忽略 Git 元数据及依赖目录 |
| read_file | path、start_line、end_line | 带行号内容、读取版本、截断标记 |
| search_code | query、file_pattern、max_results | 文件、行号、片段，结果有上限 |
| edit_file | path、old_text、new_text、读取版本凭据 | 唯一匹配后修改，记录新版本和变更 |
| run_tests | 预配置目标、受限 timeout | stdout、stderr、exit_code、duration、tested_revision |
| git_diff | 当前运行上下文 | 相对基准的候选变更，复用统一 Patch 逻辑 |

ToolResult 区分 success、结构化 data、error_code、error 和 truncated。预期可恢复错误转成工具结果；不可恢复错误由上层终止运行并尽量保存现场，不把所有异常吞掉后继续执行。

工作区边界和执行器属于 Runtime 提供的上下文，不能作为模型可随意修改的参数。

## 6. 验收清单

### 工程基础

- [ ] 按说明可以安装依赖并执行最小入口。
- [ ] 重要接口有类型定义，配置错误有明确提示。
- [ ] 完整 pytest 通过，ruff 通过。
- [ ] .env、缓存、worktree、日志等不进入 Git 提交。

### 工作区与 Patch

- [ ] 从固定 commit 创建 detached worktree，不改变源仓库的工作文件。
- [ ] 两个 worktree 对同一路径的修改互不影响。
- [ ] 创建失败、重复 run_id、清理失败有明确结果。
- [ ] 共享缓存和 worktree 元数据操作有协调机制及相应验证。
- [ ] Patch 覆盖新增、修改、删除和必要的二进制变更。
- [ ] Patch 可应用到同一基准的干净 worktree，应用后的内容符合预期。
- [ ] 清理不删除其他任务工作区；保留现场时产物可定位。

### 文件与测试工具

- [ ] 拒绝目录穿越、工作区外绝对路径和符号链接逃逸，保护 Git 元数据。
- [ ] 读取、目录遍历、搜索输出均有边界，正确标记截断。
- [ ] 精确编辑在零匹配、多匹配和文件版本过期时拒绝写入。
- [ ] 无效参数、文件不存在、编码或文件类型不支持等情况有明确错误结果。
- [ ] 测试成功、断言失败、无测试收集、进程启动失败和超时能区分。
- [ ] 测试超时终止本次执行及其子进程，保留已获取的输出。
- [ ] 测试后再次编辑会使旧验证结论失效。

### Trace 与完整链路

- [ ] 工具调用记录 run_id、时间、参数、结果、耗时和错误，敏感配置不进入日志。
- [ ] Trace 追加落盘，中途失败仍可查看已完成步骤。
- [ ] Calculator 的目标问题在修改前失败，通过工具修改后测试通过。
- [ ] 将导出的 Patch 应用到干净 worktree 后，相同测试仍然通过。
- [ ] 最终保存结果、实际测试证据、Patch 和已知限制。

## 7. 构建记录

### 2026-09-14 — 规划与仓库准备

- 完成 Agent.md 架构更新，确定 worktree、独立验收与五个里程碑。
- 初始化本地 Git 仓库，创建私有仓库 [xiaoyumuxi/AgenticFix](https://github.com/xiaoyumuxi/AgenticFix)，默认分支 main。
- 已推送规划提交：`5e2d8c7`，`docs: define AgenticFix architecture and worktree workflow`。
- 创建本构建记录，拆分第一阶段任务和验收清单。
- 当前业务代码、依赖配置、自动化测试均未实现；尚无 pytest 或 ruff 执行结果。

### 后续记录格式

每次完成一项构建工作后追加：

```text
日期 / 工作项：
状态：进行中 / 已完成 / 阻塞
实际改动：
涉及文件：
验证命令与实际结果：
提交（如有）：
已知问题与下一步：
```

## 8. 实施时需要落实的细节

- 固定包管理和类型检查工具，补充准确开发命令；沿用 Python、Pydantic、pytest、ruff 技术路线。
- 明确缓存、worktree、运行产物的默认目录和保留期限。
- 明确并发元数据操作的锁范围及故障恢复行为。
- 明确 Patch 排除规则、二进制处理和文件模式变更行为。
- 定义读取版本凭据及测试配置格式，避免用自由文本结果驱动状态更新。

上述事项属于本阶段实现细节，开发时记录选择与原因；涉及核心架构或范围改变时先讨论。

## 9. 阶段完成与交接

全部必要验收项通过后，将当前状态改为“已完成”，补充实际目录、工具接口、测试命令及结果、已知限制和交付提交。

完成 Milestone 1 后停止扩展功能，等待确认再进入 Milestone 2。下一阶段在这些工具之上接入模型适配器和自主 Loop，不提前实现后续集成。
