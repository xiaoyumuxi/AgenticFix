# AgenticFix‐7：Docker没有启动时如何留证，环境构建如何验收？

记录日期：2026-09-14，Asia/Singapore（UTC+08:00）。本页记录第三阶段的环境实现与开发失败；真实模型的三轮数据见 [AgenticFix‐8：Patch通过729项验证，为什么三轮仍然没有完成任务？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)。

## ENV-20260914-001：客户端存在，但 Docker daemon 没启动

开始检查时，`docker version` 退出码是 **1**：客户端为 **29.4.0**、context 为 **orbstack**，连接 `.orbstack/run/docker.sock` 时返回 `no such file or directory`。这时尚未调用模型，不能算一次模型环境构建失败。

执行 `open -a OrbStack` 后，再查询能连接 **Docker Engine 29.4.0**，buildx 为 **v0.33.0**。这排除了“缺少 Docker CLI”，说明当时缺的是运行中的 daemon。错误摘要来自当时工具输出的补录，原始完整控制台输出没有归档；不冒充模型 Trace。[故障补录](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/ENV-20260914-001/initial-daemon-failure.json)。

## worktree 与 Docker 分别负责什么

Git worktree 固定修复前版本、保存模型编辑并导出 Patch。真实仓库的 Python 代码全部在 Docker 里运行。模型通过 `build_environment(dockerfile)` 提交 Dockerfile，宿主工具负责构建；构建日志返回模型，环境构建与源码修复共享预算。构建失败可以继续改 Dockerfile，运行测试之前必须已有成功镜像。

模型可以选择单阶段官方 Python 3.10～3.14 slim、安装依赖。宿主工具不提供这个 Issue 的预制 Dockerfile。构建快照排除 `.git`、`.env` 和缓存，拒绝符号链接与硬链接。Git 历史、官方修复和独立验收文件不进入模型看到的源码快照。

| 条件 | 实际设置 |
| --- | --- |
| 构建 | 每次独立 docker-container BuildKit builder，`--no-cache`，结束删除 builder |
| 构建资源 | 2 CPU、2 GiB 内存、内存加交换总量 2 GiB，单次 300 秒 |
| 构建网络 | 允许下载基础镜像和依赖 |
| 测试资源 | 2 CPU、1 GiB 内存、内存加交换总量 1 GiB、128 PID，单次 120 秒 |
| 测试权限 | UID/GID 65534，无 capabilities，no-new-privileges，关闭网络 |
| 测试文件系统 | 根文件系统与 /workspace 只读，/tmp 为 128 MiB tmpfs，/results 可写 |
| 超时/取消 | 强制删除任务容器；失败有效重建不继续使用旧镜像 |

构建资源参数依据 [Docker 的 docker-container driver 文档](https://docs.docker.com/build/builders/drivers/docker-container/)。这里有构建网络与可写结果目录，不能写成“完全封闭沙箱”。镜像会保留供复核，尚无 TTL 和独立磁盘配额；也不支持系统服务、多阶段镜像、仓库链接文件或多容器项目。

## 工程实测：不是只看 Dockerfile 能否 build

实际 Docker 集成测试为 **1 passed，27.84 秒**。容器内验证非 root、没有 `.git/.env`、源码写入被拒绝、结果目录可以写入。另执行睡眠 60 秒的进程并给 1 秒超时，结果 timed_out=true，后续 inspect 已找不到任务容器。对应 [集成测试结果](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/ENV-20260914-001/docker-integration.txt)、[构建](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/ENV-20260914-001/smoke-build.json)、[权限探针](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/ENV-20260914-001/smoke-run.json)、[超时清理](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/ENV-20260914-001/smoke-timeout.json)。

最终工程测试 **91 passed、1 skipped，29.10 秒**，跳过项就是上述单独执行的真实 Docker 集成测试。ruff check/format、mypy（32 个源文件）与 sdist/wheel 构建通过。[完整测试输出](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/ENV-20260914-001/full-tests-final.txt)。这些是 Agent 工程测试，不是上游 Issue 的 729 项验证。

## 开发中出现的其他问题

**DEV-20260914-001，格式与辅助命令反馈，已处理。** 编写代码期间 ruff 报 E501 长行和 E702 分号，调整并格式化后通过。归档辅助脚本误用系统 Python，因没有 pydantic 导入失败，改为项目的 `uv run python` 后归档成功。Wiki 表格生成脚本还出现一次 int/string 拼接 TypeError，转为字符串后恢复，未改动原始实验数据。另有一次检查命令误读不存在的 `full-tests.txt`，实际文件为 `full-tests-final.txt`，没有丢失测试结果。这些发生在开发/归档步骤，不混入三次模型修复失败统计。早期完整输出及逐步 dirty diff 未全部保存，以上为开发过程补录。

**BUG-20260914-004，验收不能把 skip 当作修复，运行前检查发现并修正。** 初稿验收条件检查退出码、原有通过项和用例存在性；仅这些条件不足以排除 Issue 用例变成 skipped。正式运行前增加“基线失败的 Issue 用例，在候选版本必须逐项为 passed”。本轮没有出现错误成功报告，不能虚构修复前的真实模型成功数；这是代码审查发现的缺口。实现包含于 `1d43d4ce68f181b570d1f823058a2b3f8c8759e9`，可核对 [验收逻辑](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/scripts/run_real_issue.py)。

**ENV-20260914-002，pytest 缓存警告，保留现状。** 三轮公开测试都返回退出码 0，但 pytest 尝试在只读 /workspace 写 `.pytest_cache`，产生 `PytestCacheWarning` / `Errno 30`。这符合只读设置，未导致测试失败；后续可把缓存目录设到 /tmp 或关闭 cacheprovider。此次未改变命令，避免混入提示词对照。警告保存在各轮 measurements.json。

实现提交：`1d43d4ce68f181b570d1f823058a2b3f8c8759e9`。当时工程开发包含未提交过程；三轮正式模型运行则各自保存了干净提交、环境、Prompt 与依赖锁哈希。当前能力已支持“模型写 Dockerfile → 构建 → 测试”，但尚未观察到真实依赖安装失败后的模型恢复；这需要后续任务检验。

后续上下文实验中的测试入口与辅助脚本导入错误，另见 [AgenticFix‐9：源码新增了配置，为什么pytest仍然说字段不存在？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%909%EF%BC%9A%E6%BA%90%E7%A0%81%E6%96%B0%E5%A2%9E%E4%BA%86%E9%85%8D%E7%BD%AE%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88pytest%E4%BB%8D%E7%84%B6%E8%AF%B4%E5%AD%97%E6%AE%B5%E4%B8%8D%E5%AD%98%E5%9C%A8%EF%BC%9F)（BUG-20260914-006），不混入此页环境失败计数。


## 2026-09-14 追加：RUN-20260914-009的只读缓存警告

ENV-20260914-002在三次公开测试再次出现：基线、模型修改后、Runtime收尾均715通过、exit_code=0，各有一次`PytestCacheWarning`，原因仍是`/workspace`只读而pytest尝试写`.pytest_cache`。独立验收使用`-p no:cacheprovider`，729项通过。没有新增环境失败；本次模型与评测端各成功构建一次。模型Dockerfile仅安装pytest，实际Python3.10.21、pytest9.1.1。完整比较和固定证据见[本次记录](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)。
