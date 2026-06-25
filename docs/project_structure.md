# SciScope 项目结构

代码按**六层**组织,职责单一、依赖自底向上。**Python 承载全部智能**(数据 → RAG →
agent),**Go 仅作终端客户端**(经 SSE 消费,可替换、不绑定)。

```
数据要素/
├── data_pipeline/              ① 数据加载/规范化
│   ├── loaders.py                 读取 JSON/CSV 论文记录
│   ├── normalize.py               统一字段(标题/摘要/作者/年份/关键词)
│   ├── models.py                  共享数据类
│   └── analytics.py               基础分析
├── src/
│   ├── harvest/                ① 6 源采集(arXiv/PubMed/PMC/OpenAlex/Crossref/DOAJ)
│   ├── analysis/               ① 分析资产(分布/关键词/主题/作者网络)→ 数据报告
│   ├── models/                 ② 模型/索引层
│   │   ├── embeddings.py           多语言 e5 嵌入器
│   │   ├── build_embeddings.py     批量向量化(断点续传)
│   │   ├── bilingual.py            中→英术语映射(跨语言检索)
│   │   ├── reranker.py             cross-encoder 重排
│   │   ├── trends.py               Mann-Kendall + Sen's 斜率 + 预测
│   │   ├── recommend.py            语义+关键词+作者+MMR 推荐
│   │   ├── graph_export.py         Louvain/PageRank → output/graphs/*.json
│   │   └── keyword_filter.py       噪声关键词过滤
│   └── infra/                  建库/装载 CLI(PostgreSQL schema + load)
├── models/                     ② 模型文件:嵌入器权重·趋势·推荐·本地 LLM(Git 忽略)
├── output/graphs/              ② 知识图谱 JSON 产物(Git 忽略)
├── backend/app/
│   ├── services/               ③ 服务层 / RAG 核心
│   │   ├── retrieval_service.py    混合检索:FTS + pgvector + RRF + 双语 + 重排
│   │   ├── graphrag.py             沿关键词共现图扩展查询
│   │   ├── evidence_chat.py        固定式 GraphRAG 问答(/api/chat)+ 证据接地
│   │   ├── recommend_service.py / trends_service.py / graph_service.py
│   │   ├── corpus_service.py       样本语料回退(无 DB 时)
│   │   └── deepseek_provider.py    LLM provider 抽象
│   ├── agent/                  ④ 智能体层
│   │   ├── loop.py                 stream_agent:ReAct 循环(plan→执行→观察→反思)
│   │   └── tools.py                9 个工具(包装上面的 services)
│   ├── api/                    ⑤ 接口:routes_agent(/api/agent/stream SSE)+ search/chat/...
│   └── main.py                 FastAPI app
├── tui/                        ⑥ Go 终端客户端(Bubble Tea / Charm)
│   ├── main.go                    Elm 架构;消费 SSE,⏺/⎿ 渲染,Nerd Font 图标
│   ├── .goreleaser.yaml            Homebrew 分发配置
│   └── go.mod / go.sum
├── infra/postgres/             PostgreSQL schema + pgvector SQL
├── evaluation/                 评测套件(检索/推荐/趋势/相关性)
├── frontend/                   Next.js 工作台(规划中,复用同一 SSE/REST 接口)
├── output/{pdf,assets,eval}/   两份报告 PDF + 图表 + 评测结果
├── docs/{competition,research}/ 赛题源文档 / 研究笔记 / runbook
├── data/{raw_canonical,processed,analysis,sample}/  数据底座(多为 Git 忽略)
├── Makefile                    全流水线(make full-rebuild / backend / llm / tui ...)
├── 交付说明.md                  评委索引(成果→仓库位置映射)
└── .github/workflows/release.yml  打 tag → GoReleaser → Homebrew cask
```

## 运行时数据库(PostgreSQL + pgvector)

`papers` · `paper_chunks` · `chunk_embeddings`(367k)· `paper_embeddings`(159k)·
`authors` · `paper_authors` · `coauthor_edges` · `keyword_*`。

## 分层职责

| 层 | 目录 | 职责 |
|----|------|------|
| ① 数据 | `data_pipeline`, `src/harvest`, `src/analysis` | 采集 → 规范化/去重 → 分析资产 |
| ② 模型 | `src/models`, `models/`, `output/graphs/` | 向量/趋势/推荐/图谱模型文件,入 pgvector |
| ③ 服务/RAG | `backend/app/services` | 混合检索 + GraphRAG + 证据接地 |
| ④ 智能体 | `backend/app/agent` | ReAct 工具循环:plan→执行→观察→反思 |
| ⑤ 接口 | `backend/app/api` | FastAPI;智能体走 `/api/agent/stream`(SSE) |
| ⑥ 客户端 | `tui/` | Go/Bubble Tea 终端;Web 前端复用接口 |

## Git 跟踪约定

`data/`(除 `sample/`)、`models/`、`output/graphs/*.json`、`tui/sciscope-tui`、
`tui/dist/` 均为生成产物,被 Git 忽略(保留 `.gitkeep` 占位);可由 `make` 目标复现。
