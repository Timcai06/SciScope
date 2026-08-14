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

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		// 布局预算：外框左右 4 列（边框 2 + padding 2）；高度：外框上下 2 行 +
		// status 1 行 + composer 3 行（含自身边框）。
		innerW := msg.Width - 4
		if innerW < 40 {
			innerW = msg.Width
		}
		vh := msg.Height - 2 - 4
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
			// T05-09 resize 锚定：resize 前在底部则保持贴底（streaming 跟随
			// 场景），否则保持 YOffset（viewport 内部 clamp）。
			if wasAtBottom {
				m.vp.GotoBottom()
			}
			if len(m.blocks) == 0 && m.answer == "" {
				m.loadRecentSessions()
				m.setViewportContent(renderWelcome(innerW, m.recentSessions, nil), true)
			}
		}
		m.ti.Width = innerW - 2

	case demoStartMsg:
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
		if !m.answering {
			return m, nil
		}
		m.spin, cmd = m.spin.Update(msg)
		m.tick++
		if m.tick%12 == 0 {
			m.verb = verbs[rand.Intn(len(verbs))]
		}
		return m, cmd

	case tea.MouseMsg:
		// Mouse wheel scrolls the transcript viewport.
		if isVerticalWheel(msg) {
			m.vp, cmd = m.vp.Update(msg)
		}
		return m, cmd

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit
		case "esc":
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
		case "up", "down", "tab":
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
			// T05-09：无 submenu、无 / 命令菜单时，up/down 委托 viewport 滚动
			// （单行输入框里 up/down 本无意义；滚动 transcript 更符合沉浸式预期）。
			if msg.String() != "tab" {
				m.vp, cmd = m.vp.Update(msg)
				return m, cmd
			}
		case "enter":
			if m.submenu != "" {
				items := m.submenuItems()
				if len(items) > 0 {
					v := items[m.submenuIdx%len(items)].command
					m.submenu = ""
					m.submenuIdx = 0
					m.ti.SetValue("")
					return m.runSlash(v)
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
				return m.runSlash(v)
			}
			cmd := m.startQuestion(v, false)
			return m, cmd
		}

	case planMsg:
		plain := []string{}
		for _, s := range msg {
			plain = append(plain, "- "+s)
		}
		m.addTimeline(timelineEvent{Kind: "plan", Phase: "制定研究计划", Label: "执行计划", Detail: strings.Join([]string(msg), " / ")})
		m.record("plan", "", strings.Join(plain, "\n"))
		m.livePlan = append([]string(nil), msg...)
		planLines := []string{stBullet.Render("⏺ ") + stAccent.Render("研究计划")}
		for _, s := range msg {
			planLines = append(planLines, stConn.Render("  ⎿ ")+stInk.Render(s))
		}
		m.appendBlock(BlockResearchPlan, strings.Join(planLines, "\n"))
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
		callLine := stBullet.Render("⏺ ") + stTool.Render(toolLabel(msg.name))
		if a := m.argsStr(msg.args); a != "" {
			callLine += stFaint.Render("  " + clip(a, 56))
		}
		m.appendBlock(BlockToolCall, callLine)
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
		// T05-06 接线：证据类工具走 typed Evidence 渲染层；其余保持旧路径。
		kind := BlockToolResult
		if isEvidenceTool(msg.name) {
			kind = BlockEvidence
		}
		m.appendBlock(kind, renderEvidenceToolResult(msg.name, msg.result, m.vp.Width, elapsed))
		return m, listen(m.sub)

	case reflectMsg:
		m.answer = ""
		m.record("reflect", "", string(msg))
		m.liveReflect = string(msg)
		m.addTimeline(timelineEvent{Kind: "reflect", Phase: "自检修正", Label: "自检修正", Detail: string(msg)})
		m.appendBlock(BlockResearchTrace, stBullet.Render("⏺ ")+stWarn.Render("自检修正")+"\n"+stConn.Render("  ⎿ ")+stFaint.Render(string(msg)))
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
		m.appendBlock(BlockRecovery, stError.Render("⏺ ✗ ")+renderRecoveryPanel(string(msg)))
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
			if card := renderStructuredAnswerCardCompressed(m.lastMeta.StructuredAnswer, m.vp.Width); card != "" {
				m.appendBlock(BlockContract, card)
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

	m.ti, cmd = m.ti.Update(msg)
	return m, cmd
}
