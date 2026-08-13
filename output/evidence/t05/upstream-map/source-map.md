# T05-00｜Grok → SciScope 源码对标矩阵

- 生成时间：2026-08-13
- 上游：`xai-org/grok-build` GitHub commit `e5fd4816d43260c15ba785f103990c1ed6cea230`（`SOURCE_REV=ea094a8c369475f97c85540d01730baec0dce5d6`）
- 本地克隆：`.vendor/grok-build`（浅克隆，`--depth 1`，已加入 `.gitignore`）
- SciScope 基线：HEAD `bc2cc4316bfd9fc41f4030059543ce6c6c505ede`（T05 计划文档提交 `17a7c0d`）
- 对标口径：`copy behavior`（行为级照搬）/ `adapt`（按 SciScope 领域适配）/ `do not copy`（品牌/业务/合规禁止）
- 未读源码不写进本表；本表只覆盖 T05-00 实际阅读过的文件。

## 一、app 层（Elm 架构 → Bubble Tea）

| Grok 参考（已读） | SciScope 当前 | 对标行为 | 口径 | 对应任务 |
|---|---|---|---|---|
| `src/app/actions.rs`（Action/Effect/TaskResult 三枚举单向管道） | `tui/main.go` Msg/Update/Cmd 混于 model | 单向管道：input→Action→dispatch(纯同步)→Vec<Effect>→async task→TaskResult→再入 dispatch | `adapt`（Go 用 interface+type switch 替代穷尽 match） | T05-02 / T05-10 |
| `src/app/dispatch/mod.rs`（invariant：不碰 IO、确定性、可脱离 tokio 测试） | Update 里混杂 IO 与渲染状态 | dispatch/reducer 无 IO、纯同步可测 | `copy behavior` | T05-10 |
| `src/app/dispatch/router.rs`（match 路由到 20+ 领域子模块） | 单文件 Update | 按领域分子模块，router 只做分发 | `copy behavior` | T05-10 |
| `src/app/effects/mod.rs`（Effect 枚举统一表达副作用，spawn 成 task） | tea.Cmd 零散构造 | Effect 枚举统一表达 IO 副作用、延迟执行 | `adapt`（Bubble Tea Cmd 为串行队列，需 context cancel 补并发取消） | T05-02 / T05-10 |
| `src/app/event_loop.rs`（薄循环：select+drain+process_effects） | model 内嵌逻辑 | event loop 保持薄 | `copy behavior` | T05-10 |
| `src/app/app_view.rs`（AppView 持有全部状态，handle_input 返回声明式 InputOutcome） | model 混合 domain 与 UI 状态 | 输入处理返回声明式 outcome，view 不直接执行副作用 | `adapt`（Go 单 goroutine 纪律替代 &mut 独占借用） | T05-02 |
| `actions.rs` 的 seq/generation 丢弃过期异步结果 | 无 | 异步结果带代际号，过期丢弃 | `copy behavior` | T05-02 |

## 二、scrollback 层（typed block 模型）

| Grok 参考（已读） | SciScope 当前 | 对标行为 | 口径 | 对应任务 |
|---|---|---|---|---|
| `src/scrollback/block.rs`（RenderBlock 枚举 13 类 + BlockContent trait） | `conversationBlock` 最小缓存、blockItems 字符串拼接 | typed block record，渲染是纯投影；折叠/分组/渲染契约集中在块类型 | `adapt`（Go interface 替代 trait；kind 集按 SciScope：user/research_plan/tool_group/tool_result/research_trace/evidence/answer/contract/recovery/system） | T05-02 / T05-04 |
| `src/scrollback/entry.rs`（EntryId(u64) 单调分配；四级输出缓存） | 无稳定 ID、无分级缓存 | 单调 EntryId；缓存键含 width/theme/cwd/selection，非键变化不重渲 | `copy behavior` | T05-02 |
| `entry.rs` 的 cached_line_widths 与宽度解耦 | 无 | 行宽缓存宽度无关，resize 不 O(n) 失效 | `copy behavior` | T05-02 / T05-11 |
| `src/scrollback/state/`（DisplayMode 三态：Collapsed/Truncated/Expanded；display_mode_pinned 用户 pin 优先） | 无折叠模型 | 三态折叠 + 每块自定义 next_fold_mode/finished_display_mode；用户手动折叠优先于自动模式 | `copy behavior` | T05-04 / T05-05 |
| `src/scrollback/state/groups.rs`（GroupSpan 折叠模型：决策与投影分离） | 无 grouping | 折叠模型单点决策、单点投影，消费者不观察不一致形状 | `copy behavior` | T05-04 |
| `src/scrollback/state/layout.rs`（prepare_layout 三档：全量估算+可见区精确测量/增量 patch/纯 scroll） | 全量重渲染 | 布局懒测量：估算高度 + 视口内精确测量，O(viewport) 非 O(history) | `adapt`（先建立等价可见性测量，T05-11 性能门禁验证） | T05-02 / T05-11 |
| `src/scrollback/state/selection.rs`（fold 锚定、增长丢 follow） | follow 逻辑简单 | 折叠是显示态变化而非导航：锚定 scroll；折叠增长视为阅读意图丢 follow | `copy behavior` | T05-09 |
| `src/scrollback/export.rs`（导出走 RenderBlock 源文本纯函数，跳过 UI chrome） | `/export` 直接消费 transcript | transcript 是持久事实、UI chrome 不污染导出 | `copy behavior`（现状已接近，T05 保持） | T05-02 / TX02 |

## 三、views 层（视觉/交互语法）

| Grok 参考（已读） | SciScope 当前 | 对标行为 | 口径 | 对应任务 |
|---|---|---|---|---|
| `src/views/welcome/`（垂直居中 顶栏→logo→menu→tip→prompt；≥90 列 hero_box 单面板，窄屏 stacked） | `renderSplash` 三栏 Dashboard + 外层大 Card | 非 Dashboard 卡片；宽屏 Logo 是第一视觉、composer 第二；menu 行可交互 | `adapt`（保留 SciScope ASCII Logo 与 Recent Session；Grok braille logo、「Thanks for trying Grok Build」等文案 `do not copy`） | T05-03 |
| `src/views/prompt_widget/mod.rs`（PromptStyle 驱动 focus/prefix/chrome；focus 只改色；Enter 提交 Shift/Alt-Enter 换行；PromptInfo 行） | `textinput.Model` + 分散状态 | composer 只负责编辑/多行/提交，chrome 由样式参数驱动；focus 只改色不折叠 | `copy behavior` | T05-07 |
| `src/views/modal.rs`（ActiveModal 统一枚举）、`modal_window.rs`（统一弹窗 chrome，返回内容 Rect） | Command Palette + submenu 字符串渲染 | 统一 modal 状态与 chrome；chrome 与内容解耦 | `copy behavior` | T05-08 |
| `src/views/overlay.rs`（三态覆盖层状态机，Esc 逐级）、`overlay_list.rs`（未聚焦 dim） | menu/submenu 内嵌 | 统一 overlay 状态机、Esc 层级（子 picker→父 picker→close） | `copy behavior` | T05-08 |
| `src/views/picker.rs`（统一 PickerState + 选中态三件套：bg+bold+❯） | 各菜单自行渲染 | 选中态三件套统一；搜索、分组、selection、usage 现代列表语法 | `copy behavior` | T05-08 |
| `src/views/slash_dropdown.rs`（label 列对齐 ≤60% cap40、fuzzy 命中高亮、[tag] badge 计入列宽） | `/` launcher + filter | label 列对齐、描述截断、fuzzy 高亮、badge | `copy behavior` | T05-08 |
| `src/views/status_bar.rs`（左/中/右三槽灰字）、`context_bar.rs`（hover 不位移）、`shortcuts_bar.rs`（key/label/分隔三档层级、compact 同代码+参数） | 分散 status / hints | 一条低视觉权重 status + 不超过一行的 shortcut strip；hover 不产生布局位移 | `copy behavior`（Grok 的 credit/usage 业务 `do not copy`） | T05-07 |
| `src/views/turn_status.rs`（运行态占 1 行、idle 高度 0、spinner 降频）、`timeline.rs`（turn tick 轨道，<60 列隐藏） | workflow status + `/timeline` | 主界面 compact Research Trace：running 展开、finished 折叠为一行；完整 `/timeline` 保留 | `adapt`（Grok turn → SciScope Research Trace） | T05-05 |
| 各 view 的 height()/should_show() 预计算、几何与 hit-test 共享 | 渲染时计算 | 高度预计算、布局推式而非渲染挤式 | `copy behavior` | T05-03~09 |

## 四、do not copy 清单（品牌/业务/合规）

| 项 | 出处 | 原因 |
|---|---|---|
| Grok/xAI/SpaceXAI 名称、braille Grok logo、营销文案 | `src/views/welcome/logo`、README | 品牌资产 |
| supergrok/paywall、Tier/[Refresh]/Upgrade、额度 bar | `src/views/credit_bar.rs` | Grok 商业业务 |
| Import Claude settings、@file 引用、worktree、voice overlay、plan approval | `src/views/import_claude_modal.rs` 等 | coding-agent 业务，无 SciScope 需求 |
| 模型名、auth/device-code 流程 | `docs/user-guide/02-authentication.md` | Grok 特有 |
| 任何 vendored/移植代码直接搬移 | `third_party/`、`xai-grok-tools/THIRD_PARTY_NOTICES.md` | TX01：必须行为级重实现或完整 provenance |
| Rust/Ratatui 运行时引入 | 整个 crate | 禁止第二套 TUI runtime |

## 五、测试思路对标

| Grok 参考 | SciScope 现状 | 目标 | 任务 |
|---|---|---|---|
| `app_view_tests.rs`、`scrollback/render_tests.rs`、`views/shortcuts_help_tests.rs`（组件级 snapshot + state transition） | `main_test.go` 2054 行大而全行为测试 | 分组件 render snapshot + state transition + width matrix | T05-11 |
| `test_util.rs`（共享 fixture/断言） | fixture 内嵌各测试 | 测试工具独立，跟随 view 拆分 | T05-10 / T05-11 |

## 六、与计划第六节的差异记录

计划第六节「Grok Build 参考区域」列出的路径经 T05-00 实际核对**全部存在**，无过时路径；但有三处细化：

1. 计划写 `src/app/actions.rs` → 实际同时存在 `src/app/actions.rs` 与独立的 `src/actions/` 目录（后者为 defaults.rs+mod.rs，管线枚举定义在 `src/app/actions.rs`）。
2. `src/scrollback/` 不是单个文件而是 16 个文件的模块（block.rs/entry.rs/state//groups.rs/export.rs 等），本矩阵按实际子文件细化。
3. `src/views/welcome/`、`src/views/prompt_widget/` 是目录（mod.rs + 多文件），计划路径表述正确但粒度需按子文件记录。
