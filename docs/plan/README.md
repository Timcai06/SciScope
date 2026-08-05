# 执行计划工作区（Plan）

- 状态：`active`
- 负责人：项目负责人
- 最后验证时间：2026-08-04

`docs/plan/` 是**短期执行工作区**：把 [`docs/project/国赛目标说明书.md`](../project/国赛目标说明书.md)
的冻结目标落实为有负责人、有边界、有证据、可验收的原子任务。这里不是产品、架构、
接口或运行状态的长期事实来源；长期事实以 `docs/project/`、`docs/architecture/`、
`docs/developer/mcp.md`、`docs/operations/runbook.md` 为准。

## 与现有文档体系的关系

- [`../project/国赛目标说明书.md`](../project/国赛目标说明书.md)：**唯一目标上游**（冻结）。
  本工作区所有任务都锚定它；与它冲突时，先改实现或正式修订说明书。
- [`../project/charter.md`](../project/charter.md)：项目方针（"为什么"，长期事实）。
- [`../project/roadmap.md`](../project/roadmap.md)：北极星与分层路线（"往哪走"）。
  已完成的执行步骤压缩保留为历史执行记录，不承载逐日任务。
- `active/`：正在执行的计划；同一目标只保留一个主计划。
- `completed/`：完成或取消后经过压缩的收尾记录（范围、证据、未完成项、偏差）。
- 已实现行为的 canonical 文档：`docs/architecture/`、`docs/developer/mcp.md`、
  `docs/operations/runbook.md`、`docs/release/`。

`plan/` 不制造第二份路线图、第二份 Charter 或第二份国赛目标书；它只回答
"现在正在执行什么、谁负责、下一步是什么"。

## 当前计划

当前任务以 [`active/README.md`](active/README.md) 为唯一分配索引：

- [D 文献内容结构化](active/D-文献内容结构化.md)
- [G 知识图谱与研究发现](active/G-知识图谱与研究发现.md)
- [A 科研问答与协议](active/A-科研问答与协议.md)
- [T TUI 科研工作流](active/T-TUI科研工作流.md)
- [E 证据 L3 与国赛证明](active/E-证据L3与国赛证明.md)

## 命名规则

- active 新计划使用 `代号-中文短名.md`，例如 `E-证据L3与国赛证明.md`；
- 日期、完整目标和阶段范围写在文档正文；completed 历史可保留日期名；
- 一个文件只描述一个可独立验收的目标；
- 状态只使用 `draft`、`active`、`blocked`、`completed`、`cancelled`；
- `active` 计划必须有负责人和最后验证时间；
- 依赖其它计划或文档时使用相对链接，不复制对方内容。

## 生命周期

```text
draft -> active -> completed
                -> cancelled
        blocked -> active
```

计划完成不等于把复选框全部勾上。归档前必须：

1. 记录可复现的验证命令、测试、截图、演示或人工验收证据；
2. 把已实现的稳定事实回写到对应 canonical 文档（`docs/architecture/`、
   `docs/developer/mcp.md`、`docs/operations/runbook.md` 等）；
3. 保留实际交付范围、未完成项、关键偏差、证据和文档链接；
4. 将文件移入 `completed/`，更新本索引与 [`active/README.md`](active/README.md)，
   并清理 `active/` 中重复、暂停和被替代的计划。

单项自动化验证通过只更新 active 计划中的证据状态；只要完成终点仍有未验收能力，
计划就继续留在 `active/`。新计划从 [`00-计划模板.md`](00-计划模板.md) 开始。
