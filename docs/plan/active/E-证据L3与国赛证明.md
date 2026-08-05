# E｜证据 L3 与国赛证明

- 状态：`active`（E08 为外部阻塞，其余任务 `PENDING`）
- 负责人：项目负责人；分工：NLP/评测、后端/MCP、演示/报告、领域专家
- 当前领取：E00；上游：[冻结目标说明书](../../project/国赛目标说明书.md)
- 交付边界：先把“相关”与“支持/反驳/证据不足”区分清楚，再证明 API/MCP、TUI 和报告的
  事实一致；不以开发自测充当专家金标准，不把历史评测当当前运行态。

## 已确认事实与诚实边界

| 事实 | 代码/材料依据 | 尚未证明 |
|---|---|---|
| `verify_claim` 已有支持、反驳、中立及回退实现 | `backend/app/agent/tools/verify_claim.py` | 句级证据、校准拒答在人工金标准上的质量 |
| claim—paper—stance 可写入资产，争议视图按同一 `claim_norm` 聚合 | `infra/postgres/stance.sql` | 当前库已有可展示的真实争议或三读闭环 |
| API、Agent tool 和 MCP server 有争议读取入口 | `backend/app/api/routes_disputes.py`、`backend/app/mcp_server.py` | OpenCode 已完成“核查后读取 resource”的真实调用 |
| 历史评测/黄金会话存在 | `output/eval/`、`output/dialogue/` | 它们是当前主表或外部证明 |

## 最简依赖图

```text
E00 基线/台账 → E01 标注试运行 → E02 L3 纪律与评测 ───────────────┐
       ├──────→ E03 同 claim 争议三读 → E04 OpenCode 真调 ────────┼→ E09 提交整合
       ├──────→ E05 报告口径准备 → E06 报告源/PDF 重建 ───────────┤
       └──────→ E07 演示证据与硬件清单 ───────────────────────────┤
讯飞数据/领域专家 ─────────────────────────────────────→ E08 数据准入与真实场景 ┘
```

## 原子任务

### E00｜基线、主权与证据台账

- 状态：`PENDING`；依赖：无。
- 文件所有权：`docs/plan/**`、证据索引和引用的 canonical 文档；不改模型、数据或报告源。
- 做什么：冻结本轮 commit、运行环境、数据版本、历史/当前/计划中三层口径；将国赛指标映射到
  代码、测试、截图、外部材料，缺项显式标红。
- 验收：没有任何“代码已实现”被写成“已证明”；每个下游任务有唯一证据落点。
- 验证：`rtk git diff --check`、`rtk git status --short` 和链接检查结果回填。

### E01｜20 条标注卡试运行（两种证据等级）

- 状态：`PENDING`；依赖：E00。
- 文件所有权：`evaluation/build_stance_packets.py`、`evaluation/reconcile_stance_annotations.py`、
  标注指南/样例；不把试运行结果写入正式主表。
- 方案 A（默认、无独立标注者时唯一可用）：直接执行
  `rtk python -m evaluation.build_stance_packets --candidates <未标注候选文件> --out-dir <输出目录> --minimum 20`。
  `rtk make stance-packets` 当前固定最小 80，不能用于 20 条。可自标/内部模拟，但必须记录参与者
  与是否盲法；只报告 `agreement_rate` 和问题清单。
- 方案 B（仅有两位独立标注者）：才可报告双盲一致性。现有脚本只输出 `agreement_rate`；除非新增
  独立 κ 脚本、验收命令并经复核，否则不得写 Cohen's κ。
- 验收：20 条卡片和分歧/指南修订记录；正式金标准仍需说明书要求的规模和领域专家，不能 PASS。
- 验证：`rtk python -m evaluation.reconcile_stance_annotations <标注文件>` 或任务实现后的
  `rtk make stance-reconcile`，实际参数、退出码和产物路径回填。

### E02｜L3 句级证据、校准拒答与回退纪律

- 状态：`PENDING`；依赖：E01。
- 文件所有权：`backend/app/agent/tools/verify_claim.py`、stance schema/测试、`evaluation/`；不改
  论文语料。
- 做什么：验收并补齐证据句、限定条件、低置信拒答、解析失败不静默变 `NEUTRAL`、支持/反驳的
  对称性和回退纪律；以正式双语主集 + SciFact 锚点 + similarity 对照评估。
- 验收：每项纪律都有正/反测试；主表分别报告检索、证据句、立场、校准/拒答，明确正式金标准
  未具备时只能 `REVISE`。
- 验证：`rtk make test-backend`、`rtk make eval-stance-similarity` 及实现后的 stance 主表命令。

### E03｜同一 canonical claim 的争议三读路径

- 状态：`PENDING`；依赖：E02。
- 文件所有权：`infra/postgres/stance.sql`、`backend/app/api/routes_disputes.py`、Agent/MCP 读取测试；
  不改变 papers/chunks。
- 做什么：对**同一个 canonical claim 的一次 `verify_claim` 核查**，让其已采信检索证据同时含
  至少一条 `SUPPORT` 和一条 `CONTRADICT`，同次落库到同一 `claim_norm`，使 `contradictions`
  视图出现该 claim，并通过 API、Agent tool、MCP resource 三处读取同一资产。
- 禁止：分别对相反句子调用后将结果称为争议闭环；它们会生成不同 `claim_norm`，不能满足此任务。
- 验收：数据库、三条读取路径和来源 paper ID 完全对得上；若找不到真实案例，保留 `REVISE`。
- 验证：任务实现后 `rtk curl -fsS 'http://127.0.0.1:8000/api/disputes?limit=20'`、Agent 调用、
  `rtk make mcp` 及 SQL 抽样记录。

### E04｜OpenCode 真调用证据

- 状态：`PENDING`；依赖：E03。
- 文件所有权：`opencode.json`、MCP 文档、调用日志/截图；不修改论文语料。
- 做什么：先由 OpenCode 调用 `verify_claim` 核查真实论断，再读取
  `sciscope://disputes/recent`；如实说明前者会 upsert 已采信证据至 stance 资产
  `claim_evidence_stance`，不触碰 `papers`/`chunks`。
- 验收：日志能证明顺序、工具输入输出、resource 读取和同一 claim 的争议资产；旧“0 争议只读”
  记录只可作初始态，不得作为完成证据。
- 验证：`rtk opencode mcp list` 和一次可保存的真实调用产物。

### E05｜报告口径准备

- 状态：`PENDING`；依赖：E00。
- 文件所有权：`docs/project/报告口径.md`；本任务**不修改任何报告 TeX 源**。
- 做什么：建立四层数字来源（代码实现、已验证、已证明、计划/阻塞）、章节映射、拟改写范围和
  每条诚实边界的位置，消除 README、PPT、两份报告的口径漂移。
- 验收：每一个准备展示的数字有来源、日期、验证等级和责任人。
- 验证：文档交叉检查；改写由 E06 执行。

### E06｜报告源改写与 PDF 重建

- 状态：`PENDING`；依赖：E05、E02、E03、E04。
- 文件所有权：`output/pdf/sciscope_data_report/sections/`、
  `output/pdf/sciscope_project_report/sections/` 及报告构建产物；不得改变未在 E05 批准的数字。
- 做什么：将已验证/已证明事实写入两份报告，历史和计划明确标注；重建 PDF 并做口径一致性核对。
- 验收：两份 PDF 都由源码重建；任意核心数字可回链 E00 台账；未完成能力不被写成现状。
- 验证：`rtk make data-report-pdf`、`rtk make project-report-pdf` 和一致性核对记录。

### E07｜评委演示、硬件清单与离线回退

- 状态：`PENDING`；依赖：E03、E04、T04。
- 文件所有权：演示脚本、硬件清单、视频/截图和提交索引；TUI 实现改动交给 T 线。
- 做什么：制作“claim → 正反/不足证据 → 来源回链 → MCP 调用”的短闭环，附本机和 2080 Ti
  分工、在线依赖、预热步骤、离线只读回退和失败备用视频。
- 验收：线上/离线素材标识清楚，连续三次演练不过时，所有截图可回链具体环境。
- 验证：演练记录、视频时长记录和硬件清单复核。

### E08｜讯飞数据准入与真实场景证明

- 状态：`BLOCKED`；依赖：外部数据、许可说明、领域联系人；与 D00/D01 协作。
- 文件所有权：准入记录、许可矩阵、试点协议/反馈、匿名化统计；未经授权不提交原文。
- 做什么：收到数据后按 D 合同进行隔离、抽样质量/重复率/领域适配审查，选择可落地任务并记录
  用户前后对照；不把“拿到几千篇论文”自动解释为真实用户成效。
- 验收：来源与授权明确，至少一个可复核真实场景及外部反馈；不能满足则继续 `BLOCKED`。
- 验证：准入报告、处理日志、对照任务记录和第三方证明（若有）。

### E09｜提交整合与独立复现

- 状态：`PENDING`；依赖：E02、E03、E04、E06、E07，若主张讯飞场景还依赖 E08。
- 文件所有权：提交包构建脚本、`JUDGE_README`、复现记录；不为打包绕过许可证或密钥边界。
- 做什么：固定 commit、数据/模型说明、轻量样例与完整离线清单、评委入口、证据索引；独立环境
  验证核心材料可打开、核心演示可运行或诚实显示阻塞。
- 验收：非项目成员十分钟内找到演示、报告、证据和复现步骤；实际未运行的全量步骤不伪称完成。
- 验证：`rtk make install`（如适用）、`rtk python -m scripts.build_submission_package`（如入口存在）、
  `rtk git diff --check`，并保留独立复现记录。

## 证据台账

| 任务 | 状态 | PASS 所需证据 |
|---|---|---|
| E00 | `PENDING` | 冻结基线与指标—证据矩阵 |
| E01 | `PENDING` | 20 条试运行；非正式金标准 |
| E02 | `PENDING` | L3 主表、纪律测试和失败分析 |
| E03 | `PENDING` | 同 claim 的数据库/API/tool/resource 三读证据 |
| E04 | `PENDING` | OpenCode 先核查后 resource 的真实产物 |
| E05 | `PENDING` | 报告口径表 |
| E06 | `PENDING` | 两份重建 PDF 与一致性记录 |
| E07 | `PENDING` | 演练、硬件清单、离线回退 |
| E08 | `BLOCKED` | 授权、准入与真实场景/反馈 |
| E09 | `PENDING` | 提交包与独立复现记录 |
