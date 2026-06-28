package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func runClearCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) < 1 {
		m.openSubmenu("clear")
		return m, nil
	}
	if args[0] != "yes" {
		m.appendBlock(stFaint.Render("  已取消清空。"))
		return m, nil
	}
	m.blocks = nil
	m.blockItems = nil
	m.blocksVersion++
	m.history = nil
	m.transcript = nil
	m.timeline = nil
	m.lastExport = ""
	m.lastQuestion = ""
	m.refresh()
	return m, nil
}

func runHelpCommand(m model, args []string) (model, tea.Cmd) {
	m.appendBlock(renderSlashHelpBlock())
	return m, nil
}

func runToolsCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) >= 1 {
		if tool, ok := toolInfoByName(args[0]); ok {
			m.appendBlock(panelRow("tools", toolPlainLabel(tool.name), "detail", []string{tool.desc, "适用场景: " + tool.when, "工具名: " + tool.name}))
			return m, nil
		}
		m.appendBlock(stWarn.Render("  未找到工具 " + args[0] + "。输入 /tools 查看工具列表。"))
		return m, nil
	}
	m.openSubmenu("tools")
	return m, nil
}

func runThemeCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) < 1 {
		m.appendBlock(renderThemeBlock())
		return m, nil
	}
	nextTheme := args[0]
	if !applyTheme(nextTheme) {
		m.appendBlock(stWarn.Render("  未知主题 " + nextTheme + "。输入 /theme 查看可选主题。"))
		return m, nil
	}
	m.syncThemeStyles()
	m.appendBlock(stAccent.Render("  已切换主题: "+currentTheme) + stFaint.Render(" · "+themes[currentTheme].Title))
	return m, nil
}

func runTimelineCommand(m model, args []string) (model, tea.Cmd) {
	m.appendBlock(renderTimelineBlock(m.timeline))
	return m, nil
}

func runDoctorCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) >= 1 {
		name := strings.Join(args, " ")
		for _, check := range collectDoctorChecks() {
			if strings.EqualFold(check.Name, name) {
				m.appendBlock(panelRow("doctor", check.Name, check.Status, []string{check.Detail}))
				return m, nil
			}
		}
		m.appendBlock(stWarn.Render("  未找到检查项 " + name + "。输入 /doctor 查看状态。"))
		return m, nil
	}
	m.openSubmenu("doctor")
	return m, nil
}

func runDemoCommand(m model, args []string) (model, tea.Cmd) {
	go playDemo(m.sub)
	return m, listen(m.sub)
}

func runSessionsCommand(m model, args []string) (model, tea.Cmd) {
	sessions, err := listSessionFiles(sessionDir(), 8)
	if err != nil {
		m.appendBlock(stWarn.Render("  读取会话失败: " + err.Error()))
		return m, nil
	}
	m.recentSessions = sessions
	m.appendBlock(renderSessionsList(sessions) + "\n" + stFaint.Render("  输入 /resume N 恢复对应会话。"))
	m.openSubmenu("resume")
	return m, nil
}

func runResumeCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) < 1 {
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err != nil {
			m.appendBlock(stWarn.Render("  读取会话失败: " + err.Error()))
			return m, nil
		}
		m.recentSessions = sessions
		m.appendBlock(renderSessionsList(sessions) + "\n" + stFaint.Render("  输入 /resume N 恢复对应会话。"))
		return m, nil
	}
	if len(m.recentSessions) == 0 {
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err != nil {
			m.appendBlock(stWarn.Render("  读取会话失败: " + err.Error()))
			return m, nil
		}
		m.recentSessions = sessions
	}
	var idx int
	if _, err := fmt.Sscanf(args[0], "%d", &idx); err != nil || idx < 1 || idx > len(m.recentSessions) {
		m.appendBlock(stWarn.Render("  未找到该会话编号。输入 /sessions 查看可恢复的会话。"))
		return m, nil
	}
	session, err := loadSessionMarkdown(m.recentSessions[idx-1].Path)
	if err != nil {
		m.appendBlock(stWarn.Render("  恢复会话失败: " + err.Error()))
		return m, nil
	}
	m.blocks = []string{
		stBullet.Render("⏺ ") + stAccent.Render("已恢复会话 ") + stFaint.Render(filepath.Base(session.Path)),
		stFaint.Render(strings.TrimSpace(session.Content)),
	}
	m.syncBlockItems()
	m.transcript = []transcriptEvent{{Kind: "session", Content: session.Content}}
	m.lastQuestion = session.LastQuestion
	m.lastExport = session.Path
	m.refresh()
	return m, nil
}

func runRetryCommand(m model, args []string) (model, tea.Cmd) {
	if m.lastQuestion == "" {
		m.appendBlock(stWarn.Render("  暂无可重试的问题。先提一个问题, 或从会话记录中复制问题。"))
		return m, nil
	}
	cmd := m.startQuestion(m.lastQuestion, true)
	return m, cmd
}

func runExportCommand(m model, args []string) (model, tea.Cmd) {
	if len(m.transcript) == 0 {
		m.appendBlock(stWarn.Render("  暂无可导出的会话。先提一个问题, 再使用 /export。"))
		return m, nil
	}
	path, err := writeSessionMarkdown(sessionDir(), m.transcript, time.Now())
	if err != nil {
		m.appendBlock(stWarn.Render("  导出失败: " + err.Error()))
		return m, nil
	}
	m.lastExport = path
	m.appendBlock(stFaint.Render("  已导出 Markdown: " + path))
	return m, nil
}

func skillTemplatePaths(name string) []string {
	filename := name + ".md"
	return []string{
		filepath.Join(".sciscope", "skills", filename),
		filepath.Join("..", ".sciscope", "skills", filename),
	}
}

func loadSkillTemplate(name string) (string, error) {
	var lastErr error
	for _, path := range skillTemplatePaths(name) {
		body, err := os.ReadFile(path)
		if err == nil {
			return string(body), nil
		}
		lastErr = err
	}
	return "", fmt.Errorf("skill %s not found: %w", name, lastErr)
}

func renderSkillPrompt(name, input, fallback string) string {
	input = strings.TrimSpace(input)
	template, err := loadSkillTemplate(name)
	if err != nil {
		return fallback
	}
	return strings.ReplaceAll(template, "{{input}}", input)
}

func runVerifyCommand(m model, args []string) (model, tea.Cmd) {
	claim := strings.TrimSpace(strings.Join(args, " "))
	if claim == "" {
		m.appendBlock(stWarn.Render("  用法: /verify <需要核查的论断>"))
		return m, nil
	}
	fallback := "请核查这个论断是否有科研文献支持,给出支持等级、关键证据和谨慎表述: " + claim
	q := renderSkillPrompt("claim-check", claim, fallback)
	cmd := m.startQuestion(q, false)
	return m, cmd
}

func runReviewCommand(m model, args []string) (model, tea.Cmd) {
	topic := strings.TrimSpace(strings.Join(args, " "))
	if topic == "" {
		m.appendBlock(stWarn.Render("  用法: /review <研究主题>"))
		return m, nil
	}
	fallback := "请围绕这个主题做一份简洁的科研文献综述,包含研究现状、代表方向、趋势判断和可追溯证据: " + topic
	q := renderSkillPrompt("literature-review", topic, fallback)
	cmd := m.startQuestion(q, false)
	return m, cmd
}

func runTrendCommand(m model, args []string) (model, tea.Cmd) {
	topic := strings.TrimSpace(strings.Join(args, " "))
	if topic == "" {
		m.appendBlock(stWarn.Render("  用法: /trend <研究主题>"))
		return m, nil
	}
	fallback := "请围绕这个主题做趋势分析,说明热度变化、代表证据、趋势边界和未来判断: " + topic
	q := renderSkillPrompt("trend-analysis", topic, fallback)
	cmd := m.startQuestion(q, false)
	return m, cmd
}

func runRecommendCommand(m model, args []string) (model, tea.Cmd) {
	request := strings.TrimSpace(strings.Join(args, " "))
	if request == "" {
		m.appendBlock(stWarn.Render("  用法: /recommend <研究主题或真实 paper_id>"))
		return m, nil
	}
	fallback := "请基于这个研究主题或种子论文推荐后续阅读论文,并先确认真实 paper_id: " + request
	q := renderSkillPrompt("paper-recommendation", request, fallback)
	cmd := m.startQuestion(q, false)
	return m, cmd
}

// commandNeedsArg reports whether a palette command takes a typed argument
// (its usage hint carries a "<...>" placeholder, e.g. "recommend <topic|paper_id>").
func commandNeedsArg(c slashCmd) bool {
	return strings.Contains(c.key, "<")
}

// stageCommand fills the composer from a palette selection. A command that takes
// an argument is staged as "/cmd <>" with the cursor inside the placeholder, so
// pressing Enter on it readies the argument instead of running with an empty one;
// an argument-less command just completes to "/cmd".
func stageCommand(m model, c slashCmd) model {
	if commandNeedsArg(c) {
		tmpl := c.cmd + " <>"
		m.ti.SetValue(tmpl)
		m.ti.SetCursor(len(tmpl) - 1) // between the < and >
	} else {
		m.ti.SetValue(c.cmd)
	}
	return m
}

// stripPlaceholder removes a surrounding "<...>" placeholder pair the palette may
// have inserted, so "/recommend <graph nn>" and "/recommend graph nn" behave the
// same and an untouched "/recommend <>" submits as an empty argument.
func stripPlaceholder(args []string) []string {
	joined := strings.TrimSpace(strings.Join(args, " "))
	if strings.HasPrefix(joined, "<") && strings.HasSuffix(joined, ">") {
		joined = strings.TrimSpace(joined[1 : len(joined)-1])
	}
	if joined == "" {
		return nil
	}
	return strings.Fields(joined)
}

func (m model) runSlash(v string) (tea.Model, tea.Cmd) {
	fields := strings.Fields(v)
	if len(fields) == 0 {
		return m, nil
	}
	command, ok := slashRegistry[fields[0]]
	if !ok || command.run == nil {
		m.appendBlock(stWarn.Render("  未知命令 " + v))
		return m, nil
	}
	next, cmd := command.run(m, stripPlaceholder(fields[1:]))
	return next, cmd
}

func (m model) View() string {
	if !m.ready {
		return "启动中…"
	}
	banner := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).BorderForeground(cAccent).Padding(0, 1)
	header := banner.Render(stAccent.Render("◆ SciScope") + "  " + stInk.Render("科研智能体终端") + "  " + stFaint.Render("证据 · 时间线 · 重试 · 导出"))
	parts := []string{header, m.vp.View()}

	// thinking spinner (Claude Code-style verb + esc hint) while a turn runs
	if m.answering {
		parts = append(parts, renderWorkflowStatus(m.lastMeta, m.nodeSeen, m.lastStreamKind, time.Since(m.start), m.vp.Width))
		// plan/reflect now stream inline in the transcript, so no separate shelf.
		elapsed := int(time.Since(m.start).Seconds())
		mood := kaomojiForState(m.lastStreamKind, m.lastMeta, true)
		parts = append(parts, m.spin.View()+" "+stAccent.Render(m.verb+"…")+" "+stFaint.Render(mood)+stFaint.Render(fmt.Sprintf("  (%ds · esc 中断)", elapsed)))
	} else if m.submenu != "" {
		parts = append(parts, m.renderSubmenuPalette(m.vp.Width))
	} else if strings.HasPrefix(m.ti.Value(), "/") {
		if menu := m.renderCommandPalette(m.vp.Width); menu != "" {
			parts = append(parts, menu)
		}
	}

	parts = append(parts, m.renderComposer(m.vp.Width))
	return strings.Join(parts, "\n")
}
