// update.go — T05-10 文件职责收敛：Bubble Tea 事件处理（update routing）。
//
// 从 main.go 搬移（行为零变化，纯文件拆分）：
//   - Update 主路由（stream 事件、键位、窗口尺寸）
//   - scrollback 内容维护：appendBlock / syncBlockItems / setViewportContent / refresh
package main

import (
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
)

func (m *model) appendBlock(kind BlockKind, s string) {
	m.blocks = append(m.blocks, s)
	m.blockItems = append(m.blockItems, newScrollbackBlock(kind, s))
	m.blocksVersion++
	m.refresh()
}

func (m *model) appendUserMessage(text string, retry bool) {
	m.blocks = append(m.blocks, text)
	m.blockItems = append(m.blockItems, newScrollbackBlock(BlockUser, text))
	m.blockItems[len(m.blockItems)-1].Retry = retry
	m.blocksVersion++
	m.refresh()
}

func (m *model) appendAnswerMessage(text string, tools []string) {
	copiedTools := append([]string(nil), tools...)
	m.blocks = append(m.blocks, text)
	m.blockItems = append(m.blockItems, newScrollbackBlock(BlockAnswer, text))
	m.blockItems[len(m.blockItems)-1].Tools = copiedTools
	m.blocksVersion++
	m.refresh()
}

func (m *model) syncBlockItems() {
	if len(m.blockItems) == len(m.blocks) {
		matched := true
		for i := range m.blocks {
			if m.blockItems[i].Raw != m.blocks[i] {
				matched = false
				break
			}
		}
		if matched {
			return
		}
	}
	m.blockItems = make([]ScrollbackBlock, len(m.blocks))
	for i, raw := range m.blocks {
		m.blockItems[i] = newScrollbackBlock(BlockMessage, raw)
	}
	m.blocksVersion++
}

func (m *model) record(kind, tool, content string) {
	content = strings.TrimSpace(content)
	if content == "" {
		return
	}
	m.transcript = append(m.transcript, transcriptEvent{Kind: kind, Tool: tool, Content: content})
}

func (m *model) addTimeline(ev timelineEvent) {
	if ev.Label == "" {
		ev.Label = toolPlainLabel(ev.Tool)
	}
	m.timeline = append(m.timeline, ev)
}

func formatHTTPError(resp *http.Response) string {
	payload, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	detail := strings.TrimSpace(string(payload))
	if detail == "" {
		detail = resp.Status
	}
	return fmt.Sprintf("后端返回 %s: %s", resp.Status, detail)
}

func (m *model) setViewportContent(content string, followBottom bool) {
	if content == m.viewportContent {
		if followBottom || m.vp.PastBottom() {
			m.vp.GotoBottom()
		}
		return
	}
	m.vp.SetContent(content)
	m.viewportContent = content
	m.viewportContentVersion++
	if followBottom {
		m.vp.GotoBottom()
	}
}

func (m *model) refresh() {
	m.refreshTranscript()
}

func (m *model) refreshTranscript() {
	content := m.renderTranscriptContent(m.vp.Width)
	if strings.TrimSpace(content) == "" && m.vp.Width > 0 {
		m.loadRecentSessions()
		content = renderWelcome(m.vp.Width, m.recentSessions, nil)
	}
	// Follow new content only when already pinned to the bottom; if the user has
	// scrolled up to read, keep their position instead of yanking them down.
	atBottom := m.vp.AtBottom()
	m.setViewportContent(content, atBottom)
	m.lastRefresh = time.Now()
	m.refreshPending = false
}

func (m *model) requestStreamRefresh() tea.Cmd {
	if m.lastRefresh.IsZero() || time.Since(m.lastRefresh) >= streamRefreshInterval {
		m.refresh()
		return nil
	}
	if m.refreshPending {
		return nil
	}
	m.refreshPending = true
	wait := streamRefreshInterval - time.Since(m.lastRefresh)
	if wait < 0 {
		wait = 0
	}
	return tea.Tick(wait, func(time.Time) tea.Msg {
		return refreshTickMsg{}
	})
}

// Update 是 Bubble Tea 事件入口。为满足提示词「Msg → Action → State Update →
// Effect → New Msg」分层，Update 只做领域分发（Action 路由），各领域处理器
// 独占一类消息的 State Update，并返回 Effect（tea.Cmd）。
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		return m.updateWindowSize(msg)
	case demoStartMsg:
		return m.updateDemoStart(msg)
	case nodePulseMsg:
		m.lastMeta = msg.meta
		m.lastStreamKind = msg.kind
		m.nodeSeen = appendUniqueNode(m.nodeSeen, msg.meta.Node)
		return m, listen(m.sub)
	case refreshTickMsg:
		if m.refreshPending {
			m.refresh()
		}
		return m, nil
	case spinner.TickMsg:
		return m.updateSpinnerTick(msg)
	case tea.MouseMsg:
		return m.updateMouse(msg)
	case tea.KeyMsg:
		if m.searchMode {
			// 搜索模式：字符/退格进 query（updateKey 只处理 enter/esc 等控制键）。
			if msg.Type == tea.KeyRunes || msg.String() == "backspace" || msg.String() == "space" {
				return m.updateSearchKey(msg)
			}
		}
		return m.updateKey(msg)
	case planMsg, textMsg, toolCallMsg, toolResultMsg, reflectMsg, finalMsg, errMsg, doneMsg:
		return m.updateStreamMsg(msg)
	default:
		if m.searchMode {
			// 搜索模式：字符/退格进入 query，不流入 composer。
			return m.updateSearchKey(msg)
		}
		var cmd tea.Cmd
		m.ti, cmd = m.ti.Update(msg)
		return m, cmd
	}
}

// updateWindowSize：布局（Action=Window）。viewport 尺寸预算统一在这里计算
// （布局与渲染分层；三档响应式档位见 layoutTier）。
func (m model) updateWindowSize(msg tea.WindowSizeMsg) (model, tea.Cmd) {
	// 布局预算：外框左右 4 列（边框 2 + padding 2）；高度：外框上下 2 行 +
	// status 1 行 + composer 4 行（边框 2 + textarea 2 行内容）。
	innerW := msg.Width - 4
	if innerW < 40 {
		innerW = msg.Width
	}
	vh := msg.Height - 2 - 5
	if vh < 3 {
		vh = 3
	}
	if !m.ready {
		m.vp = newTranscriptViewport(innerW, vh)
		m.loadRecentSessions()
		m.setViewportContent(renderWelcome(innerW, m.recentSessions, nil), true)
		m.ready = true
	} else {
		wasAtBottom := m.vp.AtBottom()
		m.vp.Width, m.vp.Height = innerW, vh
		// T05-09 resize 锚定：resize 前在底部则保持贴底（streaming
		// 跟随场景），否则保持 YOffset（viewport 内部 clamp）。
		if wasAtBottom {
			m.vp.GotoBottom()
		}
		if len(m.blocks) == 0 && m.answer == "" {
			m.loadRecentSessions()
			m.setViewportContent(renderWelcome(innerW, m.recentSessions, nil), true)
		}
	}
	m.ti.SetWidth(innerW - 2)
	return m, nil
}

// updateDemoStart：离线演示流起始（Action=Demo）。
func (m model) updateDemoStart(msg demoStartMsg) (model, tea.Cmd) {
	v := string(msg)
	m.ti.SetValue("")
	m.appendUserMessage(v, false)
	m.record("user", "", v)
	m.history = append(m.history, turn{"user", v})
	m.lastQuestion = v
	m.answering = true
	m.answer = ""
	m.answerRunningID = ""
	m.used = nil
	m.toolStart = map[string]time.Time{}
	m.timeline = nil
	m.lastMeta = eventMeta{}
	m.lastStreamKind = ""
	m.nodeSeen = nil
	m.livePlan = nil
	m.liveReflect = ""
	m.verb = "演示中"
	m.start = time.Now()
	return m, listen(m.sub)
}

// updateSpinnerTick：spinner 动画帧（Effect=Tick）。
func (m model) updateSpinnerTick(msg spinner.TickMsg) (model, tea.Cmd) {
	if !m.answering {
		return m, nil
	}
	var cmd tea.Cmd
	m.spin, cmd = m.spin.Update(msg)
	m.tick++
	if m.tick%12 == 0 {
		m.verb = verbs[rand.Intn(len(verbs))]
	}
	return m, cmd
}

// updateMouse：鼠标滚轮滚动 transcript（Action=Mouse）。
func (m model) updateMouse(msg tea.MouseMsg) (model, tea.Cmd) {
	// Mouse wheel scrolls the transcript viewport.
	if isVerticalWheel(msg) {
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	}
	return m, nil
}

// updateKey：键盘事件（Action=Key）。焦点/模式决定键位语义：submenu、/ 命令
// 菜单、transcript 滚动、composer 输入。
func (m model) updateKey(msg tea.KeyMsg) (model, tea.Cmd) {
	var cmd tea.Cmd
	switch msg.String() {
	case "ctrl+c":
		return m, tea.Quit
	case "ctrl+f":
		// T05-12：transcript 搜索（Block 级能力）。
		m.startSearch()
		return m, nil
	case "ctrl+g":
		// T05-12：block 选择模式。
		m.startSelect()
		return m, nil
	case "esc":
		if m.searchMode {
			m.stopSearch()
			return m, nil
		}
		if m.selectMode {
			m.stopSelect()
			return m, nil
		}
		if m.submenu != "" && !m.answering {
			m.submenu = ""
			m.submenuIdx = 0
			m.ti.SetValue("/")
			return m, nil
		}
		if strings.HasPrefix(m.ti.Value(), "/") && !m.answering {
			m.ti.SetValue("")
			m.menuIdx = 0
			return m, nil
		}
		if m.answering && m.cancel != nil {
			m.cancel()
		}
		return m, nil
	case "pgup", "pgdown", "ctrl+u", "ctrl+d":
		// Keyboard scrolling of the transcript (viewport's own keymap).
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	case "home", "end":
		// T05-09：viewport 默认 keymap 不含 home/end，显式处理。
		if msg.String() == "home" {
			m.vp.GotoTop()
		} else {
			m.vp.GotoBottom()
		}
		return m, nil
	case "ctrl+j":
		// 提示词 Composer 换行支持：Enter 发送、Ctrl+J（\n）换行。
		// bubbletea 不解析 shift+enter 的 CSI u 序列，Ctrl+J 是所有终端
		// 都可靠发送 \n 的等价键。
		m.ti.InsertString("\n")
		return m, nil
	case "up", "down", "tab":
		if m.selectMode {
			if msg.String() == "up" {
				m.moveSelect(-1)
			} else if msg.String() == "down" {
				m.moveSelect(1)
			}
			return m, nil
		}
		if m.submenu != "" {
			items := m.submenuItems()
			if len(items) > 0 {
				switch msg.String() {
				case "up":
					m.submenuIdx = (m.submenuIdx - 1 + len(items)) % len(items)
				case "down":
					m.submenuIdx = (m.submenuIdx + 1) % len(items)
				case "tab":
					m.ti.SetValue(items[m.submenuIdx%len(items)].command)
				}
				return m, nil
			}
		}
		if strings.HasPrefix(m.ti.Value(), "/") {
			ms := filterCmds(m.ti.Value())
			if len(ms) > 0 {
				switch msg.String() {
				case "up":
					m.menuIdx = (m.menuIdx - 1 + len(ms)) % len(ms)
				case "down":
					m.menuIdx = (m.menuIdx + 1) % len(ms)
				case "tab":
					m = stageCommand(m, ms[m.menuIdx%len(ms)])
				}
				return m, nil
			}
		}
		// T05-09：无 submenu、无 / 命令菜单时的 up/down 语义（提示词 Composer：
		// 多行输入时在行间移动光标；单行且有历史时浏览历史；否则滚动 transcript）。
		if msg.String() != "tab" {
			if strings.Contains(m.ti.Value(), "\n") {
				m.ti, cmd = m.ti.Update(msg)
				return m, cmd
			}
			if m.ti.Value() != "" && len(m.inputHistory) > 0 {
				m.browseHistory(msg.String() == "up")
				return m, nil
			}
			m.vp, cmd = m.vp.Update(msg)
			return m, cmd
		}
	case "enter":
		if m.searchMode {
			// Enter：跳下一个匹配。
			m.stepSearch(1)
			return m, nil
		}
		if m.selectMode {
			// Enter：折叠/展开选中块。
			if m.selectIdx >= 0 && m.selectIdx < len(m.blockItems) {
				b := &m.blockItems[m.selectIdx]
				m.setExpanded(b.ID, !b.Expanded)
			}
			return m, nil
		}
		if m.submenu != "" {
			items := m.submenuItems()
			if len(items) > 0 {
				v := items[m.submenuIdx%len(items)].command
				m.submenu = ""
				m.submenuIdx = 0
				m.ti.SetValue("")
				next, cmd := m.runSlash(v)
				return next.(model), cmd
			}
			return m, nil
		}
		v := strings.TrimSpace(m.ti.Value())
		if v == "" || m.answering {
			// T05-05：输入为空时 Enter 切换最近轨迹块折叠（plan/trace）。
			if v == "" && !m.answering {
				m.toggleLatestTrace()
			}
			return m, nil
		}
		if strings.HasPrefix(v, "/") {
			if ms := filterCmds(m.ti.Value()); len(ms) > 0 && m.menuIdx < len(ms) && !strings.Contains(v, " ") {
				selected := ms[m.menuIdx]
				// A command that takes an argument is staged as "/cmd <>" with the
				// cursor in the slot, instead of running with an empty argument.
				if commandNeedsArg(selected) {
					m = stageCommand(m, selected)
					m.menuIdx = 0
					return m, nil
				}
				v = selected.cmd
			}
			if submenu := commandSubmenu(v); submenu != "" {
				m.openSubmenu(submenu)
				m.menuIdx = 0
				return m, nil
			}
			m.ti.SetValue("")
			m.menuIdx = 0
			next, cmd := m.runSlash(v)
			return next.(model), cmd
		}
		cmd := m.startQuestion(v, false)
		m.pushHistory(v)
		return m, cmd
	default:
		// 可打印字符/空格：转交 textinput（composer 键入）。
		// 必须显式转发——KeyRunes 不会落入 Update 路由的 default 分支
		// （KeyMsg 被 case tea.KeyMsg 截获后直达 updateKey）。
		if msg.Type == tea.KeyRunes || msg.Type == tea.KeySpace {
			m.ti, cmd = m.ti.Update(msg)
		}
		return m, cmd
	}
	// 不可达（所有 case 均 return），仅为编译器穷尽性。
	return m, cmd
}

// updateStreamMsg：SSE 流式事件（Action=Stream）。各事件更新自己的领域状态
// 并保持 listen 监听链（Effect=listen）。
func (m model) updateStreamMsg(msg tea.Msg) (model, tea.Cmd) {
	switch msg := msg.(type) {

	case planMsg:
		plain := []string{}
		for _, s := range msg {
			plain = append(plain, "- "+s)
		}
		m.addTimeline(timelineEvent{Kind: "plan", Phase: "制定研究计划", Label: "执行计划", Detail: strings.Join([]string(msg), " / ")})
		m.record("plan", "", strings.Join(plain, "\n"))
		m.livePlan = append([]string(nil), msg...)
		// 语义化：PlanSteps 存结构化步骤，Raw 存纯文本；着色发生在渲染层。
		m.appendPlanBlock(msg)
		return m, listen(m.sub)

	case toolCallMsg:
		m.used = append(m.used, msg.name)
		if m.toolStart == nil {
			m.toolStart = map[string]time.Time{}
		}
		m.toolStart[msg.name] = time.Now()
		detail := m.argsStr(msg.args)
		if a := m.argsStr(msg.args); a != "" {
			m.record("tool_call", msg.name, a)
		} else {
			m.record("tool_call", msg.name, toolLabel(msg.name))
		}
		if meta := metaDetail(msg.meta); meta != "" {
			if detail != "" {
				detail += " · " + meta
			} else {
				detail = meta
			}
		}
		m.addTimeline(timelineEvent{Kind: "tool_call", Phase: metaPhase(msg.meta), Tool: msg.name, Label: toolPlainLabel(msg.name), Detail: detail})
		// 语义化：running tool 块（ToolName/ToolArgs 结构化），渲染层按三态着色。
		m.startToolBlock(msg.name, m.argsStr(msg.args))
		if notice, ok := permissionNotice(msg.name); ok {
			m.record("permission", msg.name, notice)
			m.addTimeline(timelineEvent{Kind: "permission", Phase: metaPhase(msg.meta), Tool: msg.name, Label: "权限提示", Detail: notice})
		}
		return m, listen(m.sub)

	case toolResultMsg:
		var elapsed time.Duration
		if m.toolStart != nil {
			elapsed = time.Since(m.toolStart[msg.name])
		}
		m.addTimeline(timelineEvent{Kind: "tool_result", Phase: metaPhase(msg.meta), Tool: msg.name, Label: toolResultLabel(msg.name, msg.result), Detail: metaDetail(msg.meta), Duration: elapsed})
		m.record("tool_result", msg.name, summarizeToolResultMarkdown(msg.name, msg.result))
		// Tool Call 生命周期转正：running → succeeded/failed；摘要并入 tool 行，
		// 不再 append 日志式结果块（提示词：Tool 不要像日志）。
		status := BlockSucceeded
		summary := toolResultSummary(msg.name, msg.result)
		if strings.HasPrefix(msg.result, "[未执行]") {
			status = BlockFailed
		}
		m.finishLatestToolBlock(msg.name, status, summary, elapsed)
		// 证据类工具：结果另存为 typed Evidence 领域对象卡（Raw=JSON 原文，
		// 渲染层解析；不预渲染 ANSI）。
		if isEvidenceTool(msg.name) {
			b := newScrollbackBlock(BlockEvidence, msg.result)
			b.ToolName = msg.name
			b.ToolDuration = elapsed
			b.ToolSummary = summary
			m.blocks = append(m.blocks, msg.result)
			m.blockItems = append(m.blockItems, b)
			m.blocksVersion++
			m.refresh()
		}
		return m, listen(m.sub)

	case reflectMsg:
		m.answer = ""
		m.record("reflect", "", string(msg))
		m.liveReflect = string(msg)
		m.addTimeline(timelineEvent{Kind: "reflect", Phase: "自检修正", Label: "自检修正", Detail: string(msg)})
		// 语义化：Raw=纯文本自检内容，Meta 标记来源，渲染层着色。
		b := newScrollbackBlock(BlockResearchTrace, string(msg))
		b.Meta = "reflect"
		m.blocks = append(m.blocks, string(msg))
		m.blockItems = append(m.blockItems, b)
		m.blocksVersion++
		m.refresh()
		return m, listen(m.sub)

	case textMsg:
		if m.answerRunningID == "" {
			// T05-04: 第一个流式 chunk 创建 running answer 块；后续 chunk 更新同一块。
			m.answerRunningID = m.startRunningBlock(BlockAnswer)
			m.answering = true
			m.maybeAnchorToPrompt()
		}
		// 清洗 LLM 输出中的字面 ANSI 残骸（无 ESC 前缀的 [0m / [38;5;252m
		// 等）：训练数据里的终端日志残留，终端会原样显示成乱码。
		m.answer += stripLiteralSGRResidue(string(msg))
		m.updateRunningBlock(m.answerRunningID, m.answer)
		return m, tea.Batch(m.requestStreamRefresh(), listen(m.sub))

	case finalMsg:
		if m.answer == "" {
			m.answer = string(msg)
		}
		if m.answerRunningID == "" && m.answer != "" {
			// 兼容无 textMsg 的 finalMsg 直达路径（fixture/异常流）：补建 running 块。
			m.answerRunningID = m.startRunningBlock(BlockAnswer)
			m.updateRunningBlock(m.answerRunningID, m.answer)
			m.answering = true
		}
		m.refreshPending = false
		m.refresh()
		return m, listen(m.sub)

	case errMsg:
		errText := friendlyError(string(msg))
		m.record("error", "", errText)
		action := recoveryAction(string(msg))
		m.addTimeline(timelineEvent{Kind: "error", Phase: "错误恢复", Label: action.Title, Detail: action.Message})
		// 语义化：Raw=原始错误文本，渲染层重建 recovery 面板。
		m.appendBlock(BlockRecovery, string(msg))
		m.lastTurnErr = errText
		return m, listen(m.sub)

	case doneMsg:
		if m.answer != "" {
			ans := m.answer
			m.answering = false
			m.addTimeline(timelineEvent{Kind: "final", Phase: "综合回答", Label: "回答完成"})
			if body := timelineMarkdownBody(m.timeline); body != "" {
				m.record("timeline", "", body)
			}
			if line := contractSummaryText(m.lastMeta.StructuredAnswer); line != "" {
				b := newScrollbackBlock(BlockContract, line)
				b.Meta = "contract"
				m.blocks = append(m.blocks, line)
				m.blockItems = append(m.blockItems, b)
				m.blocksVersion++
			}
			m.record("assistant", "", ans)
			if m.answerRunningID != "" {
				// T05-04: running answer 块转正——同一块 ID。
				// Raw 必须写纯文本源（ans）：renderBlocksContent 的重渲
				// 走 renderConversationBlock → renderAnswerMessage(Raw)。
				// 若把渲染结果写进 Raw，Glamour 会对含 ANSI 的文本再渲染，
				// 把 ESC 转义剥落产生字面 [0m[38;5;252m 乱码（项目负责人
				// 真机反馈的根因）。
				m.finishRunningBlock(m.answerRunningID)
				m.setBlockContent(m.answerRunningID, ans, m.used)
				m.answerRunningID = ""
			} else {
				m.appendAnswerMessage(ans, m.used)
			}
			m.history = append(m.history, turn{"assistant", ans})
			if len(m.history) > 12 {
				m.history = m.history[len(m.history)-12:]
			}
		}
		// Persist even a failed turn (error with no final answer) so the failure
		// reason survives /export and /resume instead of being lost.
		if m.answer != "" || m.lastTurnErr != "" {
			if path, err := writeSessionMarkdown(sessionDir(), m.transcript, time.Now()); err == nil {
				m.lastExport = path
				if m.lastTurnErr != "" {
					m.appendBlock(BlockSystem, stFaint.Render("  会话已保存(含失败原因): "+path))
				} else {
					m.appendBlock(BlockSystem, stFaint.Render("  会话已保存: "+path))
				}
			} else {
				m.appendBlock(BlockSystem, stWarn.Render("  会话保存失败: "+err.Error()))
			}
		}
		m.answer = ""
		m.answering = false
		m.answerRunningID = ""
		m.anchorNextTurn = false
		m.autoFoldTraces() // T05-05：首屏优先看到结论而非 workflow engine
		m.livePlan = nil
		m.liveReflect = ""
		m.lastTurnErr = ""
		m.cancel = nil
		m.refresh()
		return m, nil
	}
	return m, nil
}
