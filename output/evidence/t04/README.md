# T04 证据索引

本目录记录 commit `546eba2137a5656937718ed7dc0c790dd81fe675` 在远端全量环境上的
端到端演练。它证明固定代码、全量数据库、完整向量资产、DeepSeek 后端和 Go TUI 可以组成
可运行链路；不证明 stance 已达到外部金标准，也不替代真实用户或评委验收。

## 证据分层

| 路径 | 证据等级 | 内容与边界 |
|---|---|---|
| `runtime/manifest.md` | 远端运行事实 | 硬件、软件、数据库计数、向量索引与 readiness；不含凭据 |
| `online/summary.{json,md}` | 自动在线演练 | 同一论断连续三次真实 SSE 调用的计时、工具、状态与引用合同摘要 |
| `online/run-*.sse` | 原始在线证据 | 三次调用的完整 SSE；用于复核摘要，不应手工改写 |
| `tui/isolated-*` | TUI 首次隔离演练 | 工具成功但引文合同 fail-closed 为 `generative_non_evidentiary`，必须保留 |
| `tui/retry-*` | TUI 有记录重试 | 同一黄金任务重试后得到 `citations ok`；不能删除首轮失败只展示重试 |
| `offline/demo-*` | 固定离线夹具 | `make tui-demo` 在不可达后端地址下仍可播放；只证明演示回退，不证明实时能力 |
| `offline/failure-*` | 故障提示 | 普通 TUI 面对不可达后端时显示 blocked、`make backend`、`/retry`、`/doctor` |
| `SHA256SUMS` | 完整性 | 除自身外全部证据文件的 SHA-256 |

## 核心结论

- 三次在线 SSE 均为 HTTP 200、收到 `[DONE]`、无 error frame；首事件均为 `0.004s`，总耗时为
  `12.259s`、`12.378s`、`12.511s`。
- 三次均通过引用合同并返回 4 条引用，但 stance 为一次 `supported`、两次
  `partially_supported`，说明运行链稳定而生成式裁决并非确定性。
- 隔离 TUI 首次生成因关键结论缺少要求格式的标题和年份引用而被合同降级；保留该失败后，
  有记录重试通过 `citations ok`。这证明 fail-closed 与重试路径，而不是 100% 首次成功率。
- `model` 未出现在 SSE final meta 中，因此摘要保留 `None`；DeepSeek 只由同批次
  `readyz.json` 的 provider configured 状态证明，不能伪造具体模型字段。

