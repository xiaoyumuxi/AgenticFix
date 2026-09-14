# AgenticFix‐9：源码新增了配置，为什么pytest仍然说字段不存在？

记录 BUG-20260914-006，2026-09-14，Asia/Singapore（UTC+08:00）。状态：开发测试导入路径已修复。这个问题发生在构建日志压缩实验的工程验证阶段，还没有启动真实模型，不计入真实 Issue 失败次数。

## 如何发现

新增 `Settings.compact_successful_build` 后，`uv run pytest tests/test_agent_loop.py -q` 返回 **18 failed，9.17 秒**；完整 `uv run pytest -q` 返回 **20 failed、74 passed、1 skipped，18.92 秒**。三个新增用例直接报：

```text
ValueError: "Settings" object has no field "compact_successful_build"
```

旧的 Agent Loop 测试也失败，因为 Runtime 读取这个字段时产生 AttributeError，任务状态变为 failed。磁盘上当前 config.py 明明包含字段，但 fixture 创建出的 Settings 不包含它，因此先查导入来源，而不是修改模型逻辑或放宽断言。

## 找到两份不同的config.py

`uv run python` 加载仓库根目录的 config.py；pytest console script 则可能从 site-packages 加载安装时复制进去的 config.py。项目包采用 editable 安装，但 pyproject.toml 对顶层 config.py 使用 wheel.force-include，它不是随普通包目录一起动态引用的同一文件。

首次失败时保存的 config-copies.json 记录：工作区副本有 compact_successful_build，安装副本没有，SHA-256 不同。失败发生在未提交开发状态，所包含的新代码随后提交为 `d110e86e06b93ef0d5c63f682633d53d60f08a12`；首次失败前没有单独保存完整 dirty diff，不能把那次失败冒充该提交的原始成绩。

修改 pytest 配置时 uv 自动重新构建了 editable 包，安装副本也随之出现新字段。因此之后的 origin-before.txt/origin-after.txt 都打印 has_new_field=True；它们是后续补采，不能拿来否认最初缺字段，也不能把完整套件恢复全部归因于路径修改。

为了排除“重新安装恰好同步了副本”这一因素，又在同一个已同步环境里运行同一个路径断言，只改变 pytest 的 pythonpath 设置：

| 条件 | config.__file__ 实际位置 | 期望 | 结果 |
| --- | --- | --- | --- |
| `-o pythonpath=`，清空路径设置 | `.venv/lib/python3.12/site-packages/config.py` | 仓库根目录 config.py | 1 failed，exit 1 |
| 使用 `pythonpath = ["."]` | 仓库根目录 `config.py` | 仓库根目录 config.py | 1 passed，exit 0 |

这组对照证明路径修复本身有效，即使两份配置内容暂时相同，旧入口仍然会选错副本，后续编辑仍可能再次出现混用版本。

## 修改及验证

在 pyproject.toml 的 `[tool.pytest.ini_options]` 增加 `pythonpath = ["."]`，明确开发测试使用当前 checkout。新增 `test_development_tests_use_checkout_configuration` 检查真实导入路径。没有改 Agent 的预算、模型、Docker 测试命令或真实 Issue 验收条件。

加入路径设置后的完整测试为 **94 passed、1 skipped，27.10 秒**；加入路径回归断言后的最终套件为 **95 passed、1 skipped，26.91 秒**。两组测试数量不同，不能直接作为同一测试集的前后成功数；直接因果对照是上面的单项路径检查。最终 mypy 检查 32 个源文件通过，工程源码范围 ruff 通过。

修复提交：`bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c`。这只保证开发测试入口的来源，不表示已经重构顶层配置模块或完成独立安装包的全部兼容性验证。

## 本轮开发反馈

路径回归测试初稿漏导入 pathlib.Path，产生 NameError/F821；补齐导入后才进行上面的路径对照。两份初稿失败输出也保留。首次检查时误读不存在的 agent/context.py、tests/test_agent.py，随后通过文件清单定位实际模块，没有修改任何文件来掩盖错误。

一次 `ruff check .` 扫描到历史证据目录，报告 13 条已有格式问题；工程源码范围检查通过，未批量格式化历史证据，避免改动旧实验。此类命令/格式反馈集中记在这里，不算模型运行失败。

## 固定版本证据

[首次完整失败](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/full-before.txt) · [首次局部失败](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/targeted-before.txt) · [两份配置哈希](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/config-copies.json) · [同环境路径失败](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/path-test-before.txt) · [同环境路径通过](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/path-test-after.txt) · [最终95项工程结果](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/full-final.txt) · [导入来源探针](https://github.com/xiaoyumuxi/AgenticFix/blob/bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c/docs/iteration-evidence/BUG-20260914-006/probe.py)。

复现路径对照：`uv run pytest tests/test_foundation.py::test_development_tests_use_checkout_configuration -q -o pythonpath=` 与去掉最后的 `-o pythonpath=`。这两个命令的区别仅为路径配置，预期分别失败和通过。

首次保存的文件证据：

| 路径 | 有新增字段 | SHA-256 |
| --- | --- | --- |
| `config.py` | True | `7e6c556b7290c86ca721f59d724b42ab732bf77fcba430de0d6fbd998813d3df` |
| `.venv/lib/python3.12/site-packages/config.py` | False | `8feb07faefc262f1de3b01877b955a2be63c74840a1ae91e1eb2a5146d82842e` |


## 同根因追加：位于/tmp的辅助脚本也会导入安装副本

归档008时，`uv run python /tmp/archive-m3-fifth.py` 再次读到安装副本，找不到后加的 retained_read_results；此时 pytest 的修复仍有效，因为临时脚本不走 pytest 配置。改用 `PYTHONPATH=. uv run python /tmp/archive-m3-fifth.py` 后完成归档。前一失败导致随后读取尚未生成的预算快照、调用尚未生成的探针模块也失败，完整重跑生成步骤后恢复。这验证了修复范围只覆盖开发测试；临时项目脚本必须使用明确的模块/导入路径。

另一次诊断误用系统 python3，缺少 httpx；改为 uv run python 后完成。以上是事后归档错误，没有影响008运行时已保存的配置和原始结果。辅助步骤初始失败完整控制台未独立归档，以上为过程补录。
