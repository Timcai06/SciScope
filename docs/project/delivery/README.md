# SciScope 交付计划存档（Delivery — 历史/参考）

> **定位**：本目录是**历史交付计划与参考执行材料**（由原 `plan/product_delivery_roadmap/` 并入），
> 冻结于 2026-07 竞赛交付期。它记录当时的阶段拆分与验收条款，供追溯与参考，
> **不再是当前承诺**。当下目标与决策以上游
> [`docs/project/国赛目标说明书.md`](../国赛目标说明书.md)（冻结目标）与
> [`docs/project/roadmap.md`](../roadmap.md)（方向）为准；
> **当前执行计划**以 [`docs/plan/active/`](../../plan/active/) 为唯一分配索引。
> 若本目录内容与冻结目标或当前执行冲突，以冻结目标/当前执行为准。

## 文件索引

| 文件 | 读者 | 解决的问题 | 定位 |
|---|---|---|---|
| `01_competition_reproducibility.md` | 评委、出题方、交付负责人 | 没有依赖环境时如何验收;有环境时如何复现关键成果 | 历史交付快照（复现路径仍可参考） |
| `02_product_distribution.md` | 产品负责人、最终用户、文档负责人 | TUI 主线如何分发;landing page 承担什么宣传、下载与文档入口角色 | 历史交付快照（TUI 分发现状以 `docs/release/` 为准） |
| `03_cross_platform_installation.md` | 发布负责人、平台工程、运维 | macOS/Linux/Windows 如何安装、打包、校验和降级 | 参考执行材料（含大量"待实现/待补齐"标记） |
| `04_delivery_checklist_and_timeline.md` | 项目负责人、执行团队 | 从产品体验到最终验收的阶段拆分、边界和验收标准 | **历史时间线**（W1-W7 已过，不再作为当前承诺） |

## 总体目标

### 1. 赛题交付

评委拿到源码、报告和固定产物后,不应被迫先配置数据库、模型、LaTeX 或交互式前端环境。即使零依赖,也能通过报告 PDF、章节源码、固定评测文件、图表 manifest、样例数据、landing 下载页和说明文档确认项目成果。若评委愿意配置环境,则通过 `Makefile` 入口复现关键指标、服务接口和 TUI 演示。

### 2. 最终用户产品化

真实用户应优先通过终端安装和使用 SciScope TUI。短期以 macOS Homebrew 为首要分发方式,GitHub Releases 承担统一产物源;Linux/Windows 逐步补齐 tarball、安装脚本、WSL/PowerShell 路线。landing page 用于说明产品、展示报告、提供安装方式和下载入口,不替代 TUI 的科研智能体主流程；交互式 Web 工作台不在当前范围。

## 执行顺序

1. 产品体验打磨  
   先让 TUI 的输入、思考过程、时间线、证据卡、错误恢复和导出体验达到产品级。

2. LangGraph 工作流升级  
   将用户可见的流程从工具调用清单升级为科研工作流:理解问题、制定研究计划、证据检索、自检修正、综合回答。

3. 报告与固定产物收敛  
   固定数据报告、项目报告、评测 JSON/Markdown、图表 manifest、TUI 会话导出样例和交付说明。

4. 打包与安装链路  
   稳定 `sciscope-tui` 的 Homebrew/GitHub Releases 分发,再补 Linux tarball、安装脚本和 Windows 路线。

5. Landing Page  
   做产品说明、截图/录屏、安装矩阵、报告下载和文档入口,让评委与真实用户都能快速理解 SciScope。

6. 最终验收  
   分别按“赛题无环境验收”“赛题有环境复现”“最终用户安装使用”三张清单收口。

## 当前边界

- 做:产品体验、LangGraph 可观测工作流、交付物复现说明、TUI 分发、landing page 信息架构。
- 不做:补采全量数据、重写底层检索/推荐/趋势模型、把后端/数据库/模型强行塞进 Homebrew 单一安装包。
- 已补:黄金会话样例 `docs/examples/golden_verify_claim_session.md`。
- 待确认:统一 release manifest、Linux/Windows 安装脚本、真实 `sciscope-session-*.md` 自动导出快照、无本机私有路径的 PDF 编译链路。

## 下一步建议

当前主线应继续优先做产品体验:先把 TUI 中 LangGraph 阶段语义、长聊天、证据时间线和错误恢复做扎实;随后补一份可提交的赛题交付 manifest,再进入打包与 landing page。
