# 运行记录补全：两个可复现缺陷

日期：2026-09-14，UTC+08:00。历史对照版本：`85782f9cbe66099ec4247b8080407108d75b365b`。

## BUG-20260914-002：仓库准备失败后没有留下失败记录

上次真实运行结束后，我们只能事后补录 Agent commit 和完整配置；如果准备阶段就失败，记录还会更少。读取 runner.py 可以看到：它先保存 model.json，创建工作区后才进入 AgentLoop 的错误处理。prepare_repository 抛异常时不会经过 Loop，因此没有最终报告。

为了验证，没有调用付费模型，也没有等待偶发网络故障。对历史 runner 与修改后 runner 注入完全相同的 `RuntimeError("controlled-setup-failure")`，触发位置都是 WorkspaceManager.prepare_repository。

| 检查 | 修改前 | 修改后 |
| --- | --- | --- |
| 准备异常是否继续向调用方抛出 | 是 | 是 |
| model.json | 有 | 有 |
| metadata.json：开始时版本/配置 | 无 | 有 |
| runner-error.json：失败类型/运行 ID | 无 | 有 |
| manifest.json：产物校验清单 | 无 | 有 |

旧目录只有一个 model.json；新目录包含 agent-diff.json、metadata.json、model.json、runner-error.json、measurements.json 和 manifest.json。不是把异常吞掉让任务“成功”，而是保持失败语义并先落盘诊断信息。

修复放在 runner 的准备流程外围：先采集版本和脱敏配置；用异常处理保存错误类型；finally 汇总已有证据。目标仓库解析后单独记录 base_commit，不与 Agent commit 混淆。API Key 验证、可信本地仓库参数验证仍发生在正式运行创建之前；这些调用参数错误不是已启动的 Agent 任务。

回归测试 `test_setup_failure_has_start_snapshot_and_manifest` 使用相同故障注入，检查上述文件和敏感异常正文未泄露。成功运行测试同时检查 manifest 的 result.json 哈希，避免生成清单后又改报告而留下错误校验值。

这是受控准备异常测试，不是实际 GitHub 服务故障，也不证明模型能从代码修改失败中恢复。未跟踪源码仅保存哈希，磁盘不可写或 SIGKILL 的归档完整性也不在本次保证范围。

## BUG-20260914-003：服务返回的实际模型名称被丢弃

采集模型版本时发现，ModelReply 只有消息、结束原因、用量和响应 ID，HTTP 适配器也没有传递响应顶层的 model。即使服务返回具体版本，Trace 里也找不到它。

固定输入响应：`model = "provider-resolved-revision"`；固定断言：`reply.model_dump().get("model") == "provider-resolved-revision"`。

| 同一回归测试 | 实际字段 | 结果 |
| --- | --- | --- |
| 修改前 | None | 1 failed，AssertionError |
| 修改后 | provider-resolved-revision | 1 passed |

修复为 ModelReply 增加可空 model 字段，解析响应时透传 body.model。字段允许为空，因为兼容服务可能不返回它，不能用请求模型名伪装成服务实际返回名。measurements.json 保留这个字段；配置的模型名仍单独记录。

本实验使用 HTTP Mock，验证信息是否被保留，不证明服务返回的别名本身就是不可变的模型权重版本。后面的真实任务会记录服务实际返回的字符串。

## 开发反馈

初次检查出现两处新代码长行 E501，格式化/缩短行后消除；全目录格式化同时触及旧证据和 Markdown 代码块，已撤回这些无关格式改动，历史证据没有重新格式化覆盖。这些属于开发检查反馈，不计作模型任务失败。

首次完整工程测试为 80 passed；随后增加模型标识回归测试（先失败再修复），最终测试结果随本次交付记录更新。复现程序、前后原始输出和修复版本见本页的证据链接。
