# SciScope TUI (`sciscope-tui`)

## 1. 产品定位

SciScope TUI 是 Go 语言的终端交互客户端，负责把后端科研代理的 **SSE 事件流**可视化为可读的研究对话。它是“展示层”，核心检索与推理链路仍在 Python 后端（`backend/` 与 `src/`）。  

设计目标：

- 对齐研究型工作流：plan / tool_call / tool_result / reflect / final。
- 优先输出可复现证据（证据卡、时间线、Markdown 导出）。
- 保持离线验收能力（`--demo` / `SCISCOPE_TUI_DEMO`）用于稳定演示。

## 2. 安装与启动

### 2.0 用户安装（Homebrew）

新版 Homebrew 默认拒绝加载第三方 tap 的 cask，需先 trust，因此流程是 **tap → trust → install**：

```bash
brew tap Timcai06/sciscope
brew trust --cask timcai06/sciscope/sciscope-tui   # 新版 Homebrew 对第三方 tap cask 必需
brew install --cask sciscope-tui
sciscope-tui --demo     # 零配置离线体验
```

二进制装到 `/opt/homebrew/bin/sciscope-tui`，安装钩子会自动去除 macOS quarantine 属性。
TUI 是终端客户端，真实问答需连接后端（见 2.1）；无后端时用 `--demo` 体验固定证据流。

### 2.1 正常联调

```bash
make tui         # 启动前需先启动后端
make backend     # 后端：127.0.0.1:8000
make llm         # 本地兼容 LLM：127.0.0.1:8001
```

可选环境变量：

- `SCISCOPE_BACKEND`：自定义后端地址（默认 `http://127.0.0.1:8000`）
- `SCISCOPE_TUI_ICONS=off`：无 Nerd Font 时仅保留文本标签
- `SCISCOPE_TUI_THEME=paper`：启动时选择主题，可选 `dark`、`paper`、`light`、`contrast`

### 2.2 命令行

```bash
sciscope-tui --help
sciscope-tui --version
sciscope-tui demo
sciscope-tui doctor
sciscope-tui export --last
```

## 3. Demo / Offline 流程

`/demo`、`sciscope-tui demo` 与 `SCISCOPE_TUI_DEMO=1` 触发离线演示：

- 不依赖后端/LLM/数据库；
- 按固定轨迹重放“用户问题 → plan → tool_call/result → reflect → final”；
- 方便新成员快速验收“可读输出规范”；
- 演示节奏由 `SCISCOPE_TUI_DEMO_DELAY_MS` 控制（单位毫秒，默认 420ms）。

## 4. 会话与交互能力（/sessions / /resume / /export / /retry）

- `writeSessionMarkdown` 在每轮完成后自动持久化 `sciscope-session-YYYYMMDD-HHMMSS.md` 到会话目录；
- 会话目录优先级：`SCISCOPE_SESSION_DIR` → `~/.sciscope/sessions` → `sessions`；
- `listSessionFiles` 按文件修改时间倒序加载，`/sessions` 展示最近会话；
- `/resume N` 从 `/sessions` 列表恢复历史会话到 transcript；
- `lastQuestion` 变更后，`/retry` 会重放最近一问；
- `/export` 会导出当前 transcript 的 Markdown（与历史恢复格式一致）。
- `sciscope-tui export --last` 可在 shell 中打印最近一条 Markdown 会话，便于管道保存或粘贴到报告。
- `sciscope-tui doctor` 执行后端、LLM、会话目录和图谱资产的产品化体检。
- `/theme` 在 slash 启动器中进入二级主题菜单；`/theme paper` 可直接切换到与报告 PDF 更一致的青绿色品牌主题。
- 最终回答会对“结论、证据、边界、建议”和含引用/指标的行做语义高亮，避免整段输出颜色过于单一。
- `/` 是多级命令启动器：一级菜单用 ↑/↓ 选择命令，Enter 执行；需要继续选择的命令会进入二级菜单，Esc 返回或关闭。

## 5. UI 语义：Splash / Dashboard / panel row

### 5.1 Splash 与 Dashboard

当聊天区为空时，会展示 splash：

- Quick actions（示例）：`/demo`、`/sessions`、`/help`
- System status：后端、LLM、会话目录的入口级状态提示，详细体检走 `/doctor` 或 `sciscope-tui doctor`
- Golden demo 预览：`verify_claim → evidence panel`
- Recent work：最近本地会话（含 `/resume` 提示）
- 终端足够宽时以三栏 miniPanel 组成 Dashboard；不足宽度则纵向 panelRow 列表。

### 5.2 panelRow 渲染语法

`panelRow(kind, title, meta, body)` 的语义：

1. 头部：`╭─ <kind> · <title> [· <meta>]`
2. 每行 body 加 `│  `
3. 尾部：`╰─`

常见 kind：`action`, `evidence`, `verify`, `timeline`, `thinking`, `recovery`。

## 6. Homebrew / GoReleaser 发布路径

- 打包配置位于 `tui/.goreleaser.yaml`；
- 仅发布 Go 终端二进制（`sciscope-tui`），并通过 cask 发布到 `Timcai06/homebrew-sciscope`；
- release 流程在 `.github/workflows/release.yml` 中由 tag 推动：`v*` 打上后触发；
- `go build`/发布产物使用链接时注入：`-X main.version={{ .Version }}`，因此运行时版本由 tag 决定；
- 本地验签预演：`make tui-build TUI_VERSION=x.y.z`，确保 `--version` 输出与预期一致。

## 7. 快速验收清单

- `make tui-build TUI_VERSION=0.2.0` → `tui/sciscope-tui --version`
- `make tui-doctor`，确认发布前环境体检输出可读。
- `make tui` 连接真实后端，执行一条测试问题，观察 plan/tool/result/final 流。
- `make tui-demo`，确认完整离线演示可完整播完。
- `make tui-export-last`，确认最近会话可从命令行导出。
- `/sessions` 能列出最近会话，`/resume` 和 `/sessions` 可在 slash 启动器中进入二级会话菜单，`/tools` 可进入工具详情菜单，`/doctor` 可进入检查项菜单，`/clear` 与 `/quit` 会先进入确认菜单，`/export` 可用。
