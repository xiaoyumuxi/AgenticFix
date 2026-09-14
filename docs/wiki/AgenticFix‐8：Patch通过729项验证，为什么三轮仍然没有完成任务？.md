# AgenticFix‐8：Patch通过729项验证，为什么三轮仍然没有完成任务？

记录日期：2026-09-14，Asia/Singapore（UTC+08:00）。RUN-20260914-004/005/006 均已完成测量，**三次候选 Patch 验收通过，三次端到端任务失败**。失败记录 BUG-20260914-005：上下文累积与保守预算预留使任务在完成前停止。状态：已定位直接停止条件，尚未修复；两次优化尝试都没有改善端到端结果。

## 为什么选这个项目

真实问题是 [more-itertools #1152：Minor bug in numeric_range()](https://github.com/more-itertools/more-itertools/issues/1152)，2026-04-10 提出，2026-04-13 关闭。修复前仓库只有 **39 个跟踪文件、653,709 字节**，没有运行时第三方依赖，适合作为第一个真实任务。它有 715 项原测试，足够检查基本回归。历史修复任务可能已存在于模型训练数据，不能宣称模型此前没见过。

固定目标 base：`247e15b3a489d5805375c95dfa79486c9bd0eb1b`；官方修复：`1806a75b836b9eff4a7885a96ece6183f5fb6409`，对应 [PR #1153](https://github.com/more-itertools/more-itertools/pull/1153)。模型仅收到原 Issue 标题、正文和 base 源码；官方修复由独立评测端持有。

Issue 的输入是 `list(reversed(numeric_range(0)))`。预期 `[]`，base 实际抛 `IndexError: numeric range object index out of range`。原因是 `__reversed__` 在构造反向区间前直接调用 `_get_by_index(-1)`，空区间没有最后一个元素。

v1/v2 的源码修改都是在该调用前加 `if not self: return iter(())`；v3 使用 `if not self._len: return iter(())`。官方修复采用捕获 IndexError 后返回空迭代器。三种写法不完全相同，因此按行为验收，不能靠与官方 Patch 相同判定成功。模型同时往原有 test_reversed 中追加案例，v1/v3 各 4 个，v2 为 3 个；这些是同一个测试方法内的断言，所以公开 pytest 用例数仍为 715。

## 三轮改变了什么，结果是什么

v1 的环境提示词要求先读运行时/依赖/锁文件与 CI，再自行构建。第一次在构建前读了 15 次文件，产生较大上下文。v2 因此增加“环境准备最多读 3 次文件，先构建并跑基线，然后定位源码；一般读不超过 80 行”。第二轮仍在构建前读取了 8 次文件，说明提示词中的次数要求没有被可靠遵守。第三轮保留 v2，只把工具的单次读取上限从 400 改为 80；它在构建前只读 3 次文件，但后续调用更多。

| 指标 | 004：v1 / 400行 | 005：v2 / 400行 | 006：v2 / 80行 |
| --- | ---: | ---: | ---: |
| 构建前 read_file 次数 | 15 | 8 | 3 |
| 模型请求 | 9 | 10 | 13 |
| 工具调用 | 22 | 19 | 17 |
| 服务报告 Token | 98264 | 98113 | 119879 |
| 输入 / 输出 Token | 96072 / 2192 | 94874 / 3239 | 117829 / 2050 |
| 模型构建总秒数 | 28.34 | 22.32 | 20.01 |
| Agent Loop 秒数 | 55.53 | 64.27 | 54.16 |
| 独立重建秒数 | 25.41 | 28.45 | 20.59 |
| 实验全流程秒数 | 122.04 | 128.00 | 112.16 |
| 模型编辑后公开测试 | 未执行 | 715 passed，exit 0 | 未执行 |
| 独立验证 base | 7 failed / 722 passed，exit 1 | 7 failed / 722 passed，exit 1 | 7 failed / 722 passed，exit 1 |
| 独立验证官方 / 候选 | 729 passed / 729 passed，exit 0 | 729 passed / 729 passed，exit 0 | 729 passed / 729 passed，exit 0 |
| 新增回归 / 缺失用例 | 0 / 0 | 0 / 0 | 0 / 0 |
| 停止原因 | token_budget | token_budget | token_budget |
| issue_fixed / solved | true / false | true / false | true / false |

三轮每轮都成功构建一次，没有模型构建失败。每轮都在新 builder 中重建模型 Dockerfile，再在同一验证镜像中验证 base、官方源码与候选源码；应用候选时恢复原测试和测试配置，避免模型改测试替自己放行。独立测试从运行前就固定在评测端。14 项验收中，base 有 7 失败、7 通过；加上原始 715 项全部通过，合计 7 失败、722 通过。候选的原 7 个失败逐项变为 passed，原先通过项仍然通过。

`solved` 还要求 Agent Runtime 正常完成，不能把独立评测事后跑通冒充 Agent 自己完成闭环。004/006 修改后没再跑公开测试；005 虽跑过，但没有完成最终返回及 Runtime 收尾验证。三轮都保留 Patch，供评测和排查。

每个条件只有一次运行，没有统计显著性。005 比 004 只少 151 Token（约 0.15%），006 又比 005 多 21,766 Token（约 22.18%）。所以这组数据不支持“更短读取能减少总用量”的结论，也不支持“v2 提示词已经更好”。三轮 Python 基础版本由模型分别选择，不是控制变量，耗时变化不能全部归因于提示词。

## 还剩 Token，为什么停了

Runtime 的下一轮请求检查为：`input_reserve = len(serialized_messages_and_tools_utf8) + 256`，`remaining = 150000 - used`，`completion_limit = min(4096, remaining - input_reserve)`。如果 completion_limit 小于 1，就不发请求，停止为 token_budget。这里的字节数是保守预留，**不是服务实际 tokenizer 的 Token 数**。

| 检查值 | 004 | 005 | 006 |
| --- | ---: | ---: | ---: |
| 已消耗，服务报告 | 98264 | 98113 | 119879 |
| 剩余预算 | 51736 | 51887 | 30121 |
| 请求序列化字节数 | 60768 | 56186 | 44267 |
| 下一轮输入预留 | 61024 | 56442 | 44523 |

这些数能直接解释停止：三轮都出现剩余预算小于下一轮输入预留。不是 DeepSeek 返回限流，也不是 API 已消费满 150,000。三轮估算入账 Token 都为 0，服务报告用量完整；“预留”不能加到已付出的用量里。

006 的上下文确实从 005 的 56,186 字节降到 44,267 字节，但请求数从 10 增至 13，每次继续携带历史消息，因此累计用量反而更多。逐轮表可以看到第 5～11 轮都在搜索/读取。当前证据确认了直接停止条件和重复输入成本，尚不能证明任意 tokenizer 替换、上下文压缩或强制收尾策略一定有效。下一轮应先固定预算预留与真实输入用量的对照，再只改一个上下文策略；不直接扩大预算掩盖问题。

## 14 个独立用例的实际值

下表是三轮结束后在 Docker 中追加的值探针；与原始 pytest 分开归档，不冒充原始 Trace。使用同一保留验证镜像，分别在 base、官方修复和三个候选上读取实际返回值。每行期望等于正常正向序列的逆序。原始 729 项结果仍以各轮 JUnit 和 summary 为准。

| numeric_range 参数 | 期望 | base 实际 | 官方实际 | 004 / 005 / 006 实际 | 通过情况 |
| --- | --- | --- | --- | --- | --- |
| `(0,)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(3, 3)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(2, 1)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(1, 2, -1)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(0.0,)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(Decimal('0'),)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(Fraction(0, 1),)` | `[]` | `IndexError` | `[]` | `[]` / `[]` / `[]` | base失败，四个修复版本通过 |
| `(5,)` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` / `[4, 3, 2, 1, 0]` / `[4, 3, 2, 1, 0]` | 五个版本均通过 |
| `(1, 6, 2)` | `[5, 3, 1]` | `[5, 3, 1]` | `[5, 3, 1]` | `[5, 3, 1]` / `[5, 3, 1]` / `[5, 3, 1]` | 五个版本均通过 |
| `(5, 0, -2)` | `[1, 3, 5]` | `[1, 3, 5]` | `[1, 3, 5]` | `[1, 3, 5]` / `[1, 3, 5]` / `[1, 3, 5]` | 五个版本均通过 |
| `(0, 1, 0.25)` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` / `[0.75, 0.5, 0.25, 0.0]` / `[0.75, 0.5, 0.25, 0.0]` | 五个版本均通过 |
| `(Decimal('0'), Decimal('1'), Decimal('0.25'))` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` / `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` / `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | 五个版本均通过 |
| `(Fraction(0, 1), Fraction(1, 1), Fraction(1, 4))` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` / `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` / `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | 五个版本均通过 |
| `(4,)` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` / `[3, 2, 1, 0]` / `[3, 2, 1, 0]` | 五个版本均通过 |

最后一行还检查输入副作用：第一次反转后，五个版本的正向遍历都仍是 `[0, 1, 2, 3]`，第二次反转都仍是 `[3, 2, 1, 0]`。其余行未额外测量输入副作用。范围对象为空的 7 行，修复前异常、修复后空列表；非空结果没有变化。

## 每次请求花在哪里

以下输入/输出/总数均为服务报告，耗时为客户端测量秒数；动作是返回的工具调用名。没有把原始对话或推理公开。

### RUN-20260914-004

| 请求 | 动作 | 输入 Token | 输出 Token | 总 Token | 秒 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | list_files, search_code | 1681 | 93 | 1774 | 1.193 |
| 2 | read_file, read_file | 4559 | 155 | 4714 | 0.851 |
| 3 | search_code, read_file | 7827 | 178 | 8005 | 1.105 |
| 4 | read_file, read_file, read_file, read_file | 9060 | 228 | 9288 | 1.339 |
| 5 | read_file, read_file, read_file, read_file, read_file | 10903 | 246 | 11149 | 1.683 |
| 6 | read_file, read_file, read_file | 12381 | 213 | 12594 | 1.304 |
| 7 | build_environment | 13342 | 190 | 13532 | 1.545 |
| 8 | run_tests | 17874 | 49 | 17923 | 0.784 |
| 9 | edit_file, edit_file | 18445 | 840 | 19285 | 3.129 |

### RUN-20260914-005

| 请求 | 动作 | 输入 Token | 输出 Token | 总 Token | 秒 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | list_files, search_code | 1803 | 103 | 1906 | 1.151 |
| 2 | read_file, read_file, read_file | 2364 | 218 | 2582 | 1.407 |
| 3 | read_file, read_file | 4794 | 233 | 5027 | 1.523 |
| 4 | read_file, read_file, read_file | 6458 | 364 | 6822 | 2.590 |
| 5 | build_environment | 7795 | 421 | 8216 | 2.197 |
| 6 | run_tests | 12669 | 77 | 12746 | 1.454 |
| 7 | search_code, search_code, search_code | 13264 | 256 | 13520 | 1.610 |
| 8 | read_file | 13890 | 91 | 13981 | 0.997 |
| 9 | edit_file, edit_file | 15191 | 1334 | 16525 | 4.908 |
| 10 | run_tests | 16646 | 142 | 16788 | 1.243 |

### RUN-20260914-006

| 请求 | 动作 | 输入 Token | 输出 Token | 总 Token | 秒 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | list_files | 1803 | 81 | 1884 | 1.369 |
| 2 | read_file, read_file, read_file | 2220 | 131 | 2351 | 1.580 |
| 3 | build_environment | 3593 | 207 | 3800 | 2.049 |
| 4 | run_tests | 8139 | 61 | 8200 | 1.036 |
| 5 | search_code, search_code | 8716 | 128 | 8844 | 1.976 |
| 6 | read_file | 9052 | 79 | 9131 | 1.783 |
| 7 | read_file | 9964 | 114 | 10078 | 1.845 |
| 8 | search_code, search_code | 10365 | 239 | 10604 | 1.677 |
| 9 | search_code | 10885 | 121 | 11006 | 1.312 |
| 10 | read_file | 12374 | 78 | 12452 | 1.319 |
| 11 | read_file | 13145 | 237 | 13382 | 1.994 |
| 12 | edit_file | 13612 | 286 | 13898 | 2.105 |
| 13 | edit_file | 13961 | 288 | 14249 | 1.704 |

## 固定版本、环境与可复现范围

共同设置：DeepSeek，请求与服务返回模型均为 `deepseek-flash`，地址 `https://api.deepseek.com`，extra_body 为 `{}`；未单独设置 temperature。150,000 Token、单次输出上限 4,096、30 轮、60 工具调用、Loop 900 秒、构建 300 秒、测试 120 秒。宿主 Python 3.12.13、macOS arm64；uv.lock SHA-256 为 `8256210a762f06efc6bed4bbb655daeafefc851ffb2ef343cd0b63c269ef24df`。金额未测量。

**RUN-20260914-004**：run_id `agent-8d292bdfcf9c`；开始时间 `2026-09-14T01:16:14.688555+00:00`（UTC），Agent commit `1d43d4ce68f181b570d1f823058a2b3f8c8759e9`，dirty=false。Prompt `environment-v1`，SHA-256 `ecd482a2b8b2ba6d4250312eddeb0b76745b607b96cdc0f833164b8fa9adfdc4`。

模型 Dockerfile：

```dockerfile
FROM python:3.10-slim
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir pytest
```

运行镜像 `sha256:aff9f6dc112ee7c1b15c59f8806bbdfe9701cfc931406de2fb2437634b7a5c50`；独立重建镜像 `sha256:605200789036ef0e77d0fae5185888534bd89edca24509066fdae36ad66e645c`。验证 Python：`3.10.21 (main, Aug 31 2026, 23:56:10) [GCC 14.2.0]`，导入位置 `/workspace/more_itertools/__init__.py`。实际 pip freeze：

```text
exceptiongroup==1.3.1
iniconfig==2.3.0
packaging==26.3
pip==23.0.1
pluggy==1.6.0
Pygments==2.21.0
pytest==9.1.1
setuptools==79.0.1
tomli==2.4.1
typing_extensions==4.16.0
wheel==0.46.3
```

候选 Patch SHA-256：`a86935db750a3013b8202d46226513c87b66e055176afe5fad5fff4bc648e3e4`。[完整测试结果](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-004/summary.json) · [逐轮数据](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-004/request-breakdown.json) · [Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-004/candidate.patch) · [配置](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-004/metadata.json) · [Prompt全文](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-004/prompt.json) · [公开归档校验](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-004/archive-manifest.json)。

**RUN-20260914-005**：run_id `agent-a9ca172e28e7`；开始时间 `2026-09-14T01:19:06.167768+00:00`（UTC），Agent commit `9b50dcc3ae599df18630955528116b7d18beccb0`，dirty=false。Prompt `environment-v2`，SHA-256 `0099a4633bfbf657117a560e617b09de3a51bee3ad6e69cc2bfd146a53183f9a`。

模型 Dockerfile：

```dockerfile
FROM python:3.12-slim
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir pytest
```

运行镜像 `sha256:b1c2fed49ce8792846cc3d151d7abd48e8eb86f57660371a9a4d996b13ff327d`；独立重建镜像 `sha256:edad5944068aa7be45add22b3ad75e39eec0f589ae5c25b66b8bddb367d23665`。验证 Python：`3.12.14 (main, Aug 31 2026, 23:47:53) [GCC 14.2.0]`，导入位置 `/workspace/more_itertools/__init__.py`。实际 pip freeze：

```text
iniconfig==2.3.0
packaging==26.3
pip==25.0.1
pluggy==1.6.0
Pygments==2.21.0
pytest==9.1.1
```

候选 Patch SHA-256：`d14bedc224538fe2de57d6b5947c5b6e45d4eddb06fc01710294b1e884dea358`。[完整测试结果](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-005/summary.json) · [逐轮数据](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-005/request-breakdown.json) · [Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-005/candidate.patch) · [配置](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-005/metadata.json) · [Prompt全文](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-005/prompt.json) · [公开归档校验](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-005/archive-manifest.json)。

**RUN-20260914-006**：run_id `agent-b9cb8fc8c544`；开始时间 `2026-09-14T01:29:30.702970+00:00`（UTC），Agent commit `90ca7cc8c8ede5db0d5442763d1f1efec7b5ede7`，dirty=false。Prompt `environment-v2`，SHA-256 `0099a4633bfbf657117a560e617b09de3a51bee3ad6e69cc2bfd146a53183f9a`。

模型 Dockerfile：

```dockerfile
FROM python:3.11-slim
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir pytest
```

运行镜像 `sha256:53927079c83392486716269e8cc67ec9a46a06febfbab770f9ebe218b78f585b`；独立重建镜像 `sha256:b2c6548ace39250546bab0f2c22f8d6ff7e6c59e424314014f6e80634d3cfdf9`。验证 Python：`3.11.16 (main, Aug 31 2026, 23:54:33) [GCC 14.2.0]`，导入位置 `/workspace/more_itertools/__init__.py`。实际 pip freeze：

```text
iniconfig==2.3.0
packaging==26.3
pip==24.0
pluggy==1.6.0
Pygments==2.21.0
pytest==9.1.1
setuptools==79.0.1
wheel==0.46.3
```

候选 Patch SHA-256：`536d73bdbd10908f3926dcd5067395439d27d42272c5a0d44bdd6d1e0e817f30`。[完整测试结果](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-006/summary.json) · [逐轮数据](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-006/request-breakdown.json) · [Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-006/candidate.patch) · [配置](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-006/metadata.json) · [Prompt全文](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-006/prompt.json) · [公开归档校验](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/RUN-20260914-006/archive-manifest.json)。

三轮都只安装 pytest，直接从 /workspace 导入目标包。没有验证 `pip install .`、flit 打包或锁文件安装；不能声称已验证复杂依赖项目。镜像和 pytest 使用可变标签/版本，本次记录了实际依赖和镜像标识，跨日期重跑可能不同。004→005 的代码变更为新增 v2 提示词；005→006 提交变化包含证据归档与提示词格式整理，提示词全文哈希相同，运行配置只改 max_read_lines。

独立验收 SHA-256：`ecadfe23ce03881e81814e5c20bb880637494a80a991da196abb856c134398fc`。[冻结任务](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/eval/tasks/more-itertools-1152/task.json)、[冻结独立测试](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/eval/tasks/more-itertools-1152/test_acceptance.py)、[补采程序](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/REAL-ISSUE-1152-PROBE/reproduce-v3.py)、[补采实际值](https://github.com/xiaoyumuxi/AgenticFix/blob/a5bf74ea5a52c7575088584183ba4e873553ec68/docs/iteration-evidence/REAL-ISSUE-1152-PROBE/results-v3.json)。

各目录 local-manifest.json 指向原本地运行产物，包括未公开的原始 Trace 哈希；archive-manifest.json 校验公开文件，两者范围不同。补采 v3 结果没有覆盖此前 results.json。

从对应 Agent commit 的干净 checkout 复现，先 `uv sync --locked`，配置 DeepSeek 密钥并启动 Docker，然后：

```bash
gh repo clone more-itertools/more-itertools .cache/m3-upstream -- --no-checkout
# 004：environment-v1 / 400；005：environment-v2 / 400；006 如下
AGENTICFIX_ENVIRONMENT_PROMPT_VERSION=environment-v2 AGENTICFIX_MAX_READ_LINES=80 uv run python -m scripts.run_real_issue
```

脚本固定 base 和验收条件；每次会产生新 run，不保证模型返回同样的 Patch。这是同一真实历史 Issue 的三个不同条件尝试，端到端完成 0/3、候选通过 3/3；不是三个独立 Issue，也不是 Benchmark 成功率。第三阶段尚未完成五任务 Mini Benchmark。
