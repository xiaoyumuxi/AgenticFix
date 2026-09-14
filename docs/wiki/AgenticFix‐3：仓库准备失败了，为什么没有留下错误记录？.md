# AgenticFix-3：仓库准备失败了，为什么没有留下错误记录？

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

## 开发反馈

初次检查出现两处新代码长行 E501，格式化/缩短行后消除；全目录格式化同时触及旧证据和 Markdown 代码块，已撤回这些无关格式改动，历史证据没有重新格式化覆盖。这些属于开发检查反馈，不计作模型任务失败。

首次完整工程测试为 80 passed；随后增加模型标识回归测试（先失败再修复），最终完整测试为 **81 passed（32.53 秒）**；ruff 检查/格式检查通过，mypy 严格检查 29 个源文件通过，sdist/wheel 构建通过。复现程序、前后原始输出和修复版本见本页的证据链接。

## 归档文件逐项对比

以下直接展开已保存的 clean-version-result.json。故障注入位置相同：prepare_repository；抛出相同 RuntimeError。下表只比较这次准备失败留下的 JSON 文件，不把本来就没开始的模型步骤算成丢失。

| 文件 / 指标 | 旧 runner | 修复后 runner | 这项数据解决什么问题 |
| --- | --- | --- | --- |
| agent-diff.json | 无 | 有 | 已跟踪差异的脱敏副本 |
| manifest.json | 无 | 有 | 已写入产物的校验清单 |
| measurements.json | 无 | 有 | 已有调用/测试摘要；准备失败时尚无调用 |
| metadata.json | 无 | 有 | 运行开始时 Agent 版本、配置、环境 |
| model.json | 有 | 有 | 请求模型基本信息 |
| runner-error.json | 无 | 有 | 运行 ID、failed 状态、异常类型 |
| 顶层 JSON 文件数 | 1 | 6 | 多出 5 项诊断产物 |

故障发生在目标仓库解析之前，两边都未获得 target base_commit，也都没有执行模型请求或测试。不能用 Agent commit 填补目标 commit；本次也没有 Patch 可评价。旧程序和新程序都向调用方抛出异常，复现脚本在外层捕获后检查目录，所以不能把脚本正常结束解释成任务修好了。

这份历史对照归档保存了文件名和存在性，没有保存这次临时目录内每个 JSON 的完整内容。因此这里不编造当时的 run_id、每个文件的字节数或耗时，也不把新版本另一次真实运行的 metadata 冒充本次故障记录。

## 修复版本与固定证据

修复提交：[完整代码差异](https://github.com/xiaoyumuxi/AgenticFix/commit/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1)。两条缺陷原版本均为 `85782f9cbe66099ec4247b8080407108d75b365b`；初次验证发生在开发工作区，准备故障随后在干净 `66f48ec0e6fbdbf6705a733bbadca87283ee5fa1` 上重复，结果一致。

- BUG-002：[复现程序](https://github.com/xiaoyumuxi/AgenticFix/blob/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/docs/iteration-evidence/BUG-20260914-002/reproduce.py)、[干净版本对照结果](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/BUG-20260914-002/clean-version-result.json)、[版本/命令上下文](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/BUG-20260914-002/clean-version-context.json)。

复现命令（在主仓库根目录）：

```bash
uv run python -m docs.iteration-evidence.BUG-20260914-002.reproduce
```

## 相关记录

[AgenticFix-4：服务返回了模型名称，为什么运行记录里没有？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%904%EF%BC%9A%E6%9C%8D%E5%8A%A1%E8%BF%94%E5%9B%9E%E4%BA%86%E6%A8%A1%E5%9E%8B%E5%90%8D%E7%A7%B0%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E8%BF%90%E8%A1%8C%E8%AE%B0%E5%BD%95%E9%87%8C%E6%B2%A1%E6%9C%89%EF%BC%9F)

本页从原合并记录拆分，原始数据与历史提交保持不变；同一问题的后续复发、修复和实验继续按日期追加到本页。
