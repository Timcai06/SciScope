# E｜证据 L3 与国赛证明

- 状态：`active`（E00、E01、E03、E04、E05 技术 `PASS`；E02 质量主表 `REVISE`；E08 外部阻塞）
- 负责人：项目负责人；分工：NLP/评测、后端/MCP、演示/报告、领域专家
- 当前领取：E02；上游：[冻结目标说明书](../../project/国赛目标说明书.md)
- 交付边界：先把“相关”与“支持/反驳/证据不足”区分清楚，再证明 API/MCP、TUI 和报告的
  事实一致；不以开发自测充当专家金标准，不把历史评测当当前运行态。

## 已确认事实与诚实边界

| 事实 | 代码/材料依据 | 尚未证明 |
|---|---|---|
| `verify_claim` 已有支持、反驳、中立及回退实现 | `backend/app/agent/tools/verify_claim.py` | 句级证据、校准拒答在人工金标准上的质量 |
| claim—paper—stance 可写入资产，争议视图按同一 `claim_norm` 聚合并返回 `paper_ids` | `infra/postgres/stance.sql`、E03 fixture + 隔离 live PostgreSQL gate | 当前库已有由真实科学 judge 产生、可用于展示的争议案例 |
| API、Agent tool 和 MCP server 有争议读取入口且 fixture 对账同一 claim/paper IDs | `backend/app/api/routes_disputes.py`、`backend/app/mcp_server.py`、[E03 工程集成](E/E03-20260810-同claim争议三读工程集成.md)、[E04 顺序调用](E/E04-20260810-OpenCode顺序调用.md) | 这证明 client 顺序调用与资产闭环，不证明自然语料上的 stance 质量 |
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

- 状态：`PASS`（2026-08-05；产物与链接已复核）；依赖：无。
- 产物：[E00 基线与证据台账](E/E00-基线与证据台账.md)（基线 commit `67e275a`，2026-08-05）。
- 文件所有权：`docs/plan/**`、证据索引和引用的 canonical 文档；不改模型、数据或报告源。
- 做什么：冻结本轮 commit、运行环境、数据版本、历史/当前/计划中三层口径；将国赛指标映射到
  代码、测试、截图、外部材料，缺项显式标红。
- 验收：没有任何“代码已实现”被写成“已证明”；每个下游任务有唯一证据落点。
- 验证：`rtk git diff --check`、`rtk git status --short` 和链接检查结果回填。

### E01｜20 条标注卡试运行（两种证据等级）

- 状态：`PASS`（2026-08-05 独立复核通过；仅为试运行，非正式金标准）；依赖：E00。
- 产物：[E01-20260805-标注试运行.md](E/E01-20260805-标注试运行.md) 及
  `output/stance_annotation/e01_trial/`、`output/stance_reconciliation/e01_trial/`。
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

- 状态：`技术门禁 PASS / 质量门禁 REVISE`（纪律、官方英文 gold 真评分、双语 silver 来源冻结已完成；正式双语人工 Gold/L3 主表仍待完成）；依赖：E01。
- 产物：[E02-20260805-L3纪律与评测.md](E/E02-20260805-L3纪律与评测.md)；
  修复 judge 格式异常静默降 NEUTRAL 缺陷（fail-closed），新增 10 条纪律测试。
- 复核修订（2026-08-05）：fail-closed 完整化——空数组/多余元素/缺失 stance/非对象元素
  一律拒答；confidence 缺失默认 0.0（不再 0.5，杜绝意外导出部分支持/证据反驳）；
  当时明确无正式双语主集与 SciFact 锚点评测，不得质量 PASS；2026-08-10 技术替代完成后仅解锁 E03 工程集成。
- 复核修订 2（2026-08-05，REVISE）：NaN/Infinity/-Infinity 置信度 fail-closed——
  judge 层 `math.isfinite` 检查（非有限值→整次 `ok=False` 走证据不足回退）；
  verify_claim 聚合层同样用 `isfinite` 防御（`inf>=阈值` 为 True，原可导出"强支持"）；
  补 judge 层参数化测试与 verify_claim 层不驱动结论/不写资产测试。
- 收口修订（2026-08，正式评测可执行性）：最初 SciFact 锚点因无官方 claims/corpus 而
  `BLOCKED`；E02a 已完成官方数据准入、哈希/schema 校验和 dry-run 入口，2026-08-10 又完成
  oracle-candidate 基线真评分。
  已固化 gold_v1 主集 schema（id/claim/evidence/language/source/domain）、train/dev/test 冻结规则、
  领域·语言分层字段与 E02 主表分开报告格式（检索/证据句定位/stance/校准拒答/similarity 对照/样本边界）；
  dev_fixture 管线可执行（16 条 baseline，仅纪律实现验证）；fail-closed 回归保持。
  2026-08-10 已补官方 dev 真评分与双语 silver，分别见 E02a Wave 0 报告和 E02b；它们关闭工程
  输入/来源门禁，但不完成 L3 质量证明。
- 替代收口（2026-08-10，无法正式专家标注）：新增 [E02b 双语 Silver 替代收口](E/E02b-20260810-双语Silver替代收口.md)。
  SciFact 官方英文 rationale 保持外部 gold 锚点；6 条中文/跨语翻译与比较方向反转样本只作为
  `unreviewed_silver`，有来源句索引、变换记录、冻结 SHA256 和模型间 agreement 入口。它关闭
  可复现输入/来源门禁，**不产生质量分数、不替代 Gold v1/专家裁决/国赛外部证明**；仅与官方
  SciFact 真评分共同解锁 E03 工程集成。
- 文件所有权：`backend/app/agent/tools/verify_claim.py`、stance schema/测试、`evaluation/`；不改
  论文语料。
- 做什么：验收并补齐证据句、限定条件、低置信拒答、解析失败不静默变 `NEUTRAL`、支持/反驳的
  对称性和回退纪律；以正式双语主集 + SciFact 锚点 + similarity 对照评估。
- 验收：每项纪律都有正/反测试；主表分别报告检索、证据句、立场、校准/拒答，明确正式金标准
  未具备时只能 `REVISE`。
- 验证：`rtk make test-backend`、`rtk make eval-stance-similarity` 及实现后的 stance 主表命令。

### E02a｜SciFact 锚点数据准入与可执行评测入口

- 状态：`技术 PASS / 质量 REVISE`（数据准入、官方格式 scorer 与公开 dev 真评分完成）；依赖：E02 纪律。
- 产物：[E02a-20260808-SciFact锚点准入.md](E/E02a-20260808-SciFact锚点准入.md)；
  `evaluation/stance/scifact_data.py`（loader/validator）、`evaluation/stance/scifact_eval.py`
  （dry-run 评测入口）、`evaluation/stance/scifact_anchor.json`（已更新为 downloaded_and_validated）、
  原始数据 `data/scifact/raw/`（官方 S3 下载，含 SHA256 manifest）。
- 边界：默认 dry-run；评分需 `--predictions` + `--allow-score` 同时满足。已跑分模型是
  TF-IDF/LogReg oracle-candidate 基线，**不宣称 L3 已通过**；只解锁 E03 工程集成。
- 验收：缺文件/哈希不符/schema 不符 fail-closed；输出样本数、标签分布、缺失率、证据引用可解析率。
- 验证：`rtk test python3 -m pytest backend/tests/test_scifact_admission.py -q`（9 passed）、
  `rtk test make test-backend`（491 passed）、`rtk summary python3 -m evaluation.stance.scifact_eval --split dev`（dry-run data_ok）。

### E03｜同一 canonical claim 的争议三读路径

- 状态：`工程 live PASS / 质量 REVISE`；依赖：E02 技术门禁。正式质量验收仍依赖 E02 人工 Gold/L3 主表。详见 [E03 工程集成](E/E03-20260810-同claim争议三读工程集成.md)。
- 文件所有权：`infra/postgres/stance.sql`、`backend/app/api/routes_disputes.py`、Agent/MCP 读取测试；
  不改变 papers/chunks。
- 做什么：在受控环境设 `SCISCOPE_ALLOW_WRITE_TOOLS=1` 后，对**同一个 canonical claim 的一次
  `verify_claim(persist=true)` 核查**，让其已采信检索证据同时含
  至少一条 `SUPPORT` 和一条 `CONTRADICT`，同次落库到同一 `claim_norm`，使 `contradictions`
  视图出现该 claim，并通过 API、Agent tool、MCP resource 三处读取同一资产。
- 禁止：分别对相反句子调用后将结果称为争议闭环；它们会生成不同 `claim_norm`，不能满足此任务。
- 验收：数据库、三条读取路径和来源 paper ID 完全对得上；若找不到真实案例，保留 `REVISE`。
- 证据边界：本任务可以证明写入/读取和 canonical claim 聚合正确，不能用来宣称 stance 模型质量达标。
- 验证：任务实现后 `rtk curl -fsS 'http://127.0.0.1:8000/api/disputes?limit=20'`、Agent 调用、
  `rtk make mcp` 及 SQL 抽样记录。

### E04｜OpenCode 真调用证据

- 状态：`PASS`（2026-08-10）；依赖：E03。
- 文件所有权：`opencode.json`、MCP 文档、调用日志/截图；不修改论文语料。
- 做什么：先由 OpenCode 在写入授权环境调用 `verify_claim(persist=true)` 核查真实论断，再读取
  `sciscope://disputes/recent`；如实说明前者会 upsert 已采信证据至 stance 资产
  `claim_evidence_stance`，不触碰 `papers`/`chunks`。
- 验收：日志能证明顺序、工具输入输出、resource 读取和同一 claim 的争议资产；旧“0 争议只读”
  记录只可作初始态，不得作为完成证据。
- 验证：`rtk opencode mcp list` 和一次可保存的真实调用产物。
- 当前收口：见 [E04 顺序调用](E/E04-20260810-OpenCode顺序调用.md)。
  本轮已拿到真实 OpenCode 事件流与 session 导出：
  `sciscope_verify_claim` 以 `persist=true` 成功写入 2 条 stance 资产；
  随后同一会话成功调用 `read_mcp_resource(server=sciscope, uri=sciscope://disputes/recent)`，
  返回相同 claim/paper IDs。期间同步修复了 SciScope MCP resource 返回契约，
  并用真实 `ClientSession.read_resource(...)` 复核兼容性。

### E05｜报告口径准备

- 状态：`PASS`（2026-08-05 独立复核通过；仅为口径准备）；依赖：E00。
- 产物：[报告口径.md](../../project/报告口径.md)。
- 复核修订（2026-08-05）：补逐项采集日期/可复现命令、DB 数字附 SQL 记录；测试数更正为本次实测
  `rtk make test-backend` = 336 passed（不再写"326 收集/2 errors"）。
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

- 状态：`BLOCKED`（交付包传输/ZIP/目录审计已完成；仍缺许可说明、usage-rights、字段映射与领域联系人）；依赖：许可说明、领域联系人；与 D00/D01 协作。
- 文件所有权：准入记录、许可矩阵、试点协议/反馈、匿名化统计；未经授权不提交原文。
- 做什么：收到数据后按 D 合同进行隔离、抽样质量/重复率/领域适配审查，选择可落地任务并记录
  用户前后对照；不把“拿到几千篇论文”自动解释为真实用户成效。
- 验收：来源与授权明确，至少一个可复核真实场景及外部反馈；不能满足则继续 `BLOCKED`。
- 验证：准入报告、处理日志、对照任务记录和第三方证明（若有）。
- 审计证据：[E08-20260810-讯飞交付包准入审计](E/E08-20260810-讯飞交付包准入审计.md)；
  `output/audit/xunfei_delivery_v1.json`。5,568 个 PDF 的 ZIP CRC 与稳定 ID 解析通过，但缺许可/字段材料且有 1 个零字节文件。
  若外部材料继续缺失，只能按审计报告 §6 的“阻塞下替代推进路径”继续推进其余 Wave 2–6 工程，
  不得把讯飞交付包包装成已落地场景或已准入语料。

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
| E00 | `PASS` | [E00 基线与证据台账](E/E00-基线与证据台账.md)：冻结基线与指标—证据矩阵 |
| E01 | `PASS` | [E01-20260805-标注试运行.md](E/E01-20260805-标注试运行.md)：20 条试运行；非正式金标准 |
| E02 | `技术 PASS / 质量 REVISE` | [E02-20260805-L3纪律与评测.md](E/E02-20260805-L3纪律与评测.md)：纪律、英文官方基线与双语 silver；正式人工 Gold/L3 主表仍缺 |
| E02a | `DONE`（待复核） | [E02a-20260808-SciFact锚点准入.md](E/E02a-20260808-SciFact锚点准入.md)：SciFact 数据准入、完整性校验与 dry-run 评测入口 |
| E02b | `技术 PASS / 质量 REVISE` | [E02b-20260810-双语Silver替代收口.md](E/E02b-20260810-双语Silver替代收口.md)：冻结的双语 silver 仅作回归/模型一致性；不替代 Gold；可支持 E03 工程集成 |
| E03 | `工程 live PASS / 质量 REVISE` | 同 claim 的真实 PostgreSQL 写入与 DB/API/tool/resource 三读证据；不得解释为 stance 质量证明 |
| E04 | `PASS` | [E04 顺序调用](E/E04-20260810-OpenCode顺序调用.md)：真实 OpenCode 已完成 `verify_claim(persist=true)` + `read_mcp_resource` 顺序调用，并保留 session 导出 |
| E05 | `PASS` | [报告口径.md](../../project/报告口径.md)：报告口径表 |
| E06 | `PENDING` | 两份重建 PDF 与一致性记录 |
| E07 | `PENDING` | 演练、硬件清单、离线回退 |
| E08 | `BLOCKED` | 授权、准入与真实场景/反馈 |
| E09 | `PENDING` | 提交包与独立复现记录 |
