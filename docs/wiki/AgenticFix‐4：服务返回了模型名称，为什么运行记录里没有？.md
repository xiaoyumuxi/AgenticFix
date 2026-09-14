# AgenticFix-4：服务返回了模型名称，为什么运行记录里没有？

日期：2026-09-14，UTC+08:00。历史对照版本：`85782f9cbe66099ec4247b8080407108d75b365b`。

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

首次完整工程测试为 80 passed；随后增加模型标识回归测试（先失败再修复），最终完整测试为 **81 passed（32.53 秒）**；ruff 检查/格式检查通过，mypy 严格检查 29 个源文件通过，sdist/wheel 构建通过。复现程序、前后原始输出和修复版本见本页的证据链接。

## 修复版本与固定证据

修复提交：[完整代码差异](https://github.com/xiaoyumuxi/AgenticFix/commit/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1)。两条缺陷原版本均为 `85782f9cbe66099ec4247b8080407108d75b365b`；初次验证发生在开发工作区，准备故障随后在干净 `66f48ec0e6fbdbf6705a733bbadca87283ee5fa1` 上重复，结果一致。

- BUG-002：[复现程序](https://github.com/xiaoyumuxi/AgenticFix/blob/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/docs/iteration-evidence/BUG-20260914-002/reproduce.py)、[干净版本对照结果](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/BUG-20260914-002/clean-version-result.json)、[版本/命令上下文](https://github.com/xiaoyumuxi/AgenticFix/blob/b975fcf45ad903e31e28e4ff4cd608ce0ec070cf/docs/iteration-evidence/BUG-20260914-002/clean-version-context.json)。
- BUG-003：[修改前断言失败](https://github.com/xiaoyumuxi/AgenticFix/blob/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/docs/iteration-evidence/BUG-20260914-003/before.txt)、[相同测试修改后通过](https://github.com/xiaoyumuxi/AgenticFix/blob/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/docs/iteration-evidence/BUG-20260914-003/after.txt)、[回归测试源码](https://github.com/xiaoyumuxi/AgenticFix/blob/66f48ec0e6fbdbf6705a733bbadca87283ee5fa1/tests/test_llm.py)。

复现命令（在主仓库根目录）：

```bash
uv run python -m docs.iteration-evidence.BUG-20260914-002.reproduce
uv run pytest -q tests/test_llm.py::test_response_model_identifier_is_preserved
```

## 相关记录

[AgenticFix-3：仓库准备失败了，为什么没有留下错误记录？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%903%EF%BC%9A%E4%BB%93%E5%BA%93%E5%87%86%E5%A4%87%E5%A4%B1%E8%B4%A5%E4%BA%86%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E6%B2%A1%E6%9C%89%E7%95%99%E4%B8%8B%E9%94%99%E8%AF%AF%E8%AE%B0%E5%BD%95%EF%BC%9F)

本页从原合并记录拆分，原始数据与历史提交保持不变；同一问题的后续复发、修复和实验继续按日期追加到本页。
