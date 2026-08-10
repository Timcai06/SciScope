# D｜文献内容结构化

- 状态：`active`（D00–D03 `PASS`；D04 Wave 0 技术门禁 `PASS`、外部语义质量门禁 `BLOCKED`；D05 技术 `PASS`）
- 负责人：数据/后端负责人；复核：领域专家 + 项目负责人
- 当前领取：D04/D05（复核）→ D 线收尾（讯飞数据到达后 E08 联动）；上游：[冻结目标说明书](../../project/国赛目标说明书.md)
- 交付边界：把**已准入**文献变为可追溯、可检索、可被 Agent 调用的结构化记录；不做
  TUI 任意 PDF 上传，不承诺对受版权限制的全文再分发。

## 已确认事实与诚实边界

> 来源 / 许可 / 原始文件 / 运行时表 / 版本哈希 / 权限分级 / 讯飞最小元数据的逐项现状见
> [D00 数据准入清单](D/D00-数据准入清单.md)（D00 产物，盘点基线 `c63ef49`）。

| 事实 | 代码/材料依据 | 当前不能据此声称的能力 |
|---|---|---|
| canonical 层实有 6 源 169,324 条，按 `(source, year)` 分区且带回链字段 | `data/raw_canonical/summary.json`、`data/raw_inventory.csv` | 6 源之外声明过的 `semantic_scholar`/`core` 有数据 |
| 全文富化可从受控来源读取 PDF、抽取文本并批量处理 | `src/harvest/fulltext_enrichment.py` | TUI 不能接收并解析用户临时上传的论文；富化覆盖 5 源（不含 pmc） |
| 原始、分析、处理和数据库层已有分层 | `src/data_contracts/`、`src/harvest/`、`infra/postgres/` | 尚无对每篇新数据的结构化字段正确率主表 |
| 检索切片由数据处理链产生 | `src/infra/chunks.py` | 切片不是“方法、结果、限制条件均已抽取”的证明 |
| 数据层**没有** license/使用范围字段 | `src/data_contracts/models.py`、`src/data_contracts/normalize.py`、`infra/postgres/schema.sql` | 能区分“可索引 / 可展示片段 / 可再分发”，或让未知许可安全进入公开导出 |
| canonical 数据无内容哈希，仅规范化时间戳 | `src/harvest/raw_governance.py`（rmtree 式全量重建） | 论文可回指到**来源**；“版本”仅时间戳、无内容哈希，D00 只记录缺口，实际保证转 D01/D02 |

## 最简依赖图

```text
D00 基线与准入边界 → D01 数据合同 → D02 解析与切片 → D03 关键信息抽取
                                                        ├→ D04 人工质量评估
                                                        └→ D05 Agent/API 结构化出口
```

## 原子任务

### D00｜冻结基线、来源与准入边界

- 状态：`PASS`（2026-08；验收为盘点当前可回指范围与缺口）；依赖：无。
- 只读范围：`data/`、`src/data_contracts/`、`src/harvest/`、`infra/postgres/`；产物：本文件的
  事实表与 [D00 数据准入清单](D/D00-数据准入清单.md)。
- 做什么：逐项记录已有来源、许可/使用范围、原始文件定位、运行时表、版本/哈希，以及讯飞
  数据到达时必须提供的最小元数据；明确“可索引”“可展示片段”“可再分发”三个不同权限。
- 验收：明确记录当前可回指范围与版本缺口（内容哈希保证转交 D01/D02 实现，不在 D00 验收范围）；未知许可一律不能进入公开导出。
- 验证：`rtk git diff --check` 退出码 0；`git status` 确认 `data/` 无改动（盘点只写 `docs/plan/`）。

### D01｜受控摄取数据合同

- 状态：`PASS`（2026-08-05 独立复核通过；双哈希语义与类型校验已验证）；依赖：D00。
- 文件所有权：`src/data_contracts/**`、相应摄取器测试、数据字典；不得改 TUI。
- 做什么：为新增论文定义稳定 ID、来源、许可、文件哈希、语言、时间、可用范围和删除/更正
  标记；拒绝缺少来源或许可状态的输入，保留原因日志。
- 验收：有一份最小样例能通过合同并导入；三种非法样例（缺来源、哈希不符、许可未知）被拒绝。
- 验证：`rtk python -m pytest backend/tests/test_admission_contract.py -v` → **17 passed**（退出码 0）；
  回归 `backend/tests/test_ingest.py test_raw_governance.py test_data_readiness.py` → **12 passed**。
  实现：`src/data_contracts/admission.py`（双哈希 + retracted/correction 类型校验）；
  数据字典：`src/data_contracts/ADMISSION.md`。

### D02｜可追溯解析、切片与回链

- 状态：`PASS`（代码实现与自动化回链验证已复核）；依赖：D01。
- 文件所有权：`src/harvest/fulltext_enrichment.py`、`src/infra/chunks.py`、对应测试与迁移；不改
  Agent 结论逻辑。
- 做什么：将解析结果保留页码/段落或可定位文本范围、解析器版本、失败原因；每个 chunk 必须
  回链 paper、来源文件和抽取版本，不能把 PDF 提示词或网页噪声当正文。
- 验收：自动化测试证明每种 locator 能从 chunk 回到原文位置并识别 span 篡改；失败样本有可查询状态而非静默丢失。
- 验证：`rtk test python3 -m pytest backend/tests/test_traceable_chunks.py` → **19 passed**（退出码 0）；
  回归 admission/infra_chunks/ingest → **29 passed**；`rtk git diff --check` 退出码 0。
  实现：`src/infra/traceable_chunks.py`（复用 chunks 原语，未改既有生产链；含 `backtrace_chunk` 回链抽查辅助）；
  报告：[D02-20260805-可追溯解析切片回链](D/D02-20260805-可追溯解析切片回链.md)。
  `backtrace_chunk` 保留为真实讯飞数据接入后的可选人工抽检工具，不是当前 PASS 门槛。

### D03｜关键科学信息结构化抽取

- 状态：`DONE`（产物已生成；已按评审修复 HIGH-1/HIGH-2 与中优先级项，验收待项目负责人复核）；依赖：D02。
- 文件所有权：新建的抽取 schema/服务及其测试，必要时扩展 `backend/app/agent/` 的只读工具；
  不把 LLM 自由文本直接写成事实字段。
- 做什么：为标题、研究对象、研究设计、方法、主要结果、数值/单位、限制条件、结论句建立
  带来源 span 与置信度的字段；低置信或无法定位的字段保留为空/待审，不伪造完整性。
- 验收：字段 schema 有版本；每个非空字段都带来源位置；至少 20 篇人工抽查并发布字段级正确率。
- 验证：`rtk test python3 -m pytest backend/tests/test_structured_extraction.py` → **14 passed**；
  回归 D01/D02 → **48 passed**；`rtk test make test-backend` → **410 passed**；`rtk git diff --check` 退出码 0。
  实现：`src/infra/structured_extraction.py`（schema `structured-extraction/v1`，离线规则，不调 LLM；
  含 chunk_uid 来源链校验与 (source, paper_id, record_sha256) 聚合）；
  报告：[D03-20260805-关键科学信息抽取](D/D03-20260805-关键科学信息抽取.md)。
  **至少 20 篇人工抽查与字段级正确率（验收项）未执行，待 D04 质量评估承接。**

### D04｜抽取质量与数据卡

- 状态：`Wave 0 技术门禁 PASS`（自动 silver 一致性/回链已验证）；**外部语义质量门禁 BLOCKED**，所以 D04 总体验收不得 PASS；依赖：D03。
- 文件所有权：评测脚本、数据卡、审查记录；不改变原始数据。
- 做什么：由非开发者或领域专家盲审 D03 样本，分别统计字段存在性、正确性、来源可定位率和
  拒答/留空率；数据卡写明领域偏差、全文覆盖边界和不可用场景。
- 验收：不只报告“抽取成功数”；每个主字段有分母、置信区间或样本数，且失败例可复查。
- 验证：`rtk python3 -m pytest backend/tests/test_extraction_eval.py -q` → **18 passed**；
  `rtk git diff --check` → 退出码 0。实现：`src/infra/extraction_eval.py`
  （人工聚合：字段 n/存在率/正确率/可定位率/拒答率/留空率/Wilson CI/失败例；自动 silver：
  D02→D03 确定性重跑、`chunk_uid → locator → exact span` 回链、fail-closed 报告）。
  报告：[D04-20260805-抽取质量与数据卡](D/D04-20260805-抽取质量与数据卡.md)（含 Data Card 与盲审模板）。
  **silver 只关闭技术门禁，不是语义正确率；许可明确原文的独立领域专家盲审 + 裁决仍是唯一剩余外部门禁。**

### D05｜结构化文献出口

- 状态：技术 `PASS`（2026-08-10 Codex 复核；不替代 D04 外部语义质量门禁）；依赖：D03、D04。
- 文件所有权：`backend/app/agent/tools/`、API schema/测试、MCP 文档；TUI 仅由 T 线消费稳定事件。
- 做什么：让 Agent/API 能按 paper ID 返回带 provenance 的结构化字段和可用范围，明确“未抽取”与
  “未授权展示”的区别；不把摘要猜测包装成全文结构化结果。
- 验收：一次 API/Agent 调用展示字段、来源、置信度和许可边界；无来源字段不会输出为确定事实。
- 验证：`rtk test python3 -m pytest backend/tests/test_structured_export.py -q` → **14 passed**；
  D01–D05 回归 → **94 passed**；`rtk test make test-backend` → **510 passed, 5 warnings**（均为 2026-08-10 D05 复核）；
  `rtk git diff --check` 退出码 0。
  实现：`src/infra/structured_export.py` + `backend/app/agent/tools/paper_structured.py`（只读 tool，已注册）；
  报告：[D05-20260805-结构化文献出口](D/D05-20260805-结构化文献出口.md)（含可复现调用记录，交 A/T 线）。

## 证据台账与风险

| 任务 | 状态 | PASS 所需证据 |
|---|---|---|
| D00 | `PASS` | [来源/许可/版本台账](D/D00-数据准入清单.md) |
| D01 | `PASS` | [交付记录](./D/D01-受控摄取数据合同.md)：双哈希、类型校验与合同测试；实现 `src/data_contracts/admission.py`、字典 `src/data_contracts/ADMISSION.md` |
| D02 | `PASS` | [交付记录](./D/D02-20260805-可追溯解析切片回链.md)：19 项测试、分页噪声过滤修复与 `backtrace_chunk` 自动化回链验证 |
| D03 | `DONE`（待复核） | [开发报告](./D/D03-20260805-关键科学信息抽取.md)：10 项测试 + 全量 402 passed + provenance；**20 篇人工抽查与字段级正确率待 D04** |
| D04 | `技术 PASS / 外部 BLOCKED` | [Data Card 与评测表](./D/D04-20260805-抽取质量与数据卡.md)：人工聚合 + 18 项专项测试 + Wilson CI；silver 重跑/回链只证明 L2 工程一致性，gold/独立盲审裁决仍待完成 |
| D05 | 技术 `PASS`（2026-08-10） | [契约测试与调用记录](./D/D05-20260805-结构化文献出口.md)：14 项专项契约测试；未授权正文/数值列表/候选句/多来源/受污染审计元数据均 fail-closed。真实论文语义质量仍受 D04 外部门禁约束。 |

讯飞数据在 D00 准入完成前只能保存在受控原始区；它不是“自动通过质量验证”的新金标准。
