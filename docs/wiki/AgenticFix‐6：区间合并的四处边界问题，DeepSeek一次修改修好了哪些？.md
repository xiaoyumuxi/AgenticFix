# AgenticFix-6：区间合并的四处边界问题，DeepSeek一次修改修好了哪些？

日期：2026-09-14，UTC+08:00。本次保留两次运行，均未重试选优。它们是自编可信任务，不是真实 GitHub Issue 成功率。

## 运行条件先固定

Agent 和公开/独立测试均固定在提交 `66f48ec0e6fbdbf6705a733bbadca87283ee5fa1`。两次 metadata.json 都自动记录 dirty=false；此前 Calculator 的版本不同，不放在一起当作同条件对照。

请求与服务返回的模型标识均为 `deepseek-flash`，provider 为 DeepSeek；extra_body={}，未显式设置 temperature，不能把服务默认参数写成 temperature=0。服务没有返回不可变权重版本，因此这里只记录其实际返回名。

两次均使用 max_iterations=30、max_tool_calls=60、max_token_budget=100000、max_completion_tokens=4096、max_run_duration=600 秒、测试超时 60 秒、模型请求超时 90 秒、max_model_retries=2。Python/依赖版本、Prompt、锁文件 SHA-256 和完整非敏感配置见自动快照。

脚本在请求模型前固定任务文件哈希。独立测试没有复制到 Agent worktree，只在另一份验收 worktree 中执行。Patch 应用前后使用同一组用例；验收时恢复冻结的公开测试与 pytest.ini，并检查原用例是否缺失。两次 Patch 都只修改实现文件。

## RUN-20260914-003 / TASK-BUG-20260914-002：区间合并的四处边界缺陷

run_id：`agent-751ccbf64f94`。目标 base_commit：`82979f5a59b001195f04d5f35650eff1fa46e2ba`。

原函数有四处互相关联的错误，不是一个断言换个期望值就能解决：

| 输入/观察 | 修改前 | 预期/修改后 | 对应原因 |
| --- | --- | --- | --- |
| `[]` | IndexError | `[]` | 直接访问 intervals[0] |
| `[[1,3],[3,5]]` | `[[1,3],[3,5]]` | `[[1,5]]` | 用 `<` 排除了端点相接 |
| `[[1,10],[2,3]]` | `[[1,3]]` | `[[1,10]]` | 无条件用较短的 end 覆盖右端点 |
| 输入 `[[4,6],[1,5]]` | 输入本身被重排为 `[[1,5],[4,6]]` | 原输入保持不变 | 调用 intervals.sort() 原地排序 |

模型读实现、测试和 Issue 后，一次替换完成处理：结果从空列表开始；排序复制后的区间；使用 `<=` 判断接触；只有新区间右端更大时才扩展已合并区间。这样空列表不进入循环，嵌套短区间不会缩短结果，也不修改调用方的数据。

| 测试组 | 修改前 | 修改后 |
| --- | --- | --- |
| 5 个公开测试 | 4 失败、1 通过 | 5 通过 |
| 10 个事先冻结的独立测试 | 7 失败、3 通过 | 10 通过 |
| 合计 | **11 失败、4 通过** | **15 通过** |

独立测试包含重复区间、点区间、负数、浮点端点、链式连接、逆序和多重嵌套，并逐项检查输入不变。原先 4 个通过项继续通过，新增回归=0、缺失用例=0；退出码从 1 变为 0。非法区间 start > end 不在 Issue 的输入约定内，也未验证。

| 请求 | 动作 | 输入 Token | 输出 Token | 合计 |
| --- | --- | ---: | ---: | ---: |
| 1 | 列目录、读实现 | 2132 | 59 | 2191 |
| 2 | 读测试、Issue | 2464 | 70 | 2534 |
| 3 | 编辑 intervals.py | 3112 | 314 | 3426 |
| 4 | 跑公开测试 | 3486 | 23 | 3509 |
| 5 | 返回完成说明 | 3674 | 172 | 3846 |
| 合计 | | **14868** | **638** | **15506** |

模型主动工具调用 6 次，加 Runtime 3 次，总计 9 次。Loop 耗时 **6.5471 秒**，请求耗时合计 **4.9310 秒**，不含独立验收。

## 这次数据支持什么

两项都只有一次 edit_file，修改后的第一次测试就通过。因此已经观察到跨文件阅读后修改正确文件、一次处理多个边界问题；没有观察到真实模型错误编辑之后再恢复。不能为了填满验收表，把基线本来失败算作“第一次修复失败”。

两项合计 33538 Token，服务报告用量全部可用，估算用量=0、未知用量请求=0，没有计算金额成本。两项一共 28 个验收用例全部通过，只支持列出的行为没有出现新增失败，不能推导真实项目成功率。

下一步先接入 DockerSandbox 与独立 Eval，再选择真实历史 Issue。失败恢复仍保留为未完成验证项；将来出现真实失败时完整留存，不通过人为改坏一次来包装恢复能力。

## 逐项数据对比

下面每行对应一个验收用例，保留公开测试与独立测试中重复的输入，不合并计数。通过/失败来自原始验收记录；具体返回值及输入是否被改动，是本次用固定提交 `66f48ec0e6fbdbf6705a733bbadca87283ee5fa1` 和原归档 Patch 补跑采集的。没有重新调用模型，也没有改变测试断言。

| 用例 | 输入 | 预期返回 | 修复前实际 | 修复后实际 | 输入被改动（前→后） | 原验收结果（前→后） |
| --- | --- | --- | --- | --- | --- | --- |
| 独立 test_cases[data0-expected0] | `[]` | `[]` | IndexError | `[]` | 否→否 | 失败→通过 |
| 独立 test_cases[data1-expected1] | `[[0,0]]` | `[[0,0]]` | `[[0,0]]` | `[[0,0]]` | 否→否 | 通过→通过 |
| 独立 test_cases[data2-expected2] | `[[2,3],[1,2]]` | `[[1,3]]` | `[[1,2],[2,3]]` | `[[1,3]]` | 是→否 | 失败→通过 |
| 独立 test_cases[data3-expected3] | `[[1,10],[2,3],[4,6]]` | `[[1,10]]` | `[[1,3],[4,6]]` | `[[1,10]]` | 否→否 | 失败→通过 |
| 独立 test_cases[data4-expected4] | `[[1,2],[1,2]]` | `[[1,2]]` | `[[1,2]]` | `[[1,2]]` | 否→否 | 通过→通过 |
| 独立 test_cases[data5-expected5] | `[[-5,-1],[-2,2]]` | `[[-5,2]]` | `[[-5,2]]` | `[[-5,2]]` | 否→否 | 通过→通过 |
| 独立 test_cases[data6-expected6] | `[[0.5,1.5],[1.5,2.5]]` | `[[0.5,2.5]]` | `[[0.5,1.5],[1.5,2.5]]` | `[[0.5,2.5]]` | 否→否 | 失败→通过 |
| 独立 test_cases[data7-expected7] | `[[1,2],[3,4],[2,3]]` | `[[1,4]]` | `[[1,2],[2,3],[3,4]]` | `[[1,4]]` | 是→否 | 失败→通过 |
| 独立 test_cases[data8-expected8] | `[[9,10],[1,2]]` | `[[1,2],[9,10]]` | `[[1,2],[9,10]]` | `[[1,2],[9,10]]` | 是→否 | 失败→通过 |
| 独立 test_cases[data9-expected9] | `[[1,5],[5,5],[5,8]]` | `[[1,8]]` | `[[1,5],[5,5],[5,8]]` | `[[1,8]]` | 否→否 | 失败→通过 |
| 公开 test_disjoint | `[[1,2],[4,5]]` | `[[1,2],[4,5]]` | `[[1,2],[4,5]]` | `[[1,2],[4,5]]` | 否→否 | 通过→通过 |
| 公开 test_empty | `[]` | `[]` | IndexError | `[]` | 否→否 | 失败→通过 |
| 公开 test_touching | `[[1,3],[3,5]]` | `[[1,5]]` | `[[1,3],[3,5]]` | `[[1,5]]` | 否→否 | 失败→通过 |
| 公开 test_nested | `[[1,10],[2,3]]` | `[[1,10]]` | `[[1,3]]` | `[[1,10]]` | 否→否 | 失败→通过 |
| 公开 test_no_mutation | `[[4,6],[1,5]]` | `[[1,6]]` | `[[1,6]]` | `[[1,6]]` | 是→否 | 失败→通过 |

注意独立用例 data8 和公开 test_no_mutation：修复前后返回值相同，但旧实现重排了调用方的输入，所以原测试仍失败。data8 的输入从 `[[9,10],[1,2]]` 被改成 `[[1,2],[9,10]]`；公开用例输入从 `[[4,6],[1,5]]` 被改成 `[[1,5],[4,6]]`。修复后均保留原输入。只列返回值会漏掉这类回归。

### 版本与整体变化

修复前使用目标 base_commit `82979f5a59b001195f04d5f35650eff1fa46e2ba`；修复后在同一基准上应用原 Patch，SHA-256 为 `bf0d8a639f2796baa4706a422c117549d89ee3205897a6b7535fdab0d7e4395d`。没有为修复后目标创建新 commit，因此用 base_commit + Patch 哈希标识它。

| 指标 | 修复前 | 修复后 | 变化 |
| --- | ---: | ---: | --- |
| 测试数 | 15 | 15 | 测试集相同 |
| 通过 | 4 | 15 | +11 |
| 失败 | 11 | 0 | −11 |
| pytest 退出码 | 1 | 0 | 失败→通过 |
| 原本通过的用例 | 4 | 4 | 全部保留 |
| 缺失用例 | — | 0 | 没有靠少跑测试通过 |

### 每轮调用的实际数据

这是生成该 Patch 的一次运行，修复前基线没有调用模型，因此不存在同条件的“修复前模型 Token”。下表按请求逐轮列出，不能把不同任务的消耗差异当成优化收益。

| 请求 | 工具动作 | 输入 Token | 输出 Token | 总 Token | 请求耗时（秒） |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | list_files, read_file | 2132 | 59 | 2191 | 1.0074 |
| 2 | read_file, read_file | 2464 | 70 | 2534 | 0.5651 |
| 3 | edit_file | 3112 | 314 | 3426 | 1.6424 |
| 4 | run_tests | 3486 | 23 | 3509 | 0.5318 |
| 5 | 返回完成说明 | 3674 | 172 | 3846 | 1.1842 |
| 合计 | 5 次请求 | 14868 | 638 | 15506 | 4.9310 |

### 原始文件供复核

- RUN-20260914-003：[完整测试前后结果](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/summary.json)、[逐轮请求数据](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/request-breakdown.json)、[Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/final.patch)、[自动版本/配置快照](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/metadata.json)、[公开归档 SHA-256 清单](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/archive-manifest.json)。
  预先冻结的[公开任务](https://github.com/xiaoyumuxi/AgenticFix/tree/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/examples/intervals)和[独立验收测试](https://github.com/xiaoyumuxi/AgenticFix/tree/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/validation/intervals)。

[本次逐项补跑数据](https://github.com/xiaoyumuxi/AgenticFix/blob/fcc98204e92e19159096254de712ec6082429b8e/docs/iteration-evidence/WIKI-DATA-COMPARISON/observations.json) · [补跑程序](https://github.com/xiaoyumuxi/AgenticFix/blob/fcc98204e92e19159096254de712ec6082429b8e/docs/iteration-evidence/WIKI-DATA-COMPARISON/reproduce.py)。原始运行记录与补跑数据分开保存；本次补跑的 pytest 汇总分别与原验收一致。

local-run-manifest.json 校验原本地运行产物；archive-manifest.json 校验已公开归档，不包含本次新增补跑文件。

## 相关记录

[AgenticFix-5：两件60元的商品为什么只算出68？DeepSeek的跨文件修复](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%905%EF%BC%9A%E4%B8%A4%E4%BB%B660%E5%85%83%E7%9A%84%E5%95%86%E5%93%81%E4%B8%BA%E4%BB%80%E4%B9%88%E5%8F%AA%E7%AE%97%E5%87%BA68%EF%BC%9FDeepSeek%E7%9A%84%E8%B7%A8%E6%96%87%E4%BB%B6%E4%BF%AE%E5%A4%8D)

本页从原合并记录拆分，原始数据与历史提交保持不变；同一问题的后续复发、修复和实验继续按日期追加到本页。

### 本次文档整理反馈

生成对比表的临时脚本首次执行出现列表括号不匹配的 SyntaxError，修正后重新生成，并核对两页分别包含 13、15 行用例。该错误发生在文档生成步骤，没有修改 Agent、原验收测试或运行数据，不计作模型失败。
