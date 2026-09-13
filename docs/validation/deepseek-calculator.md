# DeepSeek 首次真实调用验证

日期：2026-09-14。运行 ID：`agent-dd31f7965c67`。

本记录来自真实模型调用；修复动作由 DeepSeek 生成，没有使用预编排的修改步骤。

| 项目 | 实际结果 |
| --- | --- |
| 配置模型 | deepseek-flash |
| 基准 commit | 240437985b8c4b36e5d0a7ab513d136a871f997d |
| 模型请求 | 6 |
| 工具调用（含 Runtime 检查） | 11 |
| 服务报告总 Token | 17688 |
| 估算 Token | 0 |
| 主运行耗时 | 7.65 秒 |
| 修改文件 | calculator.py |
| 原始公开测试 | 2 failed, 3 passed |
| 修改后公开测试 | 5 passed |
| 独立验证，应用前 | 9 failed, 20 passed |
| 独立验证，应用后 | 29 passed |

## Patch

```diff
diff --git a/calculator.py b/calculator.py
index 087027c58866a0e9283af1947fcadda021ee28e9..c40f4ac3bd37039faad4401105347c3c6340c6aa 100644
--- a/calculator.py
+++ b/calculator.py
@@ -2,6 +2,6 @@
 
 
 def add(a: int | float, b: int | float) -> int | float:
-    if not isinstance(a, int) or not isinstance(b, int):
+    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
         raise TypeError("arguments must be numbers")
     return a + b
```

模型未修改测试。工具轨迹包含列表、读取实现和测试、编辑、测试及 Diff；本次一次编辑即通过，没有发生失败修改后的重试，因此不能以此证明真实模型的失败恢复能力。

## 独立验证范围

在从同一基准 commit 创建的干净 worktree 中，先运行原始 5 个测试和 24 个新增检查，再应用导出 Patch 并重跑同一套测试。

新增检查包括：输入集合 `[0, 2, -3, 1.25]` 的 16 种两两组合，以及 `None`、字符串、列表、字典在左右参数位置的 8 种拒绝检查。这些检查在模型运行结束后创建，没有传入该次模型上下文。

这是单个可信示例的事后独立验证，不是预先冻结的隐藏 Benchmark，也不能推导真实 GitHub Issue 成功率或无回归保证。

完整本地产物位于 `runs/agent-dd31f7965c67/`，包括 `events.jsonl`、`messages.json`、`result.json`、`final.patch`、`independent-verification.json` 和 `independent-checks/`。它们保持 Git 忽略；本记录不包含密钥或原始模型推理内容。成功任务与独立验证 worktree 已清理。
