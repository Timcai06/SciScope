# SciScope 最终提交 Manifest

本文件定义正式提交包的白名单边界。打包目标是让评委能快速定位两份报告、代码、模型资产、数据资产和复现说明；不把历史路线图、缓存、虚拟环境或未刷新文档混入正式交付。

## 必交成果

| 赛题要求 | 提交内容 | 路径 |
|---|---|---|
| 数据分析报告 | PDF、图表、图表 manifest | `output/pdf/sciscope_data_report/sciscope_data_report.pdf`; `output/assets/sciscope_data_report/` |
| 科研智能体模型 | Python 代码、skill 工作流、模型/索引资产、知识图谱、评测结果 | `src/`; `backend/`; `.sciscope/skills/`; `data_pipeline/`; `models/trends/`; `models/recommend/`; `output/graphs/`; `output/eval/` |
| 项目报告书 | PDF | `output/pdf/sciscope_project_report/sciscope_project_report.pdf` |
| 系统运行说明 | 评委索引、README、runbook、提交清单 | `交付说明.md`; `README.md`; `docs/operations/runbook.md`; `docs/reports/final_submission_checklist.md`; `docs/reports/submission_manifest.md` |
| 演示样例 | 智能体黄金会话 | `docs/examples/golden_verify_claim_session.md` |

## 代码与运行入口

- `Makefile`
- `.sciscope/skills/`
- `scripts/agent_smoke.py`
- `scripts/build_submission_package.py`
- `configs/`
- `infra/`
- `src/`
- `backend/`
- `data_pipeline/`
- `tui/`

Go TUI 是终端客户端，消费 FastAPI 的 `/api/agent/stream`；Python 层承载数据、RAG、模型与智能体逻辑。

## 数据资产

- `data/raw_canonical/`: 规范化原始底账。
- `data/analysis/`: 数据报告使用的分析资产。
- `data/processed/`: 处理后语料与 RAG 片段。

如提交平台大小受限，可优先保留 `data/analysis/`、`data/processed/*.summary.json` 和复现说明，并在提交说明中标明全量数据重建命令。

## 模型与索引资产

- 小型可直接提交资产：`models/trends/`、`models/recommend/`、`output/graphs/`、`output/eval/`。
- 大型可替换依赖：`models/embedder_local/`、`models/llm_local/`、PostgreSQL/pgvector 运行库表。

大型依赖是否随包提交取决于平台限制；若不随包提交，必须保留 `docs/operations/runbook.md` 中的下载、配置和重建路径。

## 默认排除

- Git 元数据与本地配置：`.git/`、`.env.local`。
- 构建缓存：`.cache/`、`.pytest_cache/`、`__pycache__/`、`tmp/`。
- 历史路线图/执行记录已清理；未刷新设计稿如 `output/pdf/sciscope_design/` 不进入正式提交包。
- 前端历史产物或临时构建目录。

## 生成方式

```bash
make submission-package
```

输出：

- `output/submission/SciScope_submission/`
- `output/submission/SciScope_submission.zip`
- `output/submission/SciScope_submission_manifest.csv`
