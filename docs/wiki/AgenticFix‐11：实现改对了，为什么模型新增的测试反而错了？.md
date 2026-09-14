# AgenticFix‐11：实现改对了，为什么模型新增的测试反而错了？

BUG-20260914-008，2026-09-14，Asia/Singapore（UTC+08）。发生于RUN-20260914-011；状态：模型运行失败，错误已复现，事后只纠正测试输入的诊断对照通过。原始Patch保留，没有把人工诊断改成模型成功。

## 发现：729项独立验收通过，交付的测试却不正确

011的实现为`__reversed__`增加`if self._len == 0: return iter(())`，通过全部729项独立验收。但独立评测会恢复原始715项回归测试，再加冻结的14项验收；模型自己写的测试不包含在这729项里。因此“独立验收通过”和“交付的测试也能通过”是不同结论。

在第12次模型请求中，它向`test_reversed`加入四组输入：

| 输入 | 模型写入的预期 | 实际语义 | 判断 |
| --- | --- | --- | --- |
| `(0,)` | `[]` | 空范围，反转`[]` | 正确 |
| `(1.0, 1.0)` | `[]` | 起止相等，反转`[]` | 正确 |
| `(1.0, 0.0)` | `[]` | 默认步长+1，与方向不符，反转`[]` | 正确 |
| `(1.0, 0.0, -1.0)` | `[]` | 从1.0开始、步长-1、终点0.0不包含，反转`[1.0]` | **错误** |

第13次请求尝试将最后一组改为`(0.0, 1.0, -1.0)`，这是起点0、终点1、负步长的空范围，预期`[]`正确。但上一次编辑后read版本凭据已经失效，它未重新读取文件，工具返回`success=false / NOT_INSPECTED`，错误原文`Read this file before editing with its version`。没有发生第三次实际编辑，workspace_revision仍为2。

这个路径保护按设计工作：提示词本来已经要求编辑后重新读取。当前事实是模型没有遵守，不能据此删掉版本检查或宣称工具误拒绝。第13次请求结束后，服务累计报告107270 Token；预算150000，剩42730，下一次输入预留49139，所以Runtime以token_budget停止，没有再请求模型、更没有执行修改后的公开测试。完整顺序和用量见[预算与重复运行记录](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)。

## Docker补采排除了什么

运行结束后，另在Docker中保留原始011 Patch，定点执行：

```bash
python -m pytest -q -o addopts= -p no:cacheprovider tests/test_more.py::NumericRangeTests::test_reversed
```

实际失败：`AssertionError: Lists differ: [] != [1.0]`，1 failed，exit_code=1。随后在独立干净worktree再次应用同一原始Patch，重跑确认失败，只替换一组测试输入，源码实现不变：

```diff
-            ((1.0, 0.0, -1.0), []),
+            ((0.0, 1.0, -1.0), []),
```

| 对照 | 源码 | 测试输入 | 测试结果 | 退出码 |
| --- | --- | --- | --- | --- |
| 原始模型Patch | 同一空范围修复 | 非空范围，却预期空 | 1 failed | 1 |
| 事后诊断修正 | 不变 | 真正的空范围，预期空 | 1 passed | 0 |

这支持该失败来自错误测试输入/预期配对，而非模型实现对这组输入返回错误。只跑了这个测试方法，没有把定点通过冒充修正Patch的完整回归通过。所有补采均无模型API调用、不增加原始运行Token，也没有将人工修正写回原始失败Patch。原始729项独立验收详细输入、base/官方/候选实际值保存在同页关联的011记录。

## 版本和证据

run_id `agent-38f2d2d08252`，开始UTC `2026-09-14T04:53:57.600637+00:00`。Agent `deb74899647f5ab363548fc680487ee82318d524`，开始dirty=false；目标base `247e15b3a489d5805375c95dfa79486c9bd0eb1b`、官方修复`1806a75b836b9eff4a7885a96ece6183f5fb6409`，均为more-itertools/more-itertools Issue #1152。

请求与返回模型deepseek-flash，API https://api.deepseek.com，extra_body={}，temperature未指定。environment-v3完整SHA-256`8ae2568bf76dad69693752f5583c15e719c1e7346a5c78ce6c4e6dcab8db89a7`；uv.lock SHA-256`8256210a762f06efc6bed4bbb655daeafefc851ffb2ef343cd0b63c269ef24df`。模型13次请求、19次工具调用、107270服务报告Token、估算入账0。Loop81.06秒，含独立验收162.29秒。模型新增测试未执行；原始公开基线715通过；独立base7失败/722通过、官方729通过、候选729通过，端到端solved=false。

补采使用原运行镜像`sha256:7f452ecfe1a00e70a2c1417c8487d5f4e162868b8f2c088de2ee2eb75bbf2f30`，只读容器和禁网测试规则不变。Patch SHA-256`e9e039758a714e740b80772fb79b6613a81628cc08e1e56bfa8d6ffdbcf53056`。

[原始失败Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/candidate.patch) · [三次编辑参数和结果](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/edit-attempts.json) · [只改测试输入的前后结果](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/test-expectation-comparison.json) · [可复现Docker对照脚本](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/replay_test_expectation.py) · [原始独立验收](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/summary.json) · [配置快照](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/metadata.json) · [公开文件SHA-256](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/archive-manifest.json)。

后续优先让模型在新增用例时明确核对输入与预期，在编辑错误反馈中给出下一步可执行提示，并提前观察预算余量。当前system prompt已经写有重新读取要求；需要用同样失败条件验证新反馈是否改变行为，而不能仅多写一句规则就认为修好了。默认提示词本轮未改，也没有引入v4。
