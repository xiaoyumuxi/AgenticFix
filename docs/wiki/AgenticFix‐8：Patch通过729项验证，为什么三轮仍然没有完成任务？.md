> 最新进展（2026-09-14）：第六次尝试 RUN-20260914-009 已端到端完成，独立验收729项全通过。前五次失败记录完整保留，具体比较见文末新增记录。

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


---

## 2026-09-14 追加：压缩成功构建日志、限制旧读取正文，都没有完成闭环

本次继续 BUG-20260914-005，新增 RUN-20260914-007/008。上面三轮原始记录保留。本次两个条件各跑一次，仍未得到正常完成的任务。默认配置不启用这两项策略。

先对 005/006 的历史构建返回做离线投影：只保留成功状态、退出码、镜像、Dockerfile 哈希、耗时与原始产物位置。005 的消息 content 从 **9,041 字节缩到 651 字节**，006 从 **8,827 缩到 653**。这是同一份历史数据的变换，没有调用模型；不把字节减少当成实测 Token 节省。

007 保留 006 的 v2 提示词、80 行读取、150,000 Token 预算，仅启用 compact_successful_build。失败构建仍使用原有反馈（仍受既有消息长度上限约束），原始完整工具结果保留在 Trace/产物中。运行器增加每次请求的 context_bytes/input_reserve/remaining_budget 观测字段，没有改变预算算法。

007 又未完成，因此 008 保留 007 配置，只增加 retained_read_results=3：生成请求时省略更早成功 read_file 的正文，保留路径、版本等元数据和显式省略标记；最近三次正文和失败结果保留。完整本地消息不改，助手工具调用和 tool_call_id 配对也不改。这是按时间保留的试验，不是语义摘要或智能检索。

| 指标 | 006：原对照 | 007：成功构建摘要 | 008：再保留最近3次读取 |
| --- | ---: | ---: | ---: |
| 模型请求 | 13 | 16 | 15 |
| 工具调用 | 17 | 20 | 20 |
| 服务报告 Token | 119879 | 110356 | 118525 |
| 模型编辑次数 | 2 | 2 | 0 |
| 非空 Patch | 是 | 是 | 否 |
| 编辑后公开测试 | 未执行 | 715 passed，exit 0 | 未编辑 |
| 独立 base | 7失败/722通过，exit 1 | 7失败/722通过，exit 1 | 7失败/722通过，exit 1 |
| 独立官方 | 729通过，exit 0 | 729通过，exit 0 | 729通过，exit 0 |
| 独立候选 | 729通过，exit 0 | 729通过，exit 0 | 7失败/722通过，exit 1 |
| 新增回归 / 缺失 | 0 / 0 | 0 / 0 | 0 / 0 |
| issue_fixed | true | true | false |
| solved | false | false | false |
| Loop 秒数 | 54.16 | 100.86 | 65.26 |
| 模型构建总秒数 | 20.01 | 56.83 | 30.83 |
| 独立重建总秒数 | 20.59 | 45.18 | 31.51 |
| 实验总秒数 | 112.16 | 184.55 | 138.18 |

007 少用了 9,523 Token（相对 006 约 7.94%），但请求从 13 增到 16。它完成两次编辑并跑过公开测试，随后未能发出最终请求。008 则始终在调查，0 次编辑，导出的是 0 字节 Patch；未修好的 7 项仍失败。008 新增回归为 0 的含义只是没有破坏原先通过项，绝不代表 Issue 已解决。

008 的具体过程包括：读取 more.py 2235～2410（受80行限制），继续读2314～2410，再搜索 __reversed__ 并读2393～2410；之后查 _get_by_index，翻阅测试2580～2760，再搜索 reversed 才读到2997～3030，最后又查 __len__/__bool__ 并重读2314～2392。出现了重复定位和较远范围的阅读。被省略的旧正文可能增加重读需要，但没有单独的反事实运行，不能确认全部额外调查都由省略策略导致。

本次每个配置只有一次，模型输出和基础镜像选择也有随机变化。数据只能说明这两次运行没有带来端到端收益，不能宣称这两个策略对所有任务都无效。

### 预算停止的直接证据

| 数值 | 007 | 008 |
| --- | ---: | ---: |
| 服务已报告用量 | 110356 | 118525 |
| 剩余预算 | 39644 | 31475 |
| 下一轮请求字节数 | 45098 | 42778 |
| 下一轮输入预留 | 45354 | 43034 |

两轮都是 token_budget，下一轮请求没有发出，均没有估算用量入账。008 的字节数是经过“保留3次”投影后的请求，不能与完整 messages.json 字节数混淆。全程没有扩大预算，也没有让 Runtime 跳过收尾检查。

接下来应先处理预算估算的可验证性：本轮已记录每次请求的字节预留和服务实际输入用量，能够逐次检查差距。再选择有独立依据的估算器或上下文方案做单因素实验；此处没有实现按字节简单除以常数或扩大预算。只按新旧顺序删除正文不保留关键符号及结论，当前不作为默认方案。

### 两轮逐次用量与预留

预留是请求发出前的估计，输入/输出是返回后的服务报告；不能把预留加到已消耗用量里。耗时是客户端请求秒数。

**RUN-20260914-007**

| 请求 | 动作 | 输入预留 | 实际输入 | 实际输出 | 实际总数 | 秒 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | list_files | 7157 | 1803 | 75 | 1878 | 1.000 |
| 2 | read_file, read_file | 8792 | 2214 | 94 | 2308 | 1.021 |
| 3 | read_file | 12152 | 3193 | 197 | 3390 | 1.286 |
| 4 | build_environment | 13544 | 3531 | 153 | 3684 | 1.267 |
| 5 | run_tests | 15040 | 3932 | 136 | 4068 | 1.260 |
| 6 | search_code, search_code | 17968 | 4576 | 129 | 4705 | 1.167 |
| 7 | read_file | 19321 | 4913 | 79 | 4992 | 0.843 |
| 8 | read_file | 23474 | 6249 | 90 | 6339 | 1.018 |
| 9 | read_file | 26169 | 7064 | 131 | 7195 | 1.212 |
| 10 | search_code, search_code | 27959 | 7625 | 207 | 7832 | 1.363 |
| 11 | read_file | 29423 | 7970 | 78 | 8048 | 1.307 |
| 12 | search_code, search_code | 33692 | 9511 | 137 | 9648 | 0.701 |
| 13 | read_file | 34958 | 9817 | 78 | 9895 | 1.016 |
| 14 | edit_file | 39254 | 11313 | 320 | 11633 | 1.647 |
| 15 | edit_file | 40702 | 11696 | 561 | 12257 | 2.601 |
| 16 | run_tests | 42484 | 12319 | 165 | 12484 | 1.346 |
| 合计 | — | — | 107726 | 2630 | 110356 | — |

**RUN-20260914-008**

| 请求 | 动作 | 输入预留 | 实际输入 | 实际输出 | 实际总数 | 秒 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | list_files, search_code | 7157 | 1803 | 114 | 1917 | 1.109 |
| 2 | read_file, read_file, read_file | 13257 | 3493 | 161 | 3654 | 1.232 |
| 3 | build_environment | 17440 | 4699 | 259 | 4958 | 1.881 |
| 4 | run_tests | 19362 | 5206 | 67 | 5273 | 1.422 |
| 5 | read_file | 21945 | 5785 | 117 | 5902 | 1.295 |
| 6 | read_file | 24249 | 6513 | 79 | 6592 | 1.346 |
| 7 | search_code, read_file | 28227 | 7661 | 185 | 7846 | 1.358 |
| 8 | search_code | 30328 | 8262 | 127 | 8389 | 1.082 |
| 9 | read_file | 31747 | 8644 | 79 | 8723 | 0.962 |
| 10 | read_file | 32087 | 8717 | 270 | 8987 | 1.893 |
| 11 | read_file | 33972 | 9477 | 78 | 9555 | 0.734 |
| 12 | search_code | 37665 | 10752 | 94 | 10846 | 1.559 |
| 13 | read_file | 40843 | 11676 | 78 | 11754 | 1.779 |
| 14 | search_code, search_code | 40018 | 11484 | 395 | 11879 | 2.472 |
| 15 | read_file | 42634 | 12171 | 79 | 12250 | 0.982 |
| 合计 | — | — | 116343 | 2182 | 118525 | — |

### 14 项实际值补采

两轮之后另在 Docker 中应用 007 Patch、或保留 008 的未修改源码，运行同一值探针。以下是事后补采实际输出，与原始 JUnit 分开。原始 base/official 的详细值见上文，补采也再次验证。

| 参数 | 预期 | 007 实际 | 008 实际 | 通过情况 |
| --- | --- | --- | --- | --- |
| `(0,)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(3, 3)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(2, 1)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(1, 2, -1)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(0.0,)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(Decimal('0'),)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(Fraction(0, 1),)` | `[]` | `[]` | `IndexError` | 007通过；008失败 |
| `(5,)` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | 均通过 |
| `(1, 6, 2)` | `[5, 3, 1]` | `[5, 3, 1]` | `[5, 3, 1]` | 均通过 |
| `(5, 0, -2)` | `[1, 3, 5]` | `[1, 3, 5]` | `[1, 3, 5]` | 均通过 |
| `(0, 1, 0.25)` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | 均通过 |
| `(Decimal('0'), Decimal('1'), Decimal('0.25'))` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | 均通过 |
| `(Fraction(0, 1), Fraction(1, 1), Fraction(1, 4))` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | 均通过 |
| `(4,)` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | 均通过 |

最后一项 `(4,)` 的输入副作用：两轮反转后正向遍历都为 `[0, 1, 2, 3]`，再次反转都为 `[3, 2, 1, 0]`。其他项目未追加测量输入副作用。

### 版本与复现

两轮目标 base、官方修复、独立验收 SHA-256、Prompt全文 SHA-256、模型、总预算与上文006相同。两轮请求和返回模型均为 deepseek-flash，extra_body={}；估算入账0，金额未测量。pytest 开发导入路径修复只影响本项目工程测试，实际模型启动一直使用 `python -m scripts.run_real_issue`，其容器测试和目标仓库未因此改变。

**007**：`agent-6fc5120cab68`，UTC 开始 `2026-09-14T01:54:23.247339+00:00`，Agent commit `d110e86e06b93ef0d5c63f682633d53d60f08a12`，dirty=false。uv.lock SHA-256 `8256210a762f06efc6bed4bbb655daeafefc851ffb2ef343cd0b63c269ef24df`。

```dockerfile
FROM python:3.11-slim
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir pytest coverage ruff
```

运行镜像 `sha256:44ced898653d12adbe99ef608d41f0563eb5cd0cc691809569e558143df41abd`；独立镜像 `sha256:749f44c1c8ef11d40055d9ceeafe89fc3c290d38eb6979a91944177f1723cc61`。验证 Python `3.11.16 (main, Aug 31 2026, 23:54:33) [GCC 14.2.0]`，导入 `/workspace/more_itertools/__init__.py`。实际依赖：

```text
coverage==7.16.1
iniconfig==2.3.0
packaging==26.3
pip==24.0
pluggy==1.6.0
Pygments==2.21.0
pytest==9.1.1
ruff==0.16.7
setuptools==79.0.1
wheel==0.46.3
```

Patch SHA-256 `6d05ef33c0c0fb8f7e5a63e0ff660a7cb1f69d764fc8c7bb9b7c5b7d56f6a326`。[完整验证结果](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/summary.json) · [逐次用量](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/request-breakdown.json) · [预留对照](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/request-reservations.json) · [Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/candidate.patch) · [配置](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/metadata.json) · [提示词](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/prompt.json) · [归档SHA-256](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-007/archive-manifest.json)。

**008**：`agent-38801e977fa7`，UTC 开始 `2026-09-14T01:58:41.398849+00:00`，Agent commit `ee2dcd05b8209b6763aa455326ba3454a905f5a9`，dirty=false。uv.lock SHA-256 `8256210a762f06efc6bed4bbb655daeafefc851ffb2ef343cd0b63c269ef24df`。

```dockerfile
FROM python:3.10-slim
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir pytest
```

运行镜像 `sha256:dbd08be8a659b2517afb37afafdc178d8fe54f5fff62a37e28fc5612aea13522`；独立镜像 `sha256:2c83bfe5cc76f52a9f9342a7e23a070a2e79d216c2a930d18eed34d188c3b4bf`。验证 Python `3.10.21 (main, Aug 31 2026, 23:56:10) [GCC 14.2.0]`，导入 `/workspace/more_itertools/__init__.py`。实际依赖：

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

Patch SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。[完整验证结果](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/summary.json) · [逐次用量](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/request-breakdown.json) · [预留对照](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/request-reservations.json) · [Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/candidate.patch) · [配置](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/metadata.json) · [提示词](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/prompt.json) · [归档SHA-256](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/RUN-20260914-008/archive-manifest.json)。

在相应提交的干净 checkout、启动 Docker 并配置 DeepSeek 后，运行：

```bash
# 007
AGENTICFIX_COMPACT_SUCCESSFUL_BUILD=true AGENTICFIX_ENVIRONMENT_PROMPT_VERSION=environment-v2 AGENTICFIX_MAX_READ_LINES=80 uv run python -m scripts.run_real_issue
# 008：只新增保留读取次数
AGENTICFIX_RETAINED_READ_RESULTS=3 AGENTICFIX_COMPACT_SUCCESSFUL_BUILD=true AGENTICFIX_ENVIRONMENT_PROMPT_VERSION=environment-v2 AGENTICFIX_MAX_READ_LINES=80 uv run python -m scripts.run_real_issue
```

默认 compact_successful_build=false、retained_read_results=null，因此已有流程不会自动使用这些未证明有效的策略。它们保留为可复现实验选项。构建与依赖仍然可变，不能保证跨日期重跑相同。这个任务至今5次尝试：端到端0/5，候选验收通过4/5；不能当作5个独立Issue的成功率。

工程验证：19项 Loop 测试通过，完整 **96 passed、1 skipped，28.08秒**，mypy32源文件与工程源码ruff通过。跳过的是先前独立实测过的Docker集成测试，本轮没有改Docker执行器，也没有重新运行该集成测试。新增导入错误另见 AgenticFix-9。

[离线消息投影](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/BUILD-CONTEXT-20260914/projection.json) · [补采程序](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/REAL-ISSUE-1152-PROBE/reproduce-v5.py) · [补采实际值](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/REAL-ISSUE-1152-PROBE/results-v5.json) · [最终工程测试](https://github.com/xiaoyumuxi/AgenticFix/blob/02330578a8ca935c8a091f09ad58ea24a1e3f464/docs/iteration-evidence/BUILD-CONTEXT-20260914/retention-full-tests.txt)。历史数据未覆盖。


## 2026-09-14 追加：第六次尝试终于完成了修复和交付

RUN-20260914-009 接续本页 BUG-20260914-005。前五次的端到端状态仍然是失败；其中四次 Patch 本身通过验收。第六次从同一个未修复版本重新开始，DeepSeek 自己构建环境、读取代码、修改实现和测试、执行测试并申请结束。Runtime 再次验证后返回 `completed / public_tests_passed`，评测端冷构建并检查得到 `solved=true`。

### 这次为什么改提示词

007 已经用 110,356 Token 生成正确 Patch 并跑过公开测试，下一次请求却需要预留 45,354 Token，而只剩39,644，因此根本没有发出最终请求。008 删除旧读取正文后，15次请求、118,525 Token 仍未编辑。这些数据说明“减少正文”没有自动带来完成行为；它们不说明模型一定需要更大的预算。

这次以007的配置为参照：保留80行读取上限和成功构建摘要，保留全部历史读取正文，预算仍为150,000。主要实验变量是 `environment-v2 → environment-v3`：已读实现和公开测试、能解释Issue行为后就做最小修改；修改后优先测试；当前测试通过且Patch解决问题，就给出完成答复。没有提示具体函数如何修复，没有提供官方Patch，也没有改变独立验收。

009使用了此前已提交的Docker错误反馈修复；因此与007并非仅源码一个差异的严格A/B。本轮构建和三次公开测试均成功，输出未截断，没有触发长错误摘要分支。模型请求和服务返回模型名都为 `deepseek-flash`，API为 `https://api.deepseek.com`，extra_body={}，temperature未显式设置。服务非确定性和模型自行选择的Python/依赖也会影响结果，单次成功不能证明提示词收益稳定。

### 前后具体差别

| 指标 | 007：v2+构建摘要 | 008：再删旧读取正文 | 009：v3+构建摘要、保留读取正文 |
| --- | ---: | ---: | ---: |
| Token总预算 | 150000 | 150000 | 150000 |
| 模型请求数 | 16 | 15 | 15 |
| 工具调用数，含Runtime验证/导出 | 20 | 20 | 20 |
| 服务报告Token | 110356 | 118525 | 110534 |
| 估算入账Token | 0 | 0 | 0 |
| 成功编辑次数 | 2 | 0 | 2 |
| 修改后的模型测试 | 715通过 | 未执行 | 715通过 |
| Runtime最终测试 | 未执行 | 未执行 | 715通过 |
| Patch独立验证 | 729通过 | 7失败、722通过 | 729通过 |
| Agent结束状态 | failed/token_budget | failed/token_budget | completed/public_tests_passed |
| 独立评测solved | false | false | true |

009的Token比007多178，不能称为节省Token。差别是009在15次请求内完成了整个流程：第11次改实现，第12次加回归用例，第13次跑测试，第14次看diff，第15次返回完成答复。随后Runtime再跑一次default测试并导出Patch，不需要第16次模型请求。最后一次请求开始时剩52,091，输入预留43,720，加上4,096输出上限共预留47,816，可以发出请求；实际输入12,324、输出301，总12,625。结束剩39,466；归档里的最终上下文快照并不代表尝试发出的第16次请求。

### 代码到底修了什么

旧的 `numeric_range.__reversed__` 对空范围仍调用 `_get_by_index(-1)`，所以 `list(reversed(numeric_range(0)))` 抛出 `IndexError`。模型在进入原有反转逻辑前添加：

```python
if not self:
    return iter(())
```

非空范围继续走原路径。模型另外在现有 `test_reversed` 的参数列表里加入 `(0.0,)`、`(0.0, 0.0)`、`(5.0, 5.0)`、`(0.0, 5.0, -1.0)` 四种空范围，预期均为 `[]`。这是同一个测试方法里的四组输入，所以pytest收集数仍是715，不应说新增了四个独立测试节点。

| 同一份独立测试 | 未修改base | 官方修复 | 本次Patch |
| --- | --- | --- | --- |
| 原始715项回归 | 715通过 | 715通过 | 715通过 |
| 14项冻结Issue验收 | 7失败、7通过 | 14通过 | 14通过 |
| 合计 | 7失败、722通过 | 729通过 | 729通过 |
| 退出码 | 1 | 0 | 0 |
| 新增回归/缺失用例 | — | — | 0/0 |

模型添加的测试在独立验证时被恢复为base的原始测试，隐藏验收另行放入评测worktree。`solved=true` 同时要求Agent完成、Patch非空、修复验收通过、无新增回归、无缺失测试。

### 14项输入的实际输出

下表来自原始pytest结束后的Docker值探针，使用本轮独立验证镜像分别运行base、官方修复、本次Patch；这是补采实际值，不冒充原始JUnit采集。预期来源是该范围正向结果的逆序，固定验收没有修改。

| numeric_range参数 | 预期 | base实际 | 官方实际 | 009实际 | 009结论 |
| --- | --- | --- | --- | --- | --- |
| `(0,)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(3, 3)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(2, 1)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(1, 2, -1)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(0.0,)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(Decimal('0'),)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(Fraction(0, 1),)` | `[]` | `IndexError` | `[]` | `[]` | 通过 |
| `(5,)` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | `[4, 3, 2, 1, 0]` | 通过 |
| `(1, 6, 2)` | `[5, 3, 1]` | `[5, 3, 1]` | `[5, 3, 1]` | `[5, 3, 1]` | 通过 |
| `(5, 0, -2)` | `[1, 3, 5]` | `[1, 3, 5]` | `[1, 3, 5]` | `[1, 3, 5]` | 通过 |
| `(0, 1, 0.25)` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | `[0.75, 0.5, 0.25, 0.0]` | 通过 |
| `(Decimal('0'), Decimal('1'), Decimal('0.25'))` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | `[Decimal('0.75'), Decimal('0.50'), Decimal('0.25'), Decimal('0.00')]` | 通过 |
| `(Fraction(0, 1), Fraction(1, 1), Fraction(1, 4))` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | `[Fraction(3, 4), Fraction(1, 2), Fraction(1, 4), Fraction(0, 1)]` | 通过 |
| `(4,)` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | `[3, 2, 1, 0]` | 通过 |

`(4,)` 反转后，再正向遍历得到 `[0, 1, 2, 3]`，再次反转得到 `[3, 2, 1, 0]`，三个版本一致。其他输入没有额外测量副作用，不作推断。

### 逐次模型请求

输入预留是UTF-8上下文字节数加256；实际输入、输出和总数来自服务usage，两者不是同一种计数。

| 请求 | 动作 | 输入预留 | 实际输入 | 实际输出 | 实际总数 | 客户端秒 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | list_files | 7827 | 1921 | 64 | 1985 | 0.734 |
| 2 | read_file, read_file, read_file | 9411 | 2321 | 129 | 2450 | 1.420 |
| 3 | build_environment | 13422 | 3495 | 320 | 3815 | 1.850 |
| 4 | run_tests | 15604 | 4067 | 61 | 4128 | 0.746 |
| 5 | search_code, search_code | 18170 | 4647 | 134 | 4781 | 0.889 |
| 6 | read_file | 19452 | 4958 | 79 | 5037 | 1.050 |
| 7 | read_file | 23471 | 6164 | 79 | 6243 | 0.494 |
| 8 | read_file, search_code | 27291 | 7313 | 139 | 7452 | 1.193 |
| 9 | search_code | 29876 | 8121 | 229 | 8350 | 1.540 |
| 10 | read_file | 33649 | 9180 | 78 | 9258 | 1.213 |
| 11 | edit_file | 36526 | 10208 | 415 | 10623 | 2.501 |
| 12 | edit_file | 38147 | 10686 | 293 | 10979 | 1.635 |
| 13 | run_tests | 39149 | 11041 | 56 | 11097 | 0.529 |
| 14 | git_diff | 41699 | 11617 | 94 | 11711 | 1.253 |
| 15 | 完成答复 | 43720 | 12324 | 301 | 12625 | 1.925 |
| 合计 | — | — | 108063 | 2471 | 110534 | — |

Agent Loop耗时 **89.59秒**；包含冷重建与独立验证的实验总耗时 **164.78秒**。金额成本未测量。20次工具调用中，18次由模型请求、2次是Runtime最终验证与导出。3次公开测试均715通过，测试版本依次0、2、2；模型构建1次成功，评测端冷构建1次成功。

三次公开测试均出现只读目录的 `PytestCacheWarning: [Errno 30] Read-only file system`，exit_code=0，测试通过；这是已记录的ENV-20260914-002复现。独立验收显式禁用了cacheprovider。没有把警告隐藏成“构建失败”，也没有因为警告放开目录写权限。

### 版本、环境与复现

- 实验目录 `real-1152-d44472699a1c`；Agent run_id `agent-e48662d990af`；开始UTC `2026-09-14T02:42:29.796211+00:00`，新加坡时间2026-09-14 10:42:29（UTC+08）。
- Agent提交 `c1dc3cdb69d6d07532b9c6e96f3fbdd2aca9dd40`，开始时dirty=false；本轮提示词修改在此提交。目标仓库more-itertools/more-itertools，Issue #1152；目标base `247e15b3a489d5805375c95dfa79486c9bd0eb1b`，官方修复 `1806a75b836b9eff4a7885a96ece6183f5fb6409`。Agent提交与目标源码提交不可混用。
- 独立验收SHA-256 `ecadfe23ce03881e81814e5c20bb880637494a80a991da196abb856c134398fc`。
- Prompt SHA-256 `8ae2568bf76dad69693752f5583c15e719c1e7346a5c78ce6c4e6dcab8db89a7`；uv.lock SHA-256 `8256210a762f06efc6bed4bbb655daeafefc851ffb2ef343cd0b63c269ef24df`。
- Patch SHA-256 `de5e95433061fe7a9728526307b05973496070ed3c52df58bac25debb3d3c556`。
- 运行镜像 `sha256:454dbdcd4022b1ec4222b4047ba558980427d80525a6597579f36d4a9fa861e6`；独立验证镜像 `sha256:14e84f0e4f859693983f153f6e40fa2f63f4c7f722be9f50923f5a75b593b953`。
- 宿主macOS arm64、Python3.12.13；容器Python3.10.21，目标包导入 `/workspace/more_itertools/__init__.py`，没有误用预装版本。
- 预算30次模型请求、60次工具调用、150000 Token、900秒Loop；构建300秒、测试120秒。max_read_lines=80，compact_successful_build=true，retained_read_results=null。隔离和网络规则沿用前文。

模型编写的Dockerfile：

```dockerfile
FROM python:3.10-slim

WORKDIR /workspace

COPY . /workspace/

RUN pip install --no-cache-dir pytest

CMD ["python", "-m", "pytest", "-q"]
```

评测镜像实际依赖：

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

它只安装pytest来运行源码测试，没有安装目标项目为wheel；此次不包含目标项目打包验收。Python标签和依赖未锁版本，冷重建不代表跨时间得到相同镜像，镜像ID及构建日志已归档。

在该Agent提交的干净checkout、Docker运行且DeepSeek配置可用时：

```bash
AGENTICFIX_ENVIRONMENT_PROMPT_VERSION=environment-v3 AGENTICFIX_MAX_READ_LINES=80 AGENTICFIX_COMPACT_SUCCESSFUL_BUILD=true uv run python -m scripts.run_real_issue
```

要求retained_read_results保持默认null；若个人.env改过该项，需要恢复此条件。默认环境提示词仍是v1，本轮v3作为明确选项，单次成功尚不足以替换所有默认配置。后续应固定这组成功配置做重复运行，再扩展其他真实Issue；预算输入预留偏保守的问题依然存在。

### 固定证据

[完整三方测试结果](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/summary.json) · [可交付Patch](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/candidate.patch) · [逐请求数据](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/request-breakdown.json) · [请求预留数据](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/request-reservations.json) · [开始时版本与配置](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/metadata.json) · [完整提示词](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/prompt.json) · [模型Dockerfile](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/Dockerfile) · [公开归档SHA-256](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/archive-manifest.json)。

[补采程序](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/REAL-ISSUE-1152-PROBE/reproduce-v6.py) · [补采实际值](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/REAL-ISSUE-1152-PROBE/results-v6.json)。local-manifest.json记录原始本地运行产物的哈希（包括未公开对话），archive-manifest.json仅校验公开文件，两者范围不同。未公开模型原始推理。

工程回归 **99 passed、1 skipped，28.62秒**，ruff通过，mypy33个源文件通过。跳过项是显式Docker集成测试，本次真实Issue另行实际构建并运行Docker；没有宣称重跑了该集成用例。[工程测试日志](https://github.com/xiaoyumuxi/AgenticFix/blob/cca439b44c1292b3b2bee7face13ce7dd975f99f/docs/iteration-evidence/RUN-20260914-009/engineering-tests.txt)。

这个Issue目前累计6次尝试：端到端成功1/6，候选验收通过5/6。它们是同一个Issue在不同迭代配置下的尝试，不能作为6个Issue的Benchmark成功率。此次可以交付已验证的Patch，但729项检查不能证明所有可能输入都没有新问题。
