# 第二阶段构建记录

创建日期：2026-09-14。状态：模型适配器与最小循环已实现，离线验证通过；首次真实 DeepSeek 示例修复及独立验证通过，更多任务验收待完成。

## 本次范围

按用户要求优先接入 DeepSeek，同时提供可配置的 OpenAI-compatible 适配器和常见服务预设。接入现有六个工具、worktree、公开测试与 Trace，形成最小自主循环。

不宣称覆盖所有厂商原生 API；不提前接入 LangGraph、Docker、隐藏评测、MCP 或 API 服务。

## 改动与设计

| 文件 | 职责 |
| --- | --- |
| agent/llm.py | LLMClient、结构化响应、DeepSeek 及兼容服务预设、有界 HTTP 请求 |
| agent/loop.py | Agent Loop、工具分发、预算、结束检查、失败与产物保存 |
| agent/prompts.py | 工具使用约束、先读后改、测试反馈、仓库文本不可信约束 |
| agent/runner.py | 运行配置、可信示例/本地仓库准备、客户端生命周期与清理 |
| agent/state.py | 模型调用计数、实际/估算 Token、时长与最终摘要 |
| config.py、.env.example | 服务、密钥、额外参数和预算配置 |
| main.py | 保留 demo，新增模型驱动 run 入口 |
| sandbox/local.py | 修复同秒等长修改复用过期 Python 字节码的问题 |
| tests/test_llm.py | HTTP 请求、响应与服务配置契约测试 |
| tests/test_agent_loop.py | 模型反馈、预算、重试及停止语义 |
| tests/test_agent_runner.py | 真实适配器到工具/worktree 的离线端到端验证 |
| docs/models.md | 配置、接口范围、命令、预算和验证限制 |

参数细节见 [模型接入说明](models.md)。DeepSeek 使用官方当前推荐的 `deepseek-flash`，允许显式替换模型名。Claude 仅使用官方兼容层，Gemini 仅使用兼容端点。

## 验收记录

- [x] 结构化 Function Tool Calling 接入现有工具，不从自由文本解析执行命令。
- [x] DeepSeek reasoning_content 和服务扩展字段在后续请求中保留。
- [x] 模型请求、单个工具调用、Token、运行时间与上下文上限。
- [x] 请求失败时保留未知用量估算，不记成零消耗。
- [x] 模型申请结束后重新执行默认公开测试并检查非空 Patch。
- [x] 离线测试覆盖修改失败、根据反馈继续修改及再次验证。
- [x] 配置/模型错误不暴露 API Key 或原始服务错误正文。
- [x] 完整 pytest：**78 passed**。
- [x] ruff check：通过；格式检查：**39 files already formatted**。
- [x] mypy 严格检查：**27 个源文件通过**。
- [x] `uv build`：sdist 与 wheel 构建成功。
- [x] 原 `main.py demo` 回归：基线 2 failed / 3 passed，修复后 5 passed，干净应用后 5 passed，无清理错误。
- [x] 真实 DeepSeek 联调：Calculator 修复通过，干净工作区的 29 项检查通过。
- [ ] 至少三个真实模型简单任务成功：已完成 1 个，另外 2 个待验证。
- [ ] 首批真实历史 Issue 复现与验收条件：后续准备，不属于此次模型协议接入结果。

## 开发发现

最初闭环测试出现同样源码已修改但 pytest 仍执行旧逻辑的情况。原因是 Python 对同秒、同长度源码可能复用旧 `.pyc`。修复为每次测试提供独立字节码查找前缀并禁止写入缓存，新增固定时间戳的回归测试。不是通过延迟测试或更换任务规避失败。

## Git 与配置记录

- `30cfc42`：修复旧字节码复用；同时保留工作区已有的 Agent.md → AGENTS.md 改名。
- `59c92eb`：DeepSeek 与兼容服务适配器、配置和 HTTP 契约测试。
- Loop、入口和离线集成测试以独立功能提交交付；最终说明和构建记录单独提交。
- 接入阶段仅追加了缺失配置位；用户随后完成本地密钥配置。`.env` 继续被 Git 忽略。
- 首次真实 DeepSeek 运行已完成，具体指标及验证范围见 [实测记录](validation/deepseek-calculator.md)，不据单次示例推导线上成功率。

## 交付边界

模型适配代码、离线验证及首次真实示例联调已完成。Milestone 2 还需补足更多任务、真实模型失败恢复案例及首批历史 Issue 的复现条件，之后进入 Docker 和独立 Eval。


## 2026-09-14 — 运行证据与补充任务

新增 tracing/evidence.py，运行开始自动采集版本/配置/环境，结束保存脱敏测量摘要和产物哈希。修复准备异常无失败记录、服务返回 model 字段丢失两项缺陷，受控前后证据归档到 BUG-20260914-002/003。

新增 order_total 和 intervals 两个可信任务，公开测试与独立验收测试在模型运行前冻结；执行方式与范围见 [任务说明](validation/trusted-tasks.md)。真实运行结果将在固定代码提交之后追加，不把尚未执行的任务写成通过。
