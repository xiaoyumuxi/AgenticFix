# AgenticFix‐12：补采命令没有启动，为什么不能算测试失败？

ENV-20260914-003，2026-09-14，Asia/Singapore。这是011结束后的补采脚本错误，**不属于模型运行中的环境失败**。原始Agent已经停止，补采没有调用模型。

第一次补采给DockerSandbox传入相对产物目录`runs/m3-development/run011-public-replay`。Docker把输出目录作为bind mount源，要求绝对路径，因此进程退出125，stdout为空，错误为：

```text
invalid mount config for type "bind": invalid mount path: 'runs/m3-development/run011-public-replay/agenticfix-test-2948d50d5937' mount path must be absolute
```

此时pytest根本没有启动，不能把125称为Issue测试失败。修正补采调用为`Path(...).resolve()`，使用新的输出目录保留旧现场后，同一镜像和原始Patch进入pytest，退出1，才得到真正的`[] != [1.0]`断言错误。之后另建干净worktree执行前后对照，详情见[测试预期错误](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%9011%EF%BC%9A%E5%AE%9E%E7%8E%B0%E6%94%B9%E5%AF%B9%E4%BA%86%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E6%A8%A1%E5%9E%8B%E6%96%B0%E5%A2%9E%E7%9A%84%E6%B5%8B%E8%AF%95%E5%8F%8D%E8%80%8C%E9%94%99%E4%BA%86%EF%BC%9F)。

| 补采 | 输出挂载源 | 退出码 | 实际发生的事 |
| --- | --- | ---: | --- |
| 第一次 | 相对路径 | 125 | Docker拒绝启动，未执行测试 |
| 修正路径后 | 绝对路径 | 1 | pytest启动，错误断言失败 |

修正范围仅为临时补采调用，DockerSandbox源码未改；正式runner本来传入绝对目录，不能把这个脚本调用错误归因成原始011的停止原因。未测量任何模型收益。共1次补采启动错误，原始真实运行统计不增加失败次数。

对应Agent版本`deb74899647f5ab363548fc680487ee82318d524`，目标base`247e15b3a489d5805375c95dfa79486c9bd0eb1b`，镜像`sha256:7f452ecfe1a00e70a2c1417c8487d5f4e162868b8f2c088de2ee2eb75bbf2f30`；补采时工作区存在正在整理的未提交文档和证据，未修改Runtime源码，不能称为新的干净模型实验。

[原始125错误](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/public-test-replay-mount-error.json) · [修正路径后的真实断言错误](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/public-test-replay.json) · [使用绝对目录的可复現脚本](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/replay_test_expectation.py) · [证据哈希](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/archive-manifest.json)。镜像/依赖与原始011一致，完整配置和用量在[原运行快照](https://github.com/xiaoyumuxi/AgenticFix/blob/71b58df66f79af9e4e02115d2ee686e13c640580/docs/iteration-evidence/RUN-20260914-011/metadata.json)及[011记录](https://github.com/xiaoyumuxi/AgenticFix/wiki/AgenticFix%E2%80%908%EF%BC%9APatch%E9%80%9A%E8%BF%87729%E9%A1%B9%E9%AA%8C%E8%AF%81%EF%BC%8C%E4%B8%BA%E4%BB%80%E4%B9%88%E4%B8%89%E8%BD%AE%E4%BB%8D%E7%84%B6%E6%B2%A1%E6%9C%89%E5%AE%8C%E6%88%90%E4%BB%BB%E5%8A%A1%EF%BC%9F)；这些补采不含API请求。
