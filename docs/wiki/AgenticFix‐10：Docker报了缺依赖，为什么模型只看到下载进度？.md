# AgenticFix‐10：Docker报了缺依赖，为什么模型只看到下载进度？

记录 BUG-20260914-007，2026-09-14，Asia/Singapore（UTC+08:00）。状态：错误反馈的前缀截断缺陷已修复，完成模拟流与真实 Docker 故障注入验证；尚未测试这项修改能否减少真实模型的环境重试次数或 Token。

## 起因：错误已经返回，但没有完整进入模型消息

用户提出把 Docker 环境和错误信息提供给 Agent，减少重复尝试。检查发现 build_environment 已经返回 stdout、stderr、退出码、超时、镜像等字段，系统提示词也已有 Python 镜像范围、工作目录、只读文件系统和网络限制。缺口不是完全没有反馈，而是长输出在两层被截掉：

1. Docker CLI 原来每个输出流只保留前 max_output_bytes 字节。默认上限1MiB；超过后继续排空进程输出，但丢弃后面的内容。
2. AgentLoop 将整个 ToolResult 序列化，再只保留前 max_tool_message_chars 字符，默认12000。stdout/stderr 排在退出码等字段之前，大日志会把错误尾部和结构化状态都挤掉。给模型的提示却是“缩小读取/搜索范围”，对构建故障无效。

此前 more-itertools 的五次真实模型实验全部成功构建环境，失败原因是预算停止；不能用本次新发现解释那五次失败，也不能把本次工程验证加入它们的成功率统计。

## 同一份输入的旧/新反馈对照

模拟日志由600行下载进度组成，末尾添加实际字符串：

```text
ModuleNotFoundError: No module named 'agenticfix_missing_dependency'
```

退出码1，timed_out=false。另在真正 Docker 构建里执行大量输出后导入一个不存在的模块，得到构建失败。第二次实际采集的同一份 Docker 结果分别交给旧 AgentLoop.tool_message 与新实现：

| 输入与观测 | 旧反馈 | 新反馈 |
| --- | --- | --- |
| 模拟日志：模型消息字符数 | 12597 | 5217 |
| 模拟日志：缺依赖错误可见 | 否 | 是 |
| 模拟日志：exit_code可见 | 否 | 是，1 |
| 实际Docker结果：模型消息字符数 | 12258 | 6004 |
| 实际Docker结果：缺依赖错误可见 | 否 | 是 |
| 实际Docker结果：exit_code可见 | 否 | 是，1 |

这张表是同一输入通过两个消息投影实现的对照。它证明消息字符数减少且保留了检查的错误信息，不是模型 Token 对照；本次模型请求为0，Token为0，也没有测量重试次数收益。Docker那行使用新采集器已经采集到的结果，没有冒充旧采集器的完整历史运行。

## 第一版修复为什么还失败了

开始只保留日志头尾，做真实 Docker 故障注入：

```dockerfile
FROM python:3.12-slim
RUN python -c "print('setup-start'); print('download-progress-' * 2500); import agenticfix_missing_dependency"
```

本次特意把采集上限设为20000字节，模型消息上限仍12000字符，以较小日志复现两层截断。第一次 Docker 构建退出1，构建调用31.47秒，含创建和清理共32.11秒，truncated=true。采集结果中没有 `No module named`，验证程序因此 AssertionError。末尾有大量 download-progress 以及 BuildKit 的“process … exit code: 1”包装错误，缺少 Python 的具体异常。

这说明“错误一定在最后”这个假设不成立。stdout/stderr 合并及缓冲可能影响输出顺序，本次没有分别隔离这些因素，因此不把某种缓冲行为写成已证明的唯一根因。第一次失败的 Dockerfile、CLI结果和断言失败全部保留在 attempt-head-tail/，没有被成功结果覆盖；该中间版本的源码差异未单独冻结，不能将其视为完整可重建的历史源码快照。

第二次实际构建仍退出1（故障是刻意保留的），构建调用22.92秒，总23.52秒；新反馈验证通过。该次原始头尾片段本身也恰好包含缺依赖信息，因此不能只靠两次实际构建证明“疑似错误行摘录”是成功的唯一原因。为此另外增加确定性测试：把 `ModuleNotFoundError: middle-error` 放在大段噪声中间，保证它不在头尾片段内；新采集器的 diagnostic_lines 与模型诊断摘录仍包含它。

## 最终改了什么

- Docker 输出仍有字节上限。超过上限时保留开头约四分之一、滚动尾部，并插入明确的 middle omitted 标记；每个流分别处理，避免一条流的噪声挤掉另一条流。
- 采集过程中额外保留最多16条疑似错误行，每条最多512字节，依据 error、exception、traceback、failed、not found、no module named 等关键词。跨读取块的未结束行也有长度上限，不无限累积内存。
- 对超过消息长度上限的构建/测试失败，保留 success、error_code、exit_code、timed_out、launch_error、测试状态/目标/版本、镜像及产物位置等可用状态；给诊断摘录与两个流分配有界空间。
- 提示明确写“疑似错误行是关键词匹配的日志摘录，不是根因判断”。模型仍负责结合代码与 Dockerfile 决定安装什么、如何修改。
- 短错误保持原反馈；源码读取工具不受此改动影响。原始工具对象不因模型消息投影被修改。采集产物本身可能截断，因此没有承诺无限完整日志。

成功构建摘要和旧读取保留两个先前实验选项仍默认关闭。本次修复正常启用错误保留，没有改模型、预算算法、Issue或验收测试。

新反馈中的实际片段包括：

```text
stderr: #6 0.037 ModuleNotFoundError: No module named 'agenticfix_missing_dependency'
exit_code: 1
timed_out: false
```

关键词摘录会漏掉不含匹配词的错误，超过16条时也会淘汰较早条目；它还可能选到无关的“error”文字。头尾及摘录不等于完整日志检索，本轮没有新增供模型随意读取宿主日志文件的权限。

## 验证、版本和复现

局部初次检查32 passed、1 skipped，18.81秒；最终完整工程测试 **99 passed、1 skipped，28.41秒**。新增覆盖长stdout与stderr并存、状态保留、原始结果不变、跨多个读取块的头尾截断，以及中间错误进入诊断摘录。工程ruff通过，mypy检查33个源文件通过。

完整套件跳过的是现有隔离/超时Docker集成测试；本轮另外执行的是上面的真实构建故障注入，不能混称为重跑了同一个集成测试。

旧消息投影提交：`2fd3229a08f279671745180699a3b135969e9347`。修复提交：`63e787c09a23406c46743ed8e98aa956aa198f6a`。证据提交：`0648dc29e43eee3bb2806d8380b24590c37bfefb`。

故障注入运行时是未提交开发状态；metadata.json 是结束后的补录，不是运行开始快照。保留相对旧提交的 development-source.patch、新增源文件哈希及最终修复提交，不能把当时状态说成干净提交。Docker基础镜像使用可变标签，实际解析到 `python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`；新机器重新解析标签可能变化。

[前后消息与指标](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/comparison.json) · [第一次失败](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/attempt-head-tail/probe-failed.txt) · [第一次构建结果](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/attempt-head-tail/build-result.json) · [第二次构建结果](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/build-result.json) · [元数据](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/metadata.json) · [开发源码差异](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/development-source.patch) · [最终测试](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/full-tests-final.txt) · [SHA-256清单](https://github.com/xiaoyumuxi/AgenticFix/blob/0648dc29e43eee3bb2806d8380b24590c37bfefb/docs/iteration-evidence/BUG-20260914-007/archive-manifest.json)

在仓库根目录、Docker已启动时运行：

```bash
uv run python -m docs.iteration-evidence.BUG-20260914-007.reproduce
```

复现程序刻意让Docker构建失败，再断言反馈是否包含错误；验证程序通过不代表Docker构建成功。复现输出写到 runs/environment-feedback-replay，不覆盖归档数据。程序与实现需要包含旧提交的Git历史。没有调用模型，也没有读取独立Issue验收答案。
