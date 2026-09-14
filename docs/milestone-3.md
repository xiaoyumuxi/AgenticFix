# 第三阶段：模型准备环境并处理真实 Issue

本轮用户要求：环境准备、Dockerfile 编写、依赖安装、构建失败后的提示词迭代，都计入端到端任务，而不是预先替模型准备好环境。

第一项固定任务为 more-itertools #1152：反转空 numeric_range 应返回空列表，实际抛出 IndexError。目标 base 为 `247e15b3a489d5805375c95dfa79486c9bd0eb1b`，官方修复为 `1806a75b836b9eff4a7885a96ece6183f5fb6409`，任务定义在 eval/tasks/more-itertools-1152。

## 这次实现

- sandbox/docker.py：模型 Dockerfile 使用单阶段官方 Python slim；快照不含 .git/.env、拒绝链接；构建在独立 BuildKit 容器中限 CPU/内存，每次冷构建后清理 builder。测试关闭网络、非 root、只读源码、限制 CPU/内存/PID，超时清理容器。
- build_environment：模型提供 Dockerfile，工具执行并返回构建日志；Dockerfile、每次 CLI 结果、镜像标识存入运行产物，不混入源码 Patch。
- Agent Loop 在 Docker 模式先让模型检查环境。环境构建与修复共享预算；测试不能回退到宿主机。
- 环境提示词 environment-v1 的原文和哈希随运行保存。首次预算：150000 Token、30 次模型请求上限、60 次工具调用、900 秒 Loop、300 秒单次构建、120 秒单次测试。
- scripts/run_real_issue.py：模型仅获得原 Issue 和修复前代码；独立端重新构建模型的 Dockerfile，固定原测试 + 14 个验收用例，分别验证基线、官方源码修复、Agent Patch，并检查新增失败/缺失用例。官方修复只供验收端读取。

## 已做检查

Docker 实测：1 passed，27.84 秒。验证非 root、没有 .git/.env、源码不能写、结果目录可写；1 秒超时终止 60 秒睡眠，随后 inspect 找不到容器。

离线工程测试第一轮 90 passed、1 skipped（真实 Docker 测试单独执行），27.37 秒。后续新增测试和真实运行结果会追加，不把待运行写成已通过。

## 范围与已知限制

这是第一个真实任务，单阶段 Python 镜像且不支持仓库符号链接、系统服务、多容器项目。网络在构建期间允许下载依赖，测试阶段关闭；不是网络完全隔离。模型不能设置 privileged、宿主挂载、Docker socket、secret mount 或自定义 frontend。镜像保留供复核，尚无镜像 TTL；磁盘额度尚未独立限制，构建受超时及 builder 内存/CPU 限制。

依赖和基础镜像可能使用可变版本；本轮记录实际解析值并干净重建验证，不宣称跨日期完全可复现。提示词需要根据实际失败再改，三轮不同条件尝试已完成，但每个条件只有一次；详见下面追加数据。

## 开发反馈（已整理至 Wiki）

初始 docker version 退出 1：OrbStack daemon 未启动、socket 不存在。启动本机 OrbStack 后版本查询成功，Docker Engine 29.4.0；该故障发生在模型运行前，属于宿主准备问题。

代码编辑初期 ruff 报长行和分号格式问题，经格式化及缩短行解决；不计作模型失败。验收逻辑检查时补上“原本失败的 Issue 用例必须变成 passed”，避免仅检查退出码和原有通过项、而把 skip 当成修复。本轮正式模型运行前已补齐。

## 2026-09-14 三轮真实结果

| 记录 | Prompt / 单次读取行数 | 请求 / 工具 | 服务报告 Token | 原始715项 + 独立14项，base → 候选 | Runtime |
| --- | --- | --- | ---: | --- | --- |
| 004 | v1 / 400 | 9 / 22 | 98,264 | 7失败/722通过 → 729通过 | token_budget |
| 005 | v2 / 400 | 10 / 19 | 98,113 | 7失败/722通过 → 729通过 | token_budget |
| 006 | v2 / 80 | 13 / 17 | 119,879 | 7失败/722通过 → 729通过 | token_budget |

每轮模型自行成功构建一次环境，评测端再独立冷构建一次。三个 Patch 均通过，但三次端到端任务都失败；不把验收端额外完成的测试算作模型闭环完成。单次读取收紧后，上下文字节数下降、累计请求与 Token 反而上升，暂不改变默认值。直接停止条件为剩余预算小于 UTF-8 字节数加256的输入预留；下一轮需要测量和改进上下文与预算策略。

最终工程测试 91 passed、1 skipped，29.10 秒，真实 Docker 集成测试另外 1 passed，27.84 秒。ruff、mypy 和包构建通过。前文 90 项是较早开发检查，不能与最终测试集当成同条件修复对照。

三轮运行提交依次为 `1d43d4ce68f181b570d1f823058a2b3f8c8759e9`、`9b50dcc3ae599df18630955528116b7d18beccb0`、`90ca7cc8c8ede5db0d5442763d1f1efec7b5ede7`，均干净；证据归档到 `a5bf74ea5a52c7575088584183ba4e873553ec68`。第三阶段还未完成五任务 Mini Benchmark。

Wiki：[AgenticFix‐7：Docker没有启动时如何留证，环境构建如何验收？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%907%EF%BC%9ADocker%E6%B2%A1%E6%9C%89%E5%90%AF%E5%8A%A8%E6%97%B6%E5%A6%82%E4%BD%95%E7%95%99%E8%AF%81%EF%BC%8C%E7%8E%AF%E5%A2%83%E6%9E%84%E5%BB%BA%E5%A6%82%E4%BD%95%E9%AA%8C%E6%94%B6%EF%BC%9F)、[AgenticFix‐8：Patch通过729项验证，为什么三轮仍然没有完成任务？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)。本地镜像位于 docs/wiki，同步记录 daemon 未启动、缓存写入警告、开发格式与归档脚本错误，以及验收状态检查缺口。

## 同日追加：两次上下文对照与测试入口修复

新增007成功构建消息摘要：16次请求、110,356 Token，候选729通过，Runtime预算停止。新增008再保留最近3次读取正文：15次请求、118,525 Token，没有编辑，候选仍7失败/722通过。预算150,000、目标版本和验收未变；两项策略默认关闭，尚未获得端到端成功。逐请求预留和服务实际输入量已归档。

另外发现开发pytest混用当前包与旧的安装副本config.py。通过显式pythonpath及来源断言修复，修复提交bf523a4e978fb4c0e1d0b8ec7d61ca2add289f3c；临时脚本也需显式项目导入路径，修复范围不能泛化为所有启动入口。最终工程测试96 passed、1 skipped，28.08秒，mypy与ruff通过。

完整数据追加至 [AgenticFix‐8：Patch通过729项验证，为什么三轮仍然没有完成任务？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)，独立工程问题见 [AgenticFix‐9：源码新增了配置，为什么pytest仍然说字段不存在？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%909%EF%BC%9A%E6%BA%90%E7%A0%81%E6%96%B0%E5%A2%9E%E4%BA%86%E9%85%8D%E7%BD%AE%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88pytest%E4%BB%8D%E7%84%B6%E8%AF%B4%E5%AD%97%E6%AE%B5%E4%B8%8D%E5%AD%98%E5%9C%A8%EF%BC%9F)。下一步优先验证请求预算估算，不继续无依据叠加正文删除规则。

## 环境错误反馈修复

长构建/测试失败现在保留结构化状态、日志头尾和有界疑似错误行。真实Docker故障注入与同输入消息对照验证错误可见，消息12258字符→6004字符；未测量真实模型Token或重试收益。中间错误的头尾遗漏也已记录并补充确定性测试。完整工程测试99 passed、1 skipped，28.41秒。详见 [AgenticFix‐10：Docker报了缺依赖，为什么模型只看到下载进度？](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%9010%EF%BC%9ADocker%E6%8A%A5%E4%BA%86%E7%BC%BA%E4%BE%9D%E8%B5%96%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E6%A8%A1%E5%9E%8B%E5%8F%AA%E7%9C%8B%E5%88%B0%E4%B8%8B%E8%BD%BD%E8%BF%9B%E5%BA%A6%EF%BC%9F)。


## 2026-09-14：首个真实Issue端到端完成

RUN-20260914-009在相同more-itertools #1152 base与固定729项验收上完成：DeepSeek自建Docker环境、修复空范围反转、增加4组公开测试输入、测试并提交完成答复。Runtime completed；独立验证从7失败/722通过变为729全通过，无新增回归、无缺失用例。

15次模型请求、20次工具调用（含Runtime收尾2次）、110534服务报告Token，估算入账0；Loop89.59秒，含独立冷重建/验收总164.78秒。总预算仍150000。主要调整environment-v3的修改→测试→交付顺序，以007构建摘要配置为参照，关闭008的旧读取正文删除。单次成功不能证明稳定提示词收益，默认配置暂未改变。

提示词提交`c1dc3cdb69d6d07532b9c6e96f3fbdd2aca9dd40`；证据提交`cca439b44c1292b3b2bee7face13ce7dd975f99f`。累计同一Issue6次尝试，端到端1/6、候选验收5/6，不代表6个独立任务。工程测试99 passed、1 skipped（28.62秒），ruff/mypy通过。

[完整Wiki前后比较与逐次用量](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F) · [已验证Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/candidate.patch) · [独立验收结果](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/summary.json)。
