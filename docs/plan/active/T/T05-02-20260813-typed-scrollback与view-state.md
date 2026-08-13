# T05-02｜Typed Scrollback 与 View State

- 状态：`DONE（待复核）`——产物已生成，验收待项目负责人复核
- 执行时间：2026-08-13
- 执行分支：`feat/tui-grok-alignment`（基于 T05-01 提交 `d2ba92b`）
- 依赖：T05-01 `DONE`（项目负责人已确认）

## 一、交付内容

### 1. `tui/scrollback.go`（新文件，约 230 行）—— typed scrollback 状态层

**模型**（对齐计划 T05-02 要求，字段以现有类型为准）：

- `BlockKind`（10 种）：`message`（兜底）/ `user` / `research_plan` / `tool_call` / `tool_result` / `research_trace` / `evidence` / `answer` / `contract` / `recovery` / `system`；
- `BlockStatus`：`running` / `finished`；
- `ScrollbackBlock`：`ID`（单调递增块身份，`b<N>`）/ `Kind` / `Status` / `Expanded`（折叠投影）/ `StartedAt` / `EndedAt` / `Raw`（源文本）/ `Retry` / `Tools` / `Rendered` + `RenderWidth` + `RenderVersion`（渲染缓存）。

**状态机**：

- `startRunningBlock(kind)`：创建 running 块返回 ID；running 块同步写入 `blocks`（事实行），保持 `syncBlockItems` 的对齐不变量——这是实现中发现的必要约束：`refresh()→syncBlockItems()` 会抹掉不在 `blocks` 里的块；
- `updateRunningBlock(id, raw)`：同一 ID 原地更新（更新 `blocks[i]` 同步事实行、失效渲染缓存），finished 块拒绝更新；
- `finishRunningBlock(id)`：标记 finished + `EndedAt`，使块可缓存；
- `setExpanded(id, bool)`：只改 UI 投影，不碰 `blocks`/`transcript`；
- `invalidateRenderCache()` / `invalidateRenderCacheForWidth(newWidth)`：宽度变化只失效渲染缓存，块身份与事实保留；
- `finishedBlocks()` / `blockByKind(kind)`：typed 检索，后续 T05-04/05/06 不再靠解析 ANSI/标题文本判断块类型。

### 2. 全量 typed 接入（`main.go` / `commands_run.go`）

- `model.blockItems` 升级为 `[]ScrollbackBlock`（`conversationBlock` 变为类型别名，零迁移风险）；
- **37 处 `appendBlock` 调用点全部 typed 化**：

| kind | 调用来源 |
|---|---|
| `BlockResearchPlan` | planMsg |
| `BlockToolCall` / `BlockToolResult` | toolCallMsg / toolResultMsg |
| `BlockResearchTrace` | reflectMsg、/timeline |
| `BlockRecovery` | errMsg 错误恢复面板 |
| `BlockContract` | answer-contract sidecar 卡 |
| `BlockAnswer` / `BlockUser` | finalMsg 答案 / 用户问题 |
| `BlockSystem` | 会话保存、命令反馈（help/theme/doctor/sessions/resume 等 26 处） |

- `renderConversationBlock` switch 改用 `BlockKind` 常量；新 kind 暂保持原渲染字符串（无框 block grammar 属 T05-04），**渲染行为零变化**。

## 二、验证证据

### 计划「必须证明」逐项测试（`tui/scrollback_test.go`，7 个新测试）

| 必须证明 | 测试 | 结果 |
|---|---|---|
| streaming 更新同一 running block，而非无限 append | `TestRunningBlockUpdatesSameIDNotAppend` | PASS（3 chunk 后仍 1 块、Raw 原地更新、finished 拒绝更新） |
| finished block 可缓存 | `TestFinishedBlockRenderCacheStable` | PASS（同宽二次渲染 RenderVersion 不变） |
| fold/unfold 不修改 transcript | `TestFoldUnfoldDoesNotTouchTranscript` | PASS（transcript/blocks 长度与内容不变） |
| width 改变只失效相关 render cache | `TestWidthChangeInvalidatesOnlyRenderCache` | PASS（缓存清空、ID/Raw/Kind/Status 保留、120 宽重渲染） |
| /export、/resume 仍以原事实语义工作 | `TestExportUsesTranscriptFactsOnly`、`TestResumeRebuildsBlocksFromFacts` | PASS（UI chrome 不进导出；resume 重建获得新块身份） |
| typed kind 可检索 | `TestBlocksAreRetrievableByTypedKind` | PASS |

### 其他验证

- 全量 `go test ./...` PASS 5.267s（既有 2054 行 main_test 零回归）；
- `gofmt` / `go vet` 干净；
- demo 80 列重放（28,905B）：与 T05-01 快照逐行 diff 的差异全部来自 30s 截断帧边界；语义行集合对比确认画面内容等价（研究计划/证据卡/verify 卡/结论全部一致）——T05-02 未改变任何渲染输出；
- 快照：`output/evidence/t05/baseline/demo-80col-t05-02.raw/.txt`。

## 三、发现与记录

1. **`syncBlockItems` 对齐不变量**：`refresh()` 会重建与 `blocks` 不一致的 `blockItems`，因此 running 块必须同步写入 `blocks`（`updateRunningBlock` 同步更新 `blocks[i]`），否则 streaming 块会被重建逻辑抹掉。这是 T05-04 接入真实 SSE 流时必须遵守的约束。
2. **T05-02 边界遵守**：只建状态 seam，未改任何渲染语法；`blocks` 仍是 UI 渲染的事实行来源，`transcript` 仍是导出事实源，两者职责未混淆。
3. **`BlockEvidence` 暂未接入**：现有 Evidence 卡在 `BlockToolResult` 内渲染（tool result 内嵌），独立 Evidence 卡待 T05-06 拆出后启用该 kind。

## 四、状态与复核请求

**T05-02 标 `DONE（待复核）`**。请项目负责人复核：

1. `tui/scrollback.go`、`tui/main.go`、`tui/commands_run.go`、`tui/scrollback_test.go` diff；
2. 计划「必须证明」5 项与测试对应关系（上表）；
3. demo 视觉等价性（`output/evidence/t05/baseline/demo-80col-t05-02.txt` vs `demo-80col-t05-01.txt`）；
4. 复核通过后解锁 T05-03（Welcome / ASCII 启动页）与 T05-04（Conversation / Block Grammar）主线，并可按计划 Wave B 开并行分支（T05-06/T05-08）。
