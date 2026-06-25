# SciScope 跨平台安装与打包计划（v1.0 草案）

> 说明：以下信息仅基于当前仓库现状编写。所有未在仓库中确认到的路径或行为均标注为“待确认/待补齐”。

## 目标与边界

本计划目标：形成一条统一、可复现的安装链路，以 **GitHub Releases** 为唯一二方分发入口；  
macOS 先走 Homebrew，Linux 提供 `amd64/arm64` tarball + 一键安装脚本；  
Windows 先以 WSL/PowerShell 的可运行路径交付，后续补齐原生可执行包。  

关键原则：

- 安装默认必须可运行（**至少能启动演示/只读问答**），不得要求用户先补齐全部重型依赖才可体验。
- 后端、数据库、模型服务采用 **demo/sample 降级路径**，失败时可自动退回可用模式。
- 安装包版本与发布产物应可追溯到 GitHub tag 与校验文件。

## 已有情况核对（仓库里已确认）

已有：

- `Makefile` 已有 Python/Node 安装与启动命令：
  - `make install-backend`（安装 Python 依赖）
  - `make install-frontend`（安装 frontend 依赖）
  - `make backend`、`make frontend`、`make dev`
  - `make tui-build`（本地构建 `tui/sciscope-tui`）
  - `make tui-demo`、`make tui-doctor`
- TUI 侧发布链路已存在：
  - `.github/workflows/release.yml`（tag `v*` 触发）
  - `tui/.goreleaser.yaml`（构建 `darwin/linux x {amd64,arm64}`）
  - `docs/release/tui-homebrew.md`（Homebrew 发布文档）
- 后端配置已有默认回退参数：
  - `backend/app/core/config.py` 默认 `SCISCOPE_DATA_PATH=data/sample/papers.sample.json`
  - 默认 `SCISCOPE_USE_MOCK_LLM=true`
- backend 在功能退化场景有部分“可用但能力下降”行为：
  - `backend/app/services/evidence_chat.py` 提供基于内存语料的证据检索回退
  - `tui/main.go` `doctor` 已检测 backend/LLM/sessions/graph assets，并支持 `--demo` 离线演示

待补齐：

- 后端尚无全量“打包/安装发布”脚本与统一版本发布清单。
- Windows 打包与原生安装器未见（当前仅有 TUI 的 Go 相关打包）。
- `tui` 的 `doctor` 已对齐后端稳定状态接口 `GET /api/ingest/status`，可作为安装后 backend 健康检查入口。
- 后端/数据库启动、模型下载失败时的统一 CLI 安装向导还未落地（需新增脚本/命令）。

## 平台矩阵（v1 计划）

| 平台 | 当前已支持 | 计划产物 | 统一发布入口 | 备注 |
|---|---|---|---|---|
| macOS | ✅ Homebrew for TUI | `sciscope-tui` Homebrew cask | GitHub Releases（via GoReleaser + Tap）| 当前已有；后端/前端未覆盖 |
| Linux（amd64） | ⚠️ 二进制构建配置 | `sciscope-installer-<ver>-linux-amd64.tar.gz`（待实现） | GitHub Releases | 含 tui、backend 启动脚本、frontend 资源、sample data |
| Linux（arm64） | ⚠️ 二进制构建配置 | `sciscope-installer-<ver>-linux-arm64.tar.gz`（待实现） | GitHub Releases | 同上 |
| Windows（WSL） | ⏳ 待补齐 | `sciscope-installer-<ver>-windows-ps.ps1`（待实现） | GitHub Releases | 首期走 WSL，执行 Linux 安装脚本 |
| Windows（原生） | ❌ 待实现 | `sciscope-<ver>-windows-x86_64.exe`（待实现） | GitHub Releases | 后续迭代 |

## 产物命名与目录约定（建议）

统一按 `SciScope_<version>_<platform>_<arch>_<channel>.tar.gz` 建议：

- `sciscope-tui_<ver>_darwin_amd64.tar.gz`
- `sciscope-tui_<ver>_darwin_arm64.tar.gz`
- `sciscope-tui_<ver>_linux_amd64.tar.gz`
- `sciscope-tui_<ver>_linux_arm64.tar.gz`
- `sciscope-installer_<ver>_linux_amd64.tar.gz`（待实现）
- `sciscope-installer_<ver>_linux_arm64.tar.gz`（待实现）

建议每个 tarball 内至少包含：

- `bin/`：可执行文件（`sciscope-tui`，安装后版本可 `--version` 校验）
- `scripts/`：`install.sh` / `doctor.sh` / `start.sh`（待实现）
- `configs/`：`app.example.env`
- `samples/`：`data/sample/papers.sample.json`
- `output/`：安装前可空，首次启动时创建必要子目录（仅 `output/graphs` 允许按需生成）

## 安装命令草案

### macOS（Homebrew，优先）

```bash
# 一次性安装（当前已有）
brew install Timcai06/sciscope/sciscope-tui
sciscope-tui --help
sciscope-tui --demo
```

### Linux（amd64/arm64）

```bash
# 统一安装（拟新增）
curl -fsSL https://github.com/Timcai06/SciScope/releases/download/vX.Y.Z/sciscope-installer_vX.Y.Z_linux_amd64.tar.gz | tar -xz
cd sciscope-installer
chmod +x ./scripts/install.sh
./scripts/install.sh

# 验证
sciscope-tui --version
```

- `install.sh` 建议支持：
  - 自动检测 CPU 架构并选正确 tarball
  - 自动创建 Python / Node 运行前置（若不存在给出安装提示）
  - 可选 `--demo-only`（只启用 tui 离线演示）
  - 可选 `--with-backend`（同期开启 backend + frontend）

### Windows（先 WSL）

```powershell
# 拟新增
.\install.ps1 -Tag vX.Y.Z -Mode wsl
```

预期行为：

- 自动检测/引导启动 WSL2（未开启则提示）
- 在 WSL 内执行 Linux 安装脚本
- 写入 `.env.wsl.example` 并挂载统一数据目录

### Windows（原生可执行，后续）

待确认/待实现：首版先不承诺原生可执行 installer，需在 CLI 端口映射、服务并发与文件路径兼容性评估后推进。

## 依赖与降级模式（安装即体验策略）

### 启动模式定义

1. **最小体验模式（安装默认）**
   - 不依赖 PostgreSQL 和本地模型服务。
   - 使用 sample corpus + mock LLM（确定性响应）。
   - 可保证：`make tui`, `sciscope-tui --demo`, `sciscope-tui doctor` 能跑通。
2. **完整功能模式（可选）**
   - 启用数据库检索：`SCISCOPE_DB_DSN=postgresql://...`
   - 启用模型端：本地/vLLM 或 DeepSeek
   - 启用图谱/embedding 推荐模型构建产物。

### 当前已具备的降级锚点（仓库确认）

- `SCISCOPE_USE_MOCK_LLM=true`（默认）会走 `backend/app/services/deepseek_provider.py` 的 mock provider。
- `SCISCOPE_DATA_PATH=data/sample/papers.sample.json` 提供可离线启动的语料。
- evidence chat 服务可回退内存检索（`backend/app/services/evidence_chat.py`）。
- 路由层对缺失模型/图谱有 503/空结果回退（如 `/api/search`, `/api/recommend`, `/api/graph`）。
- TUI 支持 `--demo` 严格离线演示路径（`tui/main.go`）。

### 当前缺口（待补齐）

- 安装脚本应显式写入以下保底环境：
  - `SCISCOPE_USE_MOCK_LLM=true`
  - `SCISCOPE_DB_DSN=`（空）
  - `SCISCOPE_DATA_PATH=data/sample/papers.sample.json`
  - `SCISCOPE_LLM_PROVIDER=deepseek`（保留，但默认 mock 遮盖）
- 统一健康探测入口已采用 `GET /api/ingest/status`；后续 installer 也应复用该口径。

## CI / Release 计划（基于 GitHub Releases）

### 已有

- tag 触发 release 的 workflow 已存在：`.github/workflows/release.yml`（仅 TUI）
- goreleaser 已能产出 macOS + Linux 二进制并发布 Homebrew cask

### 建议新增（v1）

- 新增 `release-staging` job：
  - job1：构建并上传 TUI（沿用现有 goreleaser）
  - job2：构建 Linux tarball（含 install.sh、sample 配置、启动脚本）
  - job3：构建 Windows bootstrap（初期为 PS wrapper + WSL 指令）
  - 所有资产统一上传到同一 `github.com/Timcai06/SciScope/releases/tag/vX.Y.Z`
- 新增 `release/manifest.json`（待实现）：
  - 列出每个平台资产名、sha256、校验算法、支持的最小安装命令
- 新增 `doctor` 验证 job：
  - 安装脚本下载后执行 `--doctor` 验证主流程

## 签名与校验

- 现状：TUI `goreleaser` 已生成 `checksums.txt`。
- 建议扩展：
  1. 所有产物统一附带 `checksums.txt`。
  2. 可选引入 `cosign/sigstore` 或 `gpg` 对发布清单签名（先定范围）。
  3. 安装脚本内置 `sha256sum -c`（Linux）/`Get-FileHash`（Windows）校验。
  4. macOS cask 保留现有 `xattr` 处理；如签名链完善后可替换为签名验证优先。

## doctor 检查项（安装后即做）

建议新增统一 `sciscope-doctor`（脚本或命令）检查：

1. 二进制版本与体系结构
2. 命令可执行性（`sciscope-tui --version`、可选 `sciscope-backend --version`）
3. 后端健康：
   - `GET /api/ingest/status`（优先）
   - 不依赖 `/health`；如未来新增仅作为兼容别名
4. 路由可达：
   - `/api/chat`
   - `/api/search`
   - `/api/agent/stream`
5. 依赖状态：
   - DB（若配置）：`SCISCOPE_DB_DSN` 可达性
   - 本地模型：`SCISCOPE_USE_MOCK_LLM` 与 `SCISCOPE_LLM_PROVIDER` 对齐
   - `output/graphs` 存在性
6. 目录与权限：
   - `~/.sciscope/sessions` 可写（或 `SCISCOPE_SESSION_DIR` 指定目录可写）
7. 回退验证：
   - 强制启用 mock/sample 路径仍可运行 `/agent` 与 `--demo`

## 失败恢复策略

- 若后端启动失败：先降级到 `--demo`，并提示用户运行 `make install-backend` / `make backend`。
- 若 DB 未就绪：自动设置“样本模式”，将检索类接口返回 503，chat/agent 至少可走内存样本或 mock 回答（按当前服务实现）。
- 若模型服务未就绪：自动切到 `SCISCOPE_USE_MOCK_LLM=true`。
- 若图谱缺失：显示“功能受限（图谱为空）”并提示执行 `make graph-export`。
- 若安装后校验失败：输出失败清单与重试命令（支持 `--reinstall`）。
- 若架构不匹配：安装脚本终止并给出替换指引（amd64↔arm64）。

## 里程碑拆分（MVP -> GA）

- M1（已具备）：TUI Homebrew 路线固化（`tui`）
- M2（本计划一期）：建立统一 release 入口与 Linux tarball+install.sh
- M3（二期）：Windows WSL 安装器 + 安装后 `doctor` 自动化
- M4（三期）：原生 Windows 二进制与统一签名链

## 目前状态汇总

- 已有（可直接写入计划执行）：**Homebrew + TUI 发布链、Makefile 安装入口、TUI demo/doctor、sample/mock 基线**
- 待实现（本次计划应覆盖）：**Linux/Windows 安装脚本与统一 tarball 分发、统一 release 产物清单、doctor 与回退健康校验**
