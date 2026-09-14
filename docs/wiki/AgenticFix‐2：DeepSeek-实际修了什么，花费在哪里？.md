# AgenticFix-2：DeepSeek 实际修了什么，花费在哪里？

记录日期：2026-09-14，UTC+08:00。

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

| 请求 | 工具动作 | 输入 Token | 输出 Token | 合计 | 请求耗时（秒） |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | list_files, read_file | 1823 | 57 | 1880 | 0.8498 |
| 2 | read_file, read_file | 2147 | 71 | 2218 | 0.6395 |
| 3 | edit_file | 2730 | 290 | 3020 | 1.4787 |
| 4 | read_file, run_tests | 3079 | 52 | 3131 | 0.8694 |
| 5 | git_diff | 3495 | 22 | 3517 | 0.7862 |
| 6 | 返回完成说明 | 3801 | 121 | 3922 | 1.1973 |
| 合计 | 6 次请求 | **17075** | **613** | **17688** | **5.8208** |

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

### 29 个用例逐项比较

下表的实际返回值、异常和输入变化由本次补跑采集：使用历史归档提交 `1ad3fda9a588dfe181a119f3b7f9247de2f07d87` 中的 Calculator 源码、原 Patch 和原追加测试，不调用模型、不修改断言。补跑结果与历史汇总相同：9 失败、20 通过 → 29 通过。它不是原模型运行时自动采集的返回值日志；24 项追加测试仍属于原运行结束后的独立检查。

| 用例 | 输入 `(a,b)` | 预期 | 修复前实际 | 修复后实际 | 输入被改动（前→后） | 补跑测试（前→后） |
| --- | --- | --- | --- | --- | --- | --- |
| 追加 test_numeric_combinations[0-0] | `[0, 0]` | 0 | 0 | 0 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[0-2] | `[2, 0]` | 2 | 2 | 2 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[0--3] | `[-3, 0]` | -3 | -3 | -3 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[0-1.25] | `[1.25, 0]` | 1.25 | TypeError | 1.25 | 否→否 | 失败→通过 |
| 追加 test_numeric_combinations[2-0] | `[0, 2]` | 2 | 2 | 2 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[2-2] | `[2, 2]` | 4 | 4 | 4 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[2--3] | `[-3, 2]` | -1 | -1 | -1 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[2-1.25] | `[1.25, 2]` | 3.25 | TypeError | 3.25 | 否→否 | 失败→通过 |
| 追加 test_numeric_combinations[-3-0] | `[0, -3]` | -3 | -3 | -3 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[-3-2] | `[2, -3]` | -1 | -1 | -1 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[-3--3] | `[-3, -3]` | -6 | -6 | -6 | 否→否 | 通过→通过 |
| 追加 test_numeric_combinations[-3-1.25] | `[1.25, -3]` | -1.75 | TypeError | -1.75 | 否→否 | 失败→通过 |
| 追加 test_numeric_combinations[1.25-0] | `[0, 1.25]` | 1.25 | TypeError | 1.25 | 否→否 | 失败→通过 |
| 追加 test_numeric_combinations[1.25-2] | `[2, 1.25]` | 3.25 | TypeError | 3.25 | 否→否 | 失败→通过 |
| 追加 test_numeric_combinations[1.25--3] | `[-3, 1.25]` | -1.75 | TypeError | -1.75 | 否→否 | 失败→通过 |
| 追加 test_numeric_combinations[1.25-1.25] | `[1.25, 1.25]` | 2.5 | TypeError | 2.5 | 否→否 | 失败→通过 |
| 追加 test_reject_non_numeric[False-None] | `[1, null]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[False-2] | `[1, "2"]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[False-bad2] | `[1, []]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[False-bad3] | `[1, {}]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[True-None] | `[null, 1]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[True-2] | `["2", 1]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[True-bad2] | `[[], 1]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 追加 test_reject_non_numeric[True-bad3] | `[{}, 1]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |
| 公开 test_integers | `[2, 3]` | 5 | 5 | 5 | 否→否 | 通过→通过 |
| 公开 test_negative_integers | `[-2, 1]` | -1 | -1 | -1 | 否→否 | 通过→通过 |
| 公开 test_float_inputs | `[1.5, 2.25]` | 3.75 | TypeError | 3.75 | 否→否 | 失败→通过 |
| 公开 test_mixed_inputs | `[1, 2.5]` | 3.5 | TypeError | 3.5 | 否→否 | 失败→通过 |
| 公开 test_rejects_text | `["1", 2]` | TypeError | TypeError | TypeError | 否→否 | 通过→通过 |

非法输入的 TypeError 是预期行为，因此这 9 项（8 项追加 + 1 项公开）抛异常仍算通过。失败的 9 项全部是应支持的浮点数组合：7 项追加、2 项公开。其余 20 项原本通过且继续通过，不能把“没有抛异常”作为所有用例的统一成功标准。

| 汇总指标 | 原基准 / 修复前 | 原 Patch 应用后 |
| --- | ---: | ---: |
| 相同测试集用例数 | 29 | 29 |
| 通过 | 20 | 29 |
| 失败 | 9 | 0 |
| pytest 退出码 | 1 | 0 |
| 原有通过项保留 | 20 | 20 |
| 新增失败 / 缺失用例 | — | 0 / 0 |

[逐项补跑数据](https://github.com/xiaoyumuxi/AgenticFix/blob/b31898692df1ee508297b65a8033ab914b814986/docs/iteration-evidence/WIKI-DATA-COMPARISON/calculator-observations.json) · [补跑程序](https://github.com/xiaoyumuxi/AgenticFix/blob/b31898692df1ee508297b65a8033ab914b814986/docs/iteration-evidence/WIKI-DATA-COMPARISON/calculator_replay.py)。

### 数据和可追溯范围

- [六次请求的原始用量与工具动作摘要](https://github.com/xiaoyumuxi/AgenticFix/blob/bf995b0b31dd1db6d5c33fa5258b88d053a24232/docs/iteration-evidence/RUN-20260914-001/request-breakdown.json)
- [运行摘要、配置来源和证据哈希](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/summary.json)
- [完整 Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/final.patch)
- [目标源文件](https://github.com/xiaoyumuxi/AgenticFix/tree/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/fixture-source)
- [新增的 24 项检查](https://github.com/xiaoyumuxi/AgenticFix/blob/1ad3fda9a588dfe181a119f3b7f9247de2f07d87/docs/iteration-evidence/RUN-20260914-001/test_additional.py)

原始运行未自动保存完整配置和 Agent commit 快照，补录字段已注明来源，未采集的额外参数保持 unknown。这是记录机制的缺口，后续应在开始运行时自动采集，不能每次靠事后整理。

## 本页修订说明

本次直接展开 29 个用例的输入、预期、前后实际值、输入变化与状态，并补齐原六次请求的耗时。历史汇总和原始证据保留；服务实际模型标识、未采集配置与计费信息仍标为缺失，不根据后续运行倒填。原页遗留的“Wiki 待发布”和旧字节码章节修订说明已纠正，本页只记录 Calculator。
