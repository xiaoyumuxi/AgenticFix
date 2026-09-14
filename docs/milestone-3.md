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

依赖和基础镜像可能使用可变版本；本轮记录实际解析值并干净重建验证，不宣称跨日期完全可复现。提示词需要根据实际失败再改，初轮还没有消融实验。

## 开发反馈待归档到 Wiki

初始 docker version 退出 1：OrbStack daemon 未启动、socket 不存在。启动本机 OrbStack 后版本查询成功，Docker Engine 29.4.0；该故障发生在模型运行前，属于宿主准备问题。

代码编辑初期 ruff 报长行和分号格式问题，经格式化及缩短行解决；不计作模型失败。验收逻辑检查时补上“原本失败的 Issue 用例必须变成 passed”，避免仅检查退出码和原有通过项、而把 skip 当成修复。本轮正式模型运行前已补齐。
