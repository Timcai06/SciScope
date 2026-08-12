# SciScope 国赛评委演示 Runbook

本 Runbook 用于远端全量环境的 6–8 分钟技术演示和 60 秒提交视频。真实在线、固定离线
fixture、受控 MCP fixture 必须在画面和旁白中分别标识，禁止互相替代。

## 1. 演示边界

| 标签 | 含义 | 可以证明 | 不能证明 |
|---|---|---|---|
| `LIVE / 全量` | 远端 PostgreSQL、完整向量、DeepSeek 和 Go TUI | 当前运行链可用 | stance 已达到人工 Gold 水平 |
| `RECORDED LIVE` | T04 原始 SSE/TUI 录制 | 指定 commit 曾真实运行 | 当前现场仍在线 |
| `OFFLINE FIXTURE` | `make tui-demo` 固定事件 | 断网时界面和协议可讲解 | 实时检索、实时模型结果 |
| `MCP FIXTURE` | E04 受控 OpenCode 顺序调用 | tool/resource 协议闭环 | 自然语料 stance 质量 |

讯飞交付数据尚未获得许可、usage-rights 和字段映射，任何公开视频不得展示其 PDF 正文，也不得
声称该批数据已进入 canonical、PostgreSQL 或向量库。

## 2. 录制前固定事实

登录远端后进入 tim 工作台，再进入项目：

```bash
tim
cproj
git status --short
git rev-parse HEAD
```

记录实际 commit；工作区必须无未说明改动。然后执行轻量预检，不运行 embedding/full rebuild：

```bash
export SCISCOPE_BACKEND=http://127.0.0.1:8010
export PGPASSFILE=/home/liu/workspaces/sciscope/runtime/.pgpass
export SCISCOPE_DB_DSN=postgresql://sciscope@127.0.0.1:5432/sciscope

curl -fsS "$SCISCOPE_BACKEND/readyz" | jq .
psql "$SCISCOPE_DB_DSN" -Atc "
SELECT 'papers', count(*) FROM papers
UNION ALL SELECT 'paper_chunks', count(*) FROM paper_chunks
UNION ALL SELECT 'chunk_embeddings', count(*) FROM chunk_embeddings
UNION ALL SELECT 'paper_embeddings', count(*) FROM paper_embeddings;"
make judge-demo-preflight
```

期望计数：`159,164` 篇论文、`367,861` 个 chunks、`159,164` 个 paper embeddings、
`367,861` 个 chunk embeddings。预检期望为 `READY_FOR_HUMAN_REVIEW`，其中 video 与真人验收
保持 PENDING 是正常状态。

若后端尚未运行，在单独 tmux 会话中启动。DeepSeek key 只输入当前进程，不写入 shell 历史、仓库或证据：

```bash
tmux new -s sciscope-backend
read -rsp 'DeepSeek API key: ' DEEPSEEK_API_KEY; echo
export DEEPSEEK_API_KEY
export SCISCOPE_USE_MOCK_LLM=false
export SCISCOPE_LLM_PROVIDER=deepseek
export SCISCOPE_DB_DSN=postgresql://sciscope@127.0.0.1:5432/sciscope
export SCISCOPE_EMBEDDER_PATH=models/embedder_local/multilingual-e5-base
BACKEND_PORT=8010 make backend
```

端口 8000 属于共享机器上的其他项目；SciScope 固定使用 8010，不停止或复用 8000 服务。

## 3. 6–8 分钟技术演示

| 时间 | 画面/操作 | 旁白目标 | 证据标签 |
|---:|---|---|---|
| 0:00–0:30 | 标题 + 一句话架构 | 公开文献被治理为可调用、可核验的证据服务 | 说明 |
| 0:30–1:00 | `runtime/manifest.md` 与四个数据库计数 | 区分原始、分析、运行库和向量资产 | RECORDED LIVE |
| 1:00–3:30 | 直接 `make tui`，执行 `/verify 检索增强生成能够降低大语言模型回答中的幻觉风险` | 展示工具、证据卡、stance、置信度、限定条件和审计链 | LIVE / 全量 |
| 3:30–4:20 | `/timeline` 与保存的首轮失败/重试 | 引用不合规会 fail-closed；重试成功也不删除首次失败 | LIVE + RECORDED LIVE |
| 4:20–5:20 | 打开 E04 OpenCode 证据，先 tool 后 resource | SciScope 可作为其他 Agent 的 MCP 证据后端 | MCP FIXTURE |
| 5:20–6:10 | 展示 `sciscope://disputes/recent` 同一 claim 的正反证据 | 争议资产来自同一 canonical claim，不拼接相反句 | MCP FIXTURE |
| 6:10–6:50 | `make tui-demo` 和不可达后端 recovery 截图 | 断网可讲解；普通失败不 silent success | OFFLINE FIXTURE |
| 6:50–7:20 | 三点创新 + 一句边界 | 证据句级 stance、协议出口、全量可复现；质量 Gold/真实试点仍待补 | 说明 |

Bubble Tea 交互必须直接运行 `make tui` / `make tui-demo`，不要用 `rtk make` 包裹，否则
alt-screen 可能被过滤。

## 4. 60 秒提交视频

1. 0–8s：痛点——“相关论文不等于支持这个科学说法”。
2. 8–18s：六源公开文献经过治理，形成全量运行库和可追溯 chunks。
3. 18–38s：真实 TUI `/verify`，定格支持/反驳/不足、证据句、限定条件和论文回链。
4. 38–50s：OpenCode 调用 MCP tool，再读取 disputes resource；画面显式标 `MCP FIXTURE`。
5. 50–57s：离线回退和故障 blocked 卡一闪而过，标 `OFFLINE FIXTURE`。
6. 57–60s：收束——“SciScope 是可被人和其他 Agent 调用的科学证据基础设施”。

视频不得展示安装滚屏、密钥、讯飞 PDF 正文、标题自检索指标或未经验证的趋势预测。

## 5. 失败切换纪律

| 失败 | 现场动作 | 禁止动作 |
|---|---|---|
| DeepSeek 超时/输出漂移 | 保留错误卡，切换到 T04 recorded live | 连续无上限重试或称其为实时结果 |
| 后端不可达 | 展示 recovery 卡；必要时使用离线 fixture | 把 fixture 冒充全量在线 |
| 首轮引用合同失败 | 讲解 fail-closed，可执行一次有记录重试 | 删除首轮失败只保留成功 |
| OpenCode 网络故障 | 播放 E04 固定证据并标 `MCP FIXTURE` | 宣称当前外部 Agent 已在线接入 |

## 6. 录制后

- 将 60 秒和技术视频放入 `output/evidence/e07/video/`，文件名包含日期和 commit。
- 记录时长、SHA-256、录制人、机器和线上/fixture 分段。
- 由一名未参与开发的队友填写
  [非技术评委验收模板](judge-demo-acceptance-template.md)。
- 两项完成后重新运行 `make judge-demo-preflight`，由项目负责人复核后才可将 E07 标为 PASS。

