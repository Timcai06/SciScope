# SciScope 下载与发布索引

这是 SciScope 终端客户端的下载入口。所有渠道安装的都是同一个 Go TUI
二进制，发布版默认连接托管后端；普通用户不需要在本机启动 Python 后端、
PostgreSQL 或模型服务。

## 推荐安装方式

| 平台 | 推荐命令 | 说明 |
| --- | --- | --- |
| macOS / Windows / Linux | `npm install -g sciscope-tui` | 已有 Node.js 时最省心，跨平台一致。 |
| macOS | `brew install --cask sciscope-tui` | 适合 Homebrew 用户，首次安装需先 tap 和 trust。 |
| Windows | `scoop install sciscope-tui` | 适合 Scoop 用户，由我们自己的 bucket 控制更新节奏。 |
| 任意平台 | GitHub Release asset | 包管理器不可用时的手动兜底。 |

## npm

```bash
npm install -g sciscope-tui
sciscope-tui
```

npm 包名：`sciscope-tui`

详细说明：[tui-npm.md](tui-npm.md)

## Homebrew

```bash
brew tap Timcai06/sciscope
brew trust --cask timcai06/sciscope/sciscope-tui
brew install --cask sciscope-tui
sciscope-tui
```

详细说明：[tui-homebrew.md](tui-homebrew.md)

## Scoop

```powershell
scoop bucket add sciscope https://github.com/Timcai06/scoop-sciscope
scoop install sciscope-tui
sciscope-tui
```

详细说明：[tui-windows.md](tui-windows.md)

## 常用运行命令

```bash
sciscope-tui
sciscope-tui demo
sciscope-tui doctor
sciscope-tui --version
```

开发者覆盖后端地址：

```bash
SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```

PowerShell:

```powershell
$env:SCISCOPE_BACKEND="http://127.0.0.1:8000"
sciscope-tui
```

## 包边界

包管理器只安装终端客户端，不安装 Python 后端、PostgreSQL/pgvector、语料、
向量或模型资产。普通用户默认使用托管产品；开发者可以从源码运行后端，再用
`SCISCOPE_BACKEND` 指向本地服务。
