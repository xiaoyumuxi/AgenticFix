# AgenticFix：第一次接入模型时遇到的问题和实测结果

记录日期：2026-09-14，UTC+08:00。

这里有两件事，分别记录：一件是测试执行器读到旧代码的错误；另一件是修复这个错误之后，DeepSeek 完成的一次 Calculator 修复。后者不是前者的对照实验。

## BUG-20260914-001：文件已经改了，测试为什么还在执行旧逻辑？

### 当时看到的异常

接入 Agent Loop 的离线测试时，第一次完整执行是 **3 failed、70 passed**。其中一个用例把 `calculate(2, 3)` 的实现从减法改成加法，但测试仍然得到 `-1`；另一个把除法改成加法，仍得到 `0.6666666666666666`。期望值都是 `5`。

```text
源码要执行：return a + b
输入：calculate(2, 3)
期望：5
实际：-1，或者 0.6666666666666666（分别对应修改前的减法和除法）
```

第三个失败出现在 `value = 1 → value = 2 → value = 3` 的连续修复测试里。模拟模型按预定步骤完成后，Runtime 仍收到失败测试，要求它继续工作，最终耗尽模拟响应队列，记录 `runtime_error:IndexError`。

这个 IndexError 是后续症状，不能直接当成模型接口错误处理。需要先解释：为什么测试给出的数值仍然是修改前的结果？

上面的开发测试当时包含未提交代码，原始完整工作区差异和控制台日志没有归档。它们是发现问题的背景，不能伪称为某个已提交版本的完整测试成绩。下面另做可重复的历史组件对照来确认原因。

### 先证明文件改成功了，再检查执行器读了什么

把问题缩到一个模块：先写入 `value = 1`，编译出 `.pyc`，再改成 `value = 2`。明确保留相同文件大小和修改时间，模拟快速连续等长修改。

| 观测项 | 编译缓存时 | 修改源码后 |
| --- | --- | --- |
| 源码内容 | `value = 1\n` | `value = 2\n` |
| 源码长度 | 10 字节 | 10 字节 |
| 文件 mtime，Unix 秒 | 1700000000 | 1700000000 |
| `.pyc` 头记录的源码长度 | 10 | 10，旧缓存未变 |
| `.pyc` 头记录的 mtime | 1700000000 | 1700000000，旧缓存未变 |
| `.pyc` flags | 0，时间戳校验模式 | 0 |

每次执行前直接读取文件，确认磁盘上的内容已经是 `value = 2`，然后启动新的 Python 子进程：

```python
import example
print(example.value)
assert example.value == 2
```

旧执行器输出 **1**，断言失败，退出码 **1**。这一步排除了“编辑没有写进文件”：磁盘内容是 2，导入得到的却是 1。

### 不是凭猜测归因，分别改一个条件再跑

以下每行都从相同的旧缓存和相同的新源码重新开始。期望输出始终为 2。

| 实验 | 源码大小 | 源码 mtime | 实际输出 | 退出码 |
| --- | ---: | ---: | ---: | ---: |
| 旧执行器，保留旧缓存 | 10 | 1700000000 | **1** | **1** |
| 旧执行器，只加 `-B` 禁止写字节码 | 10 | 1700000000 | **1** | **1** |
| 旧执行器，删除旧 `.pyc` | 10 | 1700000000 | **2** | **0** |
| 旧执行器，只把 mtime 增加两秒 | 10 | 1700000002 | **2** | **0** |
| 旧执行器，只添加注释使源码长度变化 | 25 | 1700000000 | **2** | **0** |
| 修复后的执行器，仍保留旧缓存 | 10 | 1700000000 | **2** | **0** |

这些结果连起来才能支持判断：

- 删除缓存就恢复正确，说明旧缓存参与了错误结果。
- 只改时间或大小也恢复正确，与 `.pyc` 头里的时间戳/大小校验对应。
- 单独 `-B` 仍然输出 1，说明禁止写缓存并不禁止读取已有缓存。
- 修复后的执行器在缓存、源码大小和时间均保持原条件时输出 2，说明修复覆盖了最初的触发条件。

因此，问题不是加法写错，也不是 pytest 没发现断言失败，而是测试进程导入了旧字节码。它把旧逻辑的结果反馈给 Agent，后续修复自然会被误导。

### 为什么这样修改

LocalSandbox 为每次测试进程设置：

```python
PYTHONPYCACHEPREFIX = 一个新的、尚不存在的临时路径
PYTHONDONTWRITEBYTECODE = "1"
```

换前缀是为了避开已有字节码的查找位置；禁止写入是为了不再生成新的缓存目录。只做第二项不够，上面的 `-B` 对照已经验证了这一点。

没有通过让 Agent 等一秒来解决，因为那只是让时间戳变化，依赖执行时序；也没有改变业务代码的长度来让测试碰巧通过。修复放在统一执行器中，所有通过它运行的 Python 测试都使用同样的处理。

这样会放弃部分字节码缓存收益，但目前没有做性能对照，不能给出开销数字。当前优先保证测试执行的是本次代码。

### 对应版本和证据

| 角色 | 完整 commit |
| --- | --- |
| 对照使用的旧 LocalSandbox | `ba96c26cb61efff5ba05105e07218b9aaa240940` |
| LocalSandbox 修复提交 | `30cfc421c6a7850411ba4fa72bfd3f9df5cabbf6` |
| 六组诊断实验和数据归档 | `bf995b0b31dd1db6d5c33fa5258b88d053a24232` |

[修复差异](https://github.com/xiaoyumuxi/AgenticFix/commit/30cfc421c6a7850411ba4fa72bfd3f9df5cabbf6) · [诊断程序](https://github.com/xiaoyumuxi/AgenticFix/blob/bf995b0b31dd1db6d5c33fa5258b88d053a24232/docs/iteration-evidence/BUG-20260914-001/diagnose.py) · [六组原始结果](https://github.com/xiaoyumuxi/AgenticFix/blob/bf995b0b31dd1db6d5c33fa5258b88d053a24232/docs/iteration-evidence/BUG-20260914-001/diagnosis-v2.json)

复现环境为 Python 3.12.13、macOS arm64。程序读取历史提交中的 `sandbox/local.py`，在同一当前环境里做组件对照，不代表整个历史仓库的测试成绩。

```bash
uv sync --locked
uv run python docs/iteration-evidence/BUG-20260914-001/diagnose.py
```

回归测试是 `test_same_size_same_timestamp_bytecode_is_not_reused`。早期 `reproduce.py/result.json` 只有打印、没有断言，因此两边退出码都为 0；本次 `diagnose.py/diagnosis-v2.json` 加入断言，输出旧值时退出码为 1。两份记录都保留，不能混用它们的退出码。

后续测试数量有所增加，所以也不能把开发中的“3 failed、70 passed”和最终“78 passed”直接当成这次修复的同一测试集对照。修复的直接依据是上面的六组实验。

---

## RUN-20260914-001：DeepSeek 实际修了什么，花费在哪里？

### 运行的版本和任务

| 项目 | 值 |
| --- | --- |
| run_id | `agent-dd31f7965c67` |
| Agent 代码版本 | `b55a30ca0f9dc23860ccee43785bbaefd42e0ee4` |
| Agent 工作区 | 开始前检查为干净；当时未由 Runtime 自动采集 |
| 目标仓库 | 本项目生成的 Calculator fixture |
| 目标 base_commit | `240437985b8c4b36e5d0a7ab513d136a871f997d` |
| 配置模型 | DeepSeek / `deepseek-flash` |

Agent commit 和目标 base_commit 不是同一个东西。后者属于临时生成的目标 Git 仓库；其源文件已归档，不是 AgenticFix 主仓库里可直接检出的提交。

目标函数本来就用 `a + b` 返回结果，问题出在前面的检查只接受 `int`。公开测试中：

- `add(1.5, 2.25)` 应返回 `3.75`，实际抛出 TypeError。
- `add(1, 2.5)` 应返回 `3.5`，实际抛出 TypeError。
- 两个整数用例和一个拒绝字符串的用例原本通过。

因此基线是 **2 failed、3 passed**。这组数据指出需要放宽数值类型检查，同时保留对非数值的拒绝；并不需要重写加法算法。

### 六次模型请求的实际轨迹

以下数据来自原始 Trace，Token 是服务报告值。

| 请求 | 模型选择的动作 | 输入 Token | 输出 Token | 合计 |
| --- | --- | ---: | ---: | ---: |
| 1 | 列目录，读取 calculator.py | 1823 | 57 | 1880 |
| 2 | 读取 test_calculator.py、issue.md | 2147 | 71 | 2218 |
| 3 | 精确编辑 calculator.py 的类型检查 | 2730 | 290 | 3020 |
| 4 | 重新读取 calculator.py，运行测试 | 3079 | 52 | 3131 |
| 5 | 获取 git_diff | 3495 | 22 | 3517 |
| 6 | 返回完成说明 | 3801 | 121 | 3922 |
| 总计 | | **17075** | **613** | **17688** |

模型发起了 8 次工具调用；Runtime 另外执行了开始时的测试，以及结束时的测试和 Diff，共 **11 次工具调用**。不能把这 11 次都算成模型主动选择的动作。

模型实际只做了一次编辑：

```diff
- if not isinstance(a, int) or not isinstance(b, int):
+ if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
```

这让两种参数位置都能接受浮点数，同时保留 TypeError 分支。测试文件没有修改。模型运行测试得到 5 passed 后，Runtime 在结束检查中再次得到 5 passed，随后交付非空 Patch。

### 为什么又做了 29 项检查

5 个公开测试通过，只说明这 5 个用例通过。为了检查更多组合，模型结束后，在干净 worktree 里加入了 24 个检查，并在应用 Patch 前后执行同一组测试。

| 测试组 | 用例数 | 应用前 | 应用后 |
| --- | ---: | --- | --- |
| 原始公开测试 | 5 | 2 失败、3 通过 | 5 通过 |
| `[0, 2, -3, 1.25]` 两两组合 | 16 | 7 失败、9 通过 | 16 通过 |
| None、字符串、列表、字典分别放左右参数 | 8 | 8 通过 | 8 通过 |
| 总计 | **29** | **9 失败、20 通过** | **29 通过** |

16 个数值组合里，有 7 个至少包含一个浮点数；修复前正好这 7 个被旧类型检查拒绝。剩下 9 个整数组合本来通过，修复后继续通过。8 个非法参数检查也继续通过。

因此本次结果支持：Patch 修复了这些浮点数组合，且没有破坏这些整数和非法输入行为。没有检查的行为，不能从这张表推出结论。

这 24 项是模型结束后追加的，没有发给模型，但也没有在运行前冻结，所以是事后独立检查，不称为正式隐藏 Benchmark。

### 7.65 秒和 17,688 Token 应该怎么理解

主运行耗时 **7.65 秒**，其中六次模型请求的客户端耗时相加为 **5.82 秒**。主运行耗时不含后来做的 29 项独立验证。

输入 Token 是 **17,075，占总数约 96.5%**；输出只有 **613**。虽然最终只改了一行，接口会在多轮请求里重复接收工具定义、Issue 和累积上下文，所以不能按 Patch 行数估计调用量。最后一次请求的输入从第一次的 1,823 增长到了 3,801。

这给后续实验一个可检查的方向：是否需要每轮都携带相同内容，工具结果是否可以更短。但当前没有压缩前后的对照，不能把输入 Token 全叫作浪费，也不能宣称已经能降低多少费用。原始记录没有完整的缓存计费信息，本次没有计算金额成本。

本次一次修改即成功，没有测试真实模型在错误修改后的恢复能力；一个 Calculator 示例也不能代表真实 GitHub Issue 的成功率。

### 数据和可追溯范围

- [六次请求的原始用量与工具动作摘要](https://github.com/xiaoyumuxi/AgenticFix/blob/bf995b0b31dd1db6d5c33fa5258b88d053a24232/docs/iteration-evidence/RUN-20260914-001/request-breakdown.json)
- [运行摘要、配置来源和证据哈希](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/summary.json)
- [完整 Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/final.patch)
- [目标源文件](https://github.com/xiaoyumuxi/AgenticFix/tree/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/fixture-source)
- [新增的 24 项检查](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/test_additional.py)

原始运行未自动保存完整配置和 Agent commit 快照，补录字段已注明来源，未采集的额外参数保持 unknown。这是记录机制的缺口，后续应在开始运行时自动采集，不能每次靠事后整理。

## 本页修订说明

本版补充了旧字节码问题的发现过程、六组因果对照、为什么选择当前修复、DeepSeek 的逐轮用量和测试组成。之前的简版和证据保留在 Git 历史中。

后续 Wiki 记录按 AGENTS.md 执行：关键数据写进正文，并解释这些数据如何支持判断。链接用于复核，不能代替分析。未发布前保持“Wiki 待发布”状态。
