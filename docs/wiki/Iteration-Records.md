# AgenticFix 迭代记录

记录日期：2026-09-14（Asia/Singapore，UTC+08:00）。

本页记录实际错误、历史版本、验证数据和相关证据。失败案例是后续迭代的依据，不覆盖旧结果，不用成功 Demo 代替真实评测。

## BUG-20260914-001：旧字节码导致测试执行旧代码

**状态：已修复，历史版本对照复现通过。**

### 现象与影响

接入 Agent Loop 时，源码已经修改，但再次运行 pytest 仍表现为旧逻辑。快速连续修改可能因此收到错误的测试反馈，干扰 Agent 的判断，也影响评测可信度。

根因是 Python 的时间戳式字节码缓存：当源码修改前后的大小相同，且修改时间落在相同的时间戳精度内，已有 `.pyc` 可能仍被判定有效。

### 历史版本

| 角色 | AgenticFix commit |
| --- | --- |
| 修复前 LocalSandbox | `ba96c26cb61efff5ba05105e07218b9aaa240940` |
| 修复提交 | `30cfc421c6a7850411ba4fa72bfd3f9df5cabbf6` |

[查看修复差异](https://github.com/xiaoyumuxi/AgenticFix/commit/30cfc421c6a7850411ba4fa72bfd3f9df5cabbf6)

### 可复现的对照

1. 创建 `value = 1` 的模块并编译字节码。
2. 改成等长的 `value = 2`，保留原修改时间。
3. 分别通过历史版本和修复版本的 LocalSandbox 导入模块。

| 检查 | 修复前 | 修复后 |
| --- | --- | --- |
| 源码期望值 | 2 | 2 |
| 实际读取值 | **1，错误** | **2，正确** |
| 子进程退出码 | 0 | 0 |

这是历史 LocalSandbox 组件的受控对照，不是对整个历史版本测试套件的重新评测。复现环境为 Python 3.12.13、macOS arm64。

两次退出码都为 0，说明“进程成功结束”不能证明“执行了当前源码”。

### 修复方式

每次测试执行使用新的 `PYTHONPYCACHEPREFIX`，并设置 `PYTHONDONTWRITEBYTECODE=1`，避免读取旧缓存，也不产生新的缓存目录。

增加回归测试 `test_same_size_same_timestamp_bytecode_is_not_reused`，明确构造相同大小、相同修改时间的源码，断言执行结果来自新代码。没有通过等待时间或更换任务规避错误。

### 证据与复现命令

- [最小复现程序](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/BUG-20260914-001/reproduce.py)
- [历史版本对照结果](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/BUG-20260914-001/result.json)

在包含上述证据文件的仓库版本中执行：

```bash
uv sync --locked
uv run python docs/iteration-evidence/BUG-20260914-001/reproduce.py
```

程序从 Git 历史读取两个版本的 LocalSandbox，不修改当前源码，也不调用模型。

### 迭代结论

测试执行环境是 Agent 正确性的一部分。以后任何缓存、依赖和工作区变化，都要检查它是否使测试反馈与当前代码脱节。LocalSandbox 仍只用于可信代码，本修复不提供宿主机安全隔离。

---

## RUN-20260914-001：首次真实 DeepSeek 自主修复

**状态：单个可信示例通过，不能据此推导真实 Issue 成功率。**

### 版本与任务

| 项目 | 记录 |
| --- | --- |
| run_id | `agent-dd31f7965c67` |
| Agent 运行版本 | `b55a30ca0f9dc23860ccee43785bbaefd42e0ee4` |
| Agent 工作区 | 运行前检查为干净；当时 Runtime 尚未自动采集此字段 |
| 目标项目 | 本项目生成的可信 Calculator fixture |
| 目标 base_commit | `240437985b8c4b36e5d0a7ab513d136a871f997d` |
| 服务与配置模型 | DeepSeek / `deepseek-flash` |
| 目标问题 | add() 支持整数、浮点数及混合输入，继续拒绝非数值输入 |

Agent 运行版本与目标仓库 base_commit 是两套不同的版本标识。目标 commit 属于本地生成的 fixture 仓库；其源文件已另外归档，不能当作 AgenticFix 主仓库中的 commit。

### 实际数据

| 指标 | 结果 |
| --- | --- |
| 模型请求 | 6 |
| 工具调用，含 Runtime 验证 | 11 |
| 服务报告 Token | 17,688 |
| 估算 Token | 0 |
| 主运行耗时 | 7.65 秒 |
| 修改文件 | 仅 calculator.py |
| 修改前公开测试 | 2 failed，3 passed |
| 修改后公开测试 | 5 passed |
| 独立检查应用 Patch 前 | 9 failed，20 passed |
| 独立检查应用 Patch 后 | **29 passed** |

耗时不包含后续人工组织的独立验证。本次未计算金额费用。

### 模型生成的修改

```diff
- if not isinstance(a, int) or not isinstance(b, int):
+ if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
```

模型读取实现和测试后修改代码，没有修改测试。本次一次编辑就通过，未验证真实模型在失败修改后的恢复能力。

### 独立检查范围

模型运行结束后，在相同基准的干净 worktree 中追加 24 个检查，与原始 5 个测试一起运行：

- `[0, 2, -3, 1.25]` 的 16 种两两输入组合。
- `None`、字符串、列表、字典在左右参数位置的 8 种拒绝检查。

这些新增检查没有进入此次模型上下文，但它们是事后追加验证，不是预先冻结的隐藏 Benchmark。

### 证据与元数据限制

- [脱敏指标、配置来源和证据 SHA-256](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/summary.json)
- [完整 Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/final.patch)
- [目标仓库源文件快照](https://github.com/xiaoyumuxi/AgenticFix/tree/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/fixture-source)
- [新增独立检查](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/test_additional.py)

原始运行没有完整的配置快照；摘要区分了原始数据和补录来源。未采集的额外模型参数保持 unknown，不能事后补造。原始 Trace 和对话留在本地受控产物目录，未将密钥或未经审查的原始推理上传。

### 下一步

补足其他类型的真实模型任务与失败恢复案例，并在开始运行时自动保存 Agent commit、工作区差异、脱敏配置和环境快照。真实 GitHub Issue 执行前完成 Docker 隔离及独立验收流程。

---

## 后续记录规范

规范已写入 [AGENTS.md：Wiki 与版本化证据要求](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/AGENTS.md)。

后续每次关键错误、真实运行或对照实验均需记录唯一 ID、Agent 与目标版本、实际数据、根因、修复提交、复现方式及证据校验值。历史结果追加保留，未知字段明确标记；不得只把证据留在聊天或临时 runs 目录。
