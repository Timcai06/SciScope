# SciScope 后端托管 — 阿里云演示版 Runbook

目标：在**一台阿里云 ECS** 上用 `docker compose` 跑起完整后端（PostgreSQL+pgvector + FastAPI + DeepSeek 生成），让评委的 TUI / 浏览器通过公网直连。演示优先：**不需要域名、不需要 ICP 备案**（用公网 IP + 8000 端口）。

```
评委 TUI  ──SCISCOPE_BACKEND=http://<ECS_IP>:8000──▶  ECS
                                                      ├─ api  (本仓库 FastAPI)
                                                      └─ db   (pgvector, 同机)
                                                            └─▶ DeepSeek API (生成)
```

生成层走 DeepSeek API，**不上传 `models/llm_local`（4G 本地 7B）**，ECS 无需 GPU。

---

## 0. 准备（本地）

```bash
cp deploy/.env.example deploy/.env     # 填 DEEPSEEK_API_KEY 和 POSTGRES_PASSWORD
```

把本地语料导出为可迁移的 dump（这是要搬上云的核心数据）：

```bash
# 用本地 SciScope 的 Postgres DSN；--no-owner/--no-acl 便于在容器里恢复
pg_dump "$SCISCOPE_DB_DSN" -Fc --no-owner --no-acl -f /tmp/sciscope.dump
ls -lh /tmp/sciscope.dump     # 记下大小，scp 时心里有数
```

## 1. 开 ECS

- 规格：**4 vCPU / 16 GB**（reranker + embedder 要进内存，8G 偏险）。
- 镜像：Ubuntu 22.04。区域：境内（与 DeepSeek 同区，低延迟）。
- 安全组放行入站：`22`(SSH)、`8000`(API)。**不要**放行 `5432`（DB 只在本机环回）。
- 计费：演示用**按量付费**最省，跑完释放。

## 2. ECS 上装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

## 3. 上传代码 + 模型（跳过 4G 的 llm_local）

在**本地**仓库根目录：

```bash
ECS=root@<ECS_IP>
# 代码（小）
rsync -az --exclude '.git' --exclude 'models' --exclude 'frontend/node_modules' \
      ./ "$ECS:/opt/sciscope/"
# 模型：只传需要的 ~3.2G，显式排除 llm_local
rsync -az --exclude 'llm_local' models/ "$ECS:/opt/sciscope/models/"
# 语料 dump
scp /tmp/sciscope.dump "$ECS:/opt/sciscope/deploy/"
# 你填好的 .env
scp deploy/.env "$ECS:/opt/sciscope/deploy/.env"
```

## 4. 起库 + 恢复语料

ECS 上：

```bash
cd /opt/sciscope
# 先只起 db（pip 装 torch 较慢，先让库就绪好恢复数据）
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d db
# 等 healthy
docker compose -f deploy/docker-compose.yml --env-file deploy/.env ps
# 恢复语料到容器库
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec -T db \
  pg_restore -U sciscope -d sciscope --no-owner --no-acl < deploy/sciscope.dump
```

## 5. 起 API

```bash
# 构建镜像（境内加阿里云 pip 镜像更快）
DOCKER_BUILDKIT=1 docker compose -f deploy/docker-compose.yml --env-file deploy/.env build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
docker compose -f deploy/docker-compose.yml --env-file deploy/.env logs -f api
```

> 注：当前 `Dockerfile` 未声明 `PIP_INDEX_URL` build-arg；如需镜像加速，在 `Dockerfile`
> 的 pip 行后追加 `-i https://mirrors.aliyun.com/pypi/simple/` 即可（见文件内注释）。

## 6. 验证（ECS 上 + 公网）

```bash
curl -s http://127.0.0.1:8000/api/ingest/status          # {"status":"ready","papers":<真实数量>}
curl -s http://127.0.0.1:8000/api/dashboard/overview | head
```

公网验证（任意机器）：

```bash
curl -s http://<ECS_IP>:8000/api/ingest/status
```

## 7. 客户端接入

```bash
# brew 装的 TUI 指向云后端
SCISCOPE_BACKEND=http://<ECS_IP>:8000 sciscope-tui
```

至此 “用户直接使用” 成立：评委无需本地数据/模型/GPU，装个 TUI 指向这个地址即可问答。

---

## 常见故障

- **`papers` 为 0 / 检索为空**：语料未恢复成功。重跑第 4 步 `pg_restore`，看是否报表缺失。
- **api 启动慢/OOM**：reranker 载入吃内存；确认是 16G 规格。临时可设 `SCISCOPE_USE_RERANKER=0` 降级到纯 RRF（牺牲一点相关性）。
- **DeepSeek 401/额度**：检查 `deploy/.env` 的 `DEEPSEEK_API_KEY`；或临时 `SCISCOPE_USE_MOCK_LLM=true` 验证检索链路。
- **pip 构建慢**：用阿里云 PyPI 镜像（见第 5 步）。
- **升级为正式产品**：再谈域名 + ICP 备案 + HTTPS（Caddy 自动证书）+ 把 db 拆成托管 RDS。
