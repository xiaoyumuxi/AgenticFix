# 提示词变更记录

记录实际运行使用的完整system prompt，包括通用SYSTEM_PROMPT与环境附加段。版本名用于选择策略，SHA-256用于确认实际文本；读取上限、构建日志摘要、预算属于Runtime配置，不冒充提示词修改。

| 版本 | 引入提交 | 改动原因及内容 | 首次真实运行 |
| --- | --- | --- | --- |
| environment-v1 | 1d43d4ce68f181b570d1f823058a2b3f8c8759e9 | 将依赖识别、模型编写Dockerfile、构建和基线测试纳入任务；明确容器限制和环境失败反馈 | RUN-20260914-004 |
| environment-v2 | 9b50dcc3ae599df18630955528116b7d18beccb0 | 004构建前读取15次文件；增加环境发现最多3次读取、先构建和测试、之后按符号读取通常不超过80行 | RUN-20260914-005 |
| environment-v3 | c1dc3cdb69d6d07532b9c6e96f3fbdd2aca9dd40 | 007已修复并测试却预算停止，008删旧读取内容仍未编辑；增加证据足够后修改、修改后优先测试、测试通过后完成交付 | RUN-20260914-009 |

v3相对v2新增的原文如下，没有给出特定Issue的修复代码：

```text
Complete the repair within the run budget. Once you have read the relevant implementation and
public tests and can explain the failing behavior from the issue, make the smallest supported
edit. Do not keep surveying neighboring code without a specific unresolved question.
After editing implementation and any regression tests, prioritize run_tests over further reading.
If tests fail, investigate the concrete failure and revise. If the current default tests pass
and your patch addresses the issue, return your final summary immediately; the runtime will run
its own final verification and export the patch. Do not restart discovery or add unrelated changes.
```

| 完整提示词版本 | SHA-256 |
| --- | --- |
| environment-v1 | ecd482a2b8b2ba6d4250312eddeb0b76745b607b96cdc0f833164b8fa9adfdc4 |
| environment-v2 | 0099a4633bfbf657117a560e617b09de3a51bee3ad6e69cc2bfd146a53183f9a |
| environment-v3 | 8ae2568bf76dad69693752f5583c15e719c1e7346a5c78ce6c4e6dcab8db89a7 |

截至009：v1一次端到端失败；v2四次不同Runtime配置下均端到端失败（其中三次候选Patch通过）；v3一次成功。不能将混有不同Runtime配置的这些历史运行用作严格提示词A/B结论。预算和验收一致并不意味着其余全部条件一致。

009使用v3、80行上限、成功构建摘要、保留全部读取正文。默认配置仍是v1，不因一次成功替换所有默认值。010、011为预先决定的两次重复验证，沿用009的提示词与配置，不根据中间结果临时换提示词。

后续修改必须新增版本，保留旧文本；运行开始时保存提示词全文/哈希、Agent提交与配置，记录修改动机、同条件数据和适用范围。失败运行与成功运行都关联Wiki。若后续确需纠正旧记录，注明纠错原因，不覆盖已有证据。

当前优先级：先完成固定配置重复验证；再补第二个真实Issue（优先有真实测试依赖的项目），测试跨任务适用性；随后用固定的缺依赖故障场景比较Docker错误反馈前后恢复情况。预算优化需记录输入预留和服务实际usage，不能直接将字节数除以经验常数当作严格费用上界。

重复验证结果：010成功（13次请求、111770 Token），011失败（13次请求、107270 Token，错误测试+编辑后未重新读取+token_budget）。v3累计2/3完整成功；本轮不更改默认值。

[完整Wiki记录](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F) · [错误用例诊断](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%9011%EF%BC%9A%E5%AE%9E%E7%8E%B0%E6%94%B9%E5%AF%B9%E4%BA%86%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E6%A8%A1%E5%9E%8B%E6%96%B0%E5%A2%9E%E7%9A%84%E6%B5%8B%E8%AF%95%E5%8F%8D%E8%80%8C%E9%94%99%E4%BA%86%EF%BC%9F)。三轮实际提示词全文固定证据：

- [RUN-009完整提示词](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-009/prompt.json)
- [RUN-010完整提示词](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-010/prompt.json)
- [RUN-011完整提示词](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/prompt.json)
