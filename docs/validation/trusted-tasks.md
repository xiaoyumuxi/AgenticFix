# 两个固定可信任务

这批任务用于补足 M2 的真实模型验证，不代表真实 GitHub Issue Benchmark。

- `order_total`：api.py → pricing.py / shipping.py，数量未参与小计，影响运费门槛。公开测试 3 项，独立检查 10 项。
- `intervals`：空输入、接触端点、嵌套区间和输入不变性。公开测试 5 项，独立检查 10 项。

公开代码和 Issue 在 `examples/<task>/`，预先冻结的独立测试在 `validation/<task>/`。运行脚本只把公开目录放入 Agent worktree，独立测试只放入验收 worktree。仍是自有可信代码，不是抵御恶意代码的隔离边界。

```bash
uv run python -m scripts.validate_tasks order_total
uv run python -m scripts.validate_tasks intervals
```

运行前提交代码、测试和配置变更；两次运行之间不要更改模型、Prompt 或预算。脚本在模型调用前保存测试定义哈希，在固定 base commit 的独立 worktree 跑基线，再应用模型 Patch。验收时恢复预先冻结的公开测试与 pytest.ini，逐个比较用例 ID，缺失用例不能算通过。保留 before/after JUnit、stdout、退出码、Patch、run_id 和任务摘要。

第一次修好就记录一次成功，未发生失败恢复时不宣称验证恢复能力。失败与成功都归档到 Wiki；不要删除失败运行后只报最好结果。

## 自动运行证据

`run_agent` 在准备仓库前写入 metadata.json（Agent commit、dirty 状态、配置、环境、锁文件和 Prompt 哈希）和 agent-diff.json（脱敏的已跟踪差异）。目标解析后写 task.json，包含固定 base_commit、Issue 和测试命令。

结束时保存 measurements.json 和 manifest.json。前者保留服务用量、实际返回模型、调用耗时和测试结果，不复制助手原文/推理；后者校验运行顶层产物，包括最终 result.json 和 Patch。异常退出的准备步骤有 runner-error.json，不保存可能包含密钥的异常原文。

未跟踪文件当前只记录哈希，不保存内容；因此 dirty 工作区有未跟踪源码时，不能声称快照可完整复现。正式比较使用干净提交。脱敏补丁若改变了原字节，其哈希和原补丁哈希分别保存。运行目录是本地证据，不等于允许直接公开：归档到主仓库或 Wiki 前仍审查脱敏内容。磁盘不可写/进程被强制杀死时不能保证生成完整清单。
