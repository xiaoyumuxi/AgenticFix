# 模型接入与最小自主循环

当前接入范围是非流式 OpenAI-compatible Chat Completions + Function Tool Calling。第一优先是 DeepSeek；其他服务使用同一个适配器和服务预设。不能据此宣称已经支持所有厂商的全部原生能力。

## DeepSeek 配置

在本地 `.env` 中添加或修改这些字段，保留已有目录配置：

```dotenv
AGENTICFIX_MODEL_PROVIDER=deepseek
AGENTICFIX_MODEL_NAME=deepseek-flash
AGENTICFIX_MODEL_API_KEY=在本地填写自己的密钥
```

不要把密钥提交到 Git 或复制到构建记录。没有密钥时 `run` 会在创建工作区和请求模型前报出配置提示。程序不会购买额度或切换到其他账号。

```bash
uv sync --locked
uv run python main.py run
```

`run` 不带仓库参数时使用内置 Calculator。与 `demo` 的区别是，搜索、阅读、编辑及测试动作由模型生成，生产代码中没有针对 Calculator 的预设修复动作。初始公开测试和结束检查由 Runtime 执行。

结果包含状态、停止原因、Token 计数、模型请求次数、工具调用次数、耗时、Patch 路径与保留工作区。`completed / public_tests_passed` 只表示当前候选 Patch 通过配置的公开测试，不表示已通过独立隐藏验收。

## 服务预设

除 DeepSeek 外，必须显式设置账号可用的模型名。切换服务时同时更新模型和密钥；不会自动用 DeepSeek 密钥试探其他服务。

| provider | 默认 base_url | 默认输出 Token 参数 | 范围 |
| --- | --- | --- | --- |
| deepseek | https://api.deepseek.com | max_tokens | 默认模型 deepseek-flash，保留 reasoning_content |
| openai | https://api.openai.com/v1 | max_completion_tokens | Chat Completions；不覆盖仅支持 Responses API 的模型 |
| gemini | https://generativelanguage.googleapis.com/v1beta/openai | max_tokens | 官方兼容端点，保留工具扩展字段 |
| qwen | https://dashscope.aliyuncs.com/compatible-mode/v1 | max_tokens | 默认北京地址，需按密钥地域/业务空间覆盖 |
| claude | https://api.anthropic.com/v1 | max_tokens | 官方兼容层；不是原生 Messages API 完整适配 |
| compatible | 必须显式设置 | max_tokens | 自定义兼容网关或本地服务，需支持工具调用 |

覆盖地址示例：

```dotenv
AGENTICFIX_MODEL_PROVIDER=compatible
AGENTICFIX_MODEL_NAME=服务实际提供的模型名
AGENTICFIX_MODEL_BASE_URL=http://localhost:8000/v1
AGENTICFIX_MODEL_API_KEY=本地服务要求的值
```

仅回环地址允许 HTTP；其他地址要求 HTTPS。base_url 不接受嵌入的账号、密码或查询参数；不能填写到 `/chat/completions` 这一层。不跟随重定向，以免认证信息被意外转发。

`compatible` 允许适配其他网关，但未做其线上认证；模型必须支持标准函数工具调用。Gemini、Qwen、Claude 的模型能力和兼容限制仍以服务文档为准。

## 思考模式和可选参数

DeepSeek 思考模式产生的 `reasoning_content` 与原始 assistant 工具调用一起保留在后续请求中，不自行删除或改写。Gemini 等服务返回的工具扩展字段也保留。

按模型能力设置额外请求字段，例如 DeepSeek：

```dotenv
AGENTICFIX_MODEL_EXTRA_BODY={"thinking":{"type":"enabled"},"reasoning_effort":"low"}
AGENTICFIX_MAX_COMPLETION_TOKENS=8192
```

如需关闭 DeepSeek 思考模式：

```dotenv
AGENTICFIX_MODEL_EXTRA_BODY={"thinking":{"type":"disabled"}}
```

额外字段不能覆盖 model、messages、tools、tool_choice、stream、n 或 Token 上限。不要把一个厂商专有的字段直接用于另一厂商；不存在自动兼容所有参数的假设。

需要组织、项目或 Claude 工作区请求头时：

```dotenv
AGENTICFIX_MODEL_EXTRA_HEADERS={"anthropic-workspace-id":"你的工作区标识"}
```

允许的额外请求头只有 `anthropic-workspace-id`、`openai-organization`、`openai-project`、`http-referer`、`x-title`。认证头始终由适配器生成。头值使用 SecretStr，Trace 会遮盖已配置值。

## 本地可信仓库

```bash
uv run python main.py run --repo /absolute/path/to/repo --issue-file /absolute/path/to/issue.md --trusted-local
```

可选 `--ref <commit-or-ref>` 和 `--keep-worktrees`。输入必须是本地 Git 仓库；运行前解析固定 commit，不带入未提交文件。测试默认使用当前 uv 环境的 `python -m pytest -q`，自定义项目的依赖需要预先准备。

当前没有 Docker；`--trusted-local` 表示调用方确认仓库代码可信，不构成安全隔离。暂不提供对任意 GitHub URL 自动下载并在宿主机执行的入口。

## 运行规则与预算

- 开始时运行默认公开测试基线；模型通过结构化工具调用获取证据和修改代码。
- 多个工具调用顺序执行，每个分别计数；无效 JSON 也消耗工具预算。
- 同一代码版本上重复相同动作超过阈值会停止；正常编辑后允许再次读取和测试。
- 普通最终回复是结束申请。Runtime 重新运行默认测试、检查当前代码版本及非空 Patch；不满足时把结果反馈给模型继续处理。
- `length`、内容过滤等不完整响应不会执行其中的工具调用。
- 模型超时、连接错误、429 和 5xx 有限重试；400、401、403 等直接记录失败，不跨服务自动重试。
- 预算耗尽、模型失败或取消后尽可能保留 Patch、对话和现场。Trace 写入失败不会伪装成成功。

| 配置（均加 AGENTICFIX_ 前缀） | 默认值 |
| --- | --- |
| MAX_ITERATIONS | 30（每个模型请求尝试都计数） |
| MAX_TOOL_CALLS | 60（包括 Runtime 的基线和结束验证） |
| MAX_TOKEN_BUDGET | 100000 |
| MAX_COMPLETION_TOKENS | 4096 |
| MAX_RUN_DURATION | 600 秒 |
| MODEL_TIMEOUT | 90 秒 |
| MAX_MODEL_RETRIES | 2（首次失败后的额外次数） |
| RETRY_DELAY | 1 秒，指数递增 |
| MAX_CONTEXT_BYTES | 150000 |
| MAX_TOOL_MESSAGE_CHARS | 12000 |
| MAX_REPEATED_ACTIONS | 3 |

每次模型请求前按请求 UTF-8 字节数加固定开销预留输入预算，并限制输出 Token。收到可靠 usage 后按服务报告结算；没有 usage、请求失败或中途取消时保留估算，单独记录 `reported_tokens`、`estimated_tokens`、`unknown_usage_requests`，绝不按零费用处理。

这些是本地预算控制，不是账单金额保证。字节估算较保守；服务 tokenizer、额外计费项和失败请求费用可能不同。总时限约束异步模型/测试流程；同步 Git 元数据操作仍受各自命令超时约束，清理与产物保存可能使实际耗时超过设置值。

当前不做复杂上下文压缩：工具输出会缩短给模型的预览，原始有界结果仍在 Trace 中；整个上下文超过上限时明确停止，避免剪掉必要的 reasoning_content 或未配对的工具消息。

## 验证状态

离线测试使用 HTTP MockTransport 和确定性模型响应，覆盖请求/响应协议、六种配置、扩展字段回传、错误分类、预算、失败后重试、真实工具链和产物。它们不证明真实模型能解决 Issue。

当前开发环境未配置模型密钥，未执行真实 DeepSeek 或其他厂商请求。线上联调和真实 Issue 成功率保持待验证状态，配置密钥后用 `run` 获取实际 Trace 再分析。

## 官方接口依据

核对日期：2026-09-14。

- [DeepSeek 首次调用与当前模型名](https://api-docs.deepseek.com/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Thinking Mode 与多轮 reasoning_content](https://api-docs.deepseek.com/guides/thinking_mode/)
- [Gemini OpenAI 兼容接口](https://ai.google.dev/gemini-api/docs/openai)
- [Qwen 各地域与业务空间 Base URL](https://help.aliyun.com/zh/model-studio/base-url)
- [Claude OpenAI SDK 兼容层及限制](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk)
