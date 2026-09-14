# AgenticFix-5：两件60元的商品为什么只算出68？DeepSeek的跨文件修复

日期：2026-09-14，UTC+08:00。本次保留两次运行，均未重试选优。它们是自编可信任务，不是真实 GitHub Issue 成功率。

## 运行条件先固定

Agent 和公开/独立测试均固定在提交 `66f48ec0e6fbdbf6705a733bbadca87283ee5fa1`。两次 metadata.json 都自动记录 dirty=false；此前 Calculator 的版本不同，不放在一起当作同条件对照。

请求与服务返回的模型标识均为 `deepseek-flash`，provider 为 DeepSeek；extra_body={}，未显式设置 temperature，不能把服务默认参数写成 temperature=0。服务没有返回不可变权重版本，因此这里只记录其实际返回名。

两次均使用 max_iterations=30、max_tool_calls=60、max_token_budget=100000、max_completion_tokens=4096、max_run_duration=600 秒、测试超时 60 秒、模型请求超时 90 秒、max_model_retries=2。Python/依赖版本、Prompt、锁文件 SHA-256 和完整非敏感配置见自动快照。

脚本在请求模型前固定任务文件哈希。独立测试没有复制到 Agent worktree，只在另一份验收 worktree 中执行。Patch 应用前后使用同一组用例；验收时恢复冻结的公开测试与 pytest.ini，并检查原用例是否缺失。两次 Patch 都只修改实现文件。

## RUN-20260914-002 / TASK-BUG-20260914-001：数量漏算，连带影响运费

run_id：`agent-579c61919ecb`。目标 base_commit：`1d2aba9eac5daf0f7b560e7e12fac1a129e14d18`。目标 commit 属于生成的 fixture 仓库，不是主仓库提交。

订单经过 api.checkout_total → pricing.subtotal → shipping.shipping_fee。原来的 subtotal 只把每种商品的 unit_price 加起来，没有乘 quantity。

| 输入 | 修改前实际值 | 预期/修改后 |
| --- | ---: | ---: |
| 单价 20，数量 1 | 28 | 28 |
| 单价 60，数量 2 | 68 | 120 |
| 单价 12 数量 3，加单价 7 数量 2 | 27 | 58 |

第二个输入最能说明影响：旧小计是 60，所以又收取了 8 运费；正确小计为 120，应超过默认的 100 免运费门槛。单独把运费判断改掉也不能修好数量漏算。

模型先列目录、读公开测试，再读取 api.py、pricing.py、shipping.py 和 Issue。确认入口和运费逻辑后，只修改 pricing.py：

```diff
- return sum(item["unit_price"] for item in items)
+ return sum(item["unit_price"] * item.get("quantity", 1) for item in items)
```

quantity 使用 get(..., 1) 额外允许缺省数量；Issue 约定每项都有 quantity，本轮验收没有覆盖缺省数量，不将这一行为算作已验证能力。浮点金额仍沿用原有 round，并未验证货币精度的所有情况。

| 测试组 | 修改前 | 修改后 |
| --- | --- | --- |
| 3 个公开测试 | 2 失败、1 通过 | 3 通过 |
| 10 个事先冻结的独立测试 | 7 失败、3 通过 | 10 通过 |
| 合计 | **9 失败、4 通过** | **13 通过** |

独立用例包含零数量、零价格、空订单、浮点价格、自定义免运费门槛和不修改输入。原本通过的 4 项继续通过，新增回归=0、缺失用例=0。基线 pytest 退出码为 1，Patch 后为 0。

| 请求 | 动作 | 输入 Token | 输出 Token | 合计 |
| --- | --- | ---: | ---: | ---: |
| 1 | 列目录、读测试 | 1741 | 67 | 1808 |
| 2 | 读三个实现文件和 Issue | 2158 | 128 | 2286 |
| 3 | 编辑 pricing.py | 2927 | 290 | 3217 |
| 4 | 跑公开测试 | 3277 | 23 | 3300 |
| 5 | 查看 Diff | 3464 | 28 | 3492 |
| 6 | 返回完成说明 | 3757 | 172 | 3929 |
| 合计 | | **17324** | **708** | **18032** |

模型主动调用工具 9 次，Runtime 基线/最终测试/最终 Diff 另加 3 次，总计 12 次。Agent Loop 耗时 **8.1497 秒**，其中请求耗时合计 **6.4402 秒**。耗时不含外部独立验收。

## 这次数据支持什么

两项都只有一次 edit_file，修改后的第一次测试就通过。因此已经观察到跨文件阅读后修改正确文件、一次处理多个边界问题；没有观察到真实模型错误编辑之后再恢复。不能为了填满验收表，把基线本来失败算作“第一次修复失败”。

两项合计 33538 Token，服务报告用量全部可用，估算用量=0、未知用量请求=0，没有计算金额成本。两项一共 28 个验收用例全部通过，只支持列出的行为没有出现新增失败，不能推导真实项目成功率。

下一步先接入 DockerSandbox 与独立 Eval，再选择真实历史 Issue。失败恢复仍保留为未完成验证项；将来出现真实失败时完整留存，不通过人为改坏一次来包装恢复能力。

## 固定版本证据

- RUN-20260914-002：[完整测试前后结果](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-002/summary.json)、[逐轮请求数据](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-002/request-breakdown.json)、[Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-002/final.patch)、[自动版本/配置快照](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-002/metadata.json)、[公开归档 SHA-256 清单](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-002/archive-manifest.json)。
  预先冻结的[公开任务](https://github.com/xiaoyumuxi/AgenticFix/tree/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/examples/order_total)和[独立验收测试](https://github.com/xiaoyumuxi/AgenticFix/tree/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/validation/order_total)。
- RUN-20260914-003：[完整测试前后结果](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/summary.json)、[逐轮请求数据](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/request-breakdown.json)、[Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/final.patch)、[自动版本/配置快照](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/metadata.json)、[公开归档 SHA-256 清单](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/RUN-20260914-003/archive-manifest.json)。
  预先冻结的[公开任务](https://github.com/xiaoyumuxi/AgenticFix/tree/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/examples/intervals)和[独立验收测试](https://github.com/xiaoyumuxi/AgenticFix/tree/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/validation/intervals)。

local-run-manifest.json 指向原本地运行产物，包含未公开的原始 Trace 哈希；archive-manifest.json 校验本次公开文件，两个范围不能混用。

## 相关记录

[AgenticFix-6：区间合并的四处边界问题，DeepSeek一次修改修好了哪些？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%906%EF%BC%9A%E5%8C%BA%E9%97%B4%E5%90%88%E5%B9%B6%E7%9A%84%E5%9B%9B%E5%A4%84%E8%BE%B9%E7%95%8C%E9%97%AE%E9%A2%98%EF%BC%8CDeepSeek%E4%B8%80%E6%AC%A1%E4%BF%AE%E6%94%B9%E4%BF%AE%E5%A5%BD%E4%BA%86%E5%93%AA%E4%BA%9B%EF%BC%9F)

本页从原合并记录拆分，原始数据与历史提交保持不变；同一问题的后续复发、修复和实验继续按日期追加到本页。
