package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func runClearCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) < 1 {
		m.openSubmenu("clear")
		return m, nil
	}
	if args[0] != "yes" {
		m.appendBlock(BlockSystem, stFaint.Render("  已取消清空。"))
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
	m.appendBlock(BlockSystem, renderSlashHelpBlock())
	return m, nil
}

func runToolsCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) >= 1 {
		if tool, ok := toolInfoByName(args[0]); ok {
			m.appendBlock(BlockSystem, panelRow("tools", toolPlainLabel(tool.name), "detail", []string{tool.desc, "适用场景: " + tool.when, "工具名: " + tool.name}))
			return m, nil
		}
		m.appendBlock(BlockSystem, stWarn.Render("  未找到工具 "+args[0]+"。输入 /tools 查看工具列表。"))
		return m, nil
	}
	m.openSubmenu("tools")
	return m, nil
}

func runThemeCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) < 1 {
		m.appendBlock(BlockSystem, renderThemeBlock())
		return m, nil
	}
	nextTheme := args[0]
	if !applyTheme(nextTheme) {
		m.appendBlock(BlockSystem, stWarn.Render("  未知主题 "+nextTheme+"。输入 /theme 查看可选主题。"))
		return m, nil
	}
	m.syncThemeStyles()
	m.invalidateRenderCache()
	m.appendBlock(BlockSystem, stAccent.Render("  已切换主题: "+currentTheme)+stFaint.Render(" · "+themes[currentTheme].Title))
	return m, nil
}

func runTimelineCommand(m model, args []string) (model, tea.Cmd) {
	m.appendTimelineBlock(m.timeline)
	return m, nil
}

func runDoctorCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) >= 1 {
		name := strings.Join(args, " ")
		for _, check := range collectDoctorChecks() {
			if strings.EqualFold(check.Name, name) {
				m.appendBlock(BlockSystem, panelRow("doctor", check.Name, check.Status, []string{check.Detail}))
				return m, nil
			}
		}
		m.appendBlock(BlockSystem, stWarn.Render("  未找到检查项 "+name+"。输入 /doctor 查看状态。"))
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
		m.appendBlock(BlockSystem, stWarn.Render("  读取会话失败: "+err.Error()))
		return m, nil
	}
	m.recentSessions = sessions
	m.appendBlock(BlockSystem, renderSessionsList(sessions)+"\n"+stFaint.Render("  输入 /resume N 恢复对应会话。"))
	m.openSubmenu("resume")
	return m, nil
}

func runResumeCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) < 1 {
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err != nil {
			m.appendBlock(BlockSystem, stWarn.Render("  读取会话失败: "+err.Error()))
			return m, nil
		}
		m.recentSessions = sessions
		m.appendBlock(BlockSystem, renderSessionsList(sessions)+"\n"+stFaint.Render("  输入 /resume N 恢复对应会话。"))
		return m, nil
	}
	if len(m.recentSessions) == 0 {
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err != nil {
			m.appendBlock(BlockSystem, stWarn.Render("  读取会话失败: "+err.Error()))
			return m, nil
		}
		m.recentSessions = sessions
	}
	var idx int
	if _, err := fmt.Sscanf(args[0], "%d", &idx); err != nil || idx < 1 || idx > len(m.recentSessions) {
		m.appendBlock(BlockSystem, stWarn.Render("  未找到该会话编号。输入 /sessions 查看可恢复的会话。"))
		return m, nil
	}
	session, err := loadSessionMarkdown(m.recentSessions[idx-1].Path)
	if err != nil {
		m.appendBlock(BlockSystem, stWarn.Render("  恢复会话失败: "+err.Error()))
		return m, nil
	}
	// 语义化：恢复块存纯文本（会话 markdown 原文），渲染层透传，不把 ANSI
	// 塞回 scrollback（提示词核心目标 1：对话历史不保存渲染字符串）。
	m.blocks = []string{
		"已恢复会话 " + filepath.Base(session.Path),
		strings.TrimSpace(session.Content),
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
		m.appendBlock(BlockSystem, stWarn.Render("  暂无可重试的问题。先提一个问题, 或从会话记录中复制问题。"))
		return m, nil
	}
	cmd := m.startQuestion(m.lastQuestion, true)
	return m, cmd
}

func runExportCommand(m model, args []string) (model, tea.Cmd) {
	if len(m.transcript) == 0 {
		m.appendBlock(BlockSystem, stWarn.Render("  暂无可导出的会话。先提一个问题, 再使用 /export。"))
		return m, nil
	}
	path, err := writeSessionMarkdown(sessionDir(), m.transcript, time.Now())
	if err != nil {
		m.appendBlock(BlockSystem, stWarn.Render("  导出失败: "+err.Error()))
		return m, nil
	}
	m.lastExport = path
	m.appendBlock(BlockSystem, stFaint.Render("  已导出 Markdown: "+path))
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
		m.appendBlock(BlockSystem, stWarn.Render("  用法: /verify <需要核查的论断>"))
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
		m.appendBlock(BlockSystem, stWarn.Render("  用法: /review <研究主题>"))
		return m, nil
	}
	fallback := "请围绕这个主题做一份简洁的科研文献综述,包含研究现状、代表方向、趋势判断和可追溯证据: " + topic
	q := renderSkillPrompt("literature-review", topic, fallback)
	cmd := m.startQuestion(q, false)
	return m, cmd
}

func trendFallbackPrompt(topic string) string {
	return "请围绕这个主题做历史趋势描述,说明热度变化、代表证据、描述边界与不确定性,不得外推未来结论: " + topic
}

func runTrendCommand(m model, args []string) (model, tea.Cmd) {
	topic := strings.TrimSpace(strings.Join(args, " "))
	if topic == "" {
		m.appendBlock(BlockSystem, stWarn.Render("  用法: /trend <研究主题>"))
		return m, nil
	}
	fallback := trendFallbackPrompt(topic)
	q := renderSkillPrompt("trend-analysis", topic, fallback)
	cmd := m.startQuestion(q, false)
	return m, cmd
}

func runRecommendCommand(m model, args []string) (model, tea.Cmd) {
	request := strings.TrimSpace(strings.Join(args, " "))
	if request == "" {
		m.appendBlock(BlockSystem, stWarn.Render("  用法: /recommend <研究主题或真实 paper_id>"))
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
		m.appendBlock(BlockSystem, stWarn.Render("  未知命令 "+v))
		return m, nil
	}
	next, cmd := command.run(m, stripPlaceholder(fields[1:]))
	return next, cmd
}

func (m model) View() string {
	if !m.ready {
		return "启动中…"
	}
	// T05-07 修订（项目负责人要求）：全局 Accent 外边框包裹整个画面。
	// 外框占左右 2 边框 + 2 padding = 4 列，内部组件使用 innerW。
	innerW := m.vp.Width - 4
	if innerW < 40 {
		innerW = m.vp.Width
	}
	content := m.vp.View()
	// T05-12：搜索/选择模式的行 marker（▍/❯），在 canvas 黑底前插入。
	if m.searchMode {
		content = m.markSearchMatches(content)
	}
	if m.selectMode {
		content = m.markSelectedBlock(content)
	}
	parts := []string{content}

	if m.submenu != "" {
		parts = append(parts, m.renderSubmenuPalette(innerW))
	} else if strings.HasPrefix(m.ti.Value(), "/") {
		if menu := m.renderCommandPalette(innerW); menu != "" {
			parts = append(parts, menu)
		}
	}

	if m.searchMode {
		// 搜索模式：底部输入框切换为搜索框。
		parts = append(parts, m.renderSearchBox(innerW))
	} else {
		parts = append(parts, m.renderComposer(innerW))
	}
	content = strings.Join(parts, "\n")
	// black canvas（计划 5.1 节，Grok 式 cell 级背景的字符串模型等价实现）：
	// 组件渲染行内部含 \x1b[0m / \x1b[49m 重置序列，会把行首黑底 reset 掉，
	// 使行尾填充空格落在终端默认背景（IDE 灰）——对每个重置立即恢复黑底。
	// 注意：不经过 lipgloss 的包裹 Render（其 reflow 对含 ANSI 的行会产生
	// 拆行）；行宽由各层组件精确保证（vp 116 列、外框 120 列）。
	if lipgloss.ColorProfile() != termenv.Ascii {
		content = paintCanvasLines(content, activeTheme().Canvas)
	}
	// 全局外边框：Accent 色圆角框。手动拼接（不经过 lipgloss Border Render——
	// 它对含 ANSI 的多行内容做 reflow 时会把转义序列计入宽度，导致行被拆断）。
	framed := wrapWithFrame(content, m.vp.Width)
	// 边框行同样铺黑底（行首黑底 + reset 修复）。
	// T05-11 Terminal matrix：TERM=dumb / 无颜色能力（Ascii profile）时
	// fail gracefully——不输出任何控制字符垃圾，退回纯文本布局。
	if lipgloss.ColorProfile() == termenv.Ascii {
		return framed
	}
	return paintCanvasLines(framed, activeTheme().Canvas)
}

// canvasRGBSeq 把 lipgloss 颜色字符串 "#RRGGBB" 转成 SGR RGB 参数 "r;g;b"。
func canvasRGBSeq(c lipgloss.Color) string {
	s := strings.TrimPrefix(string(c), "#")
	if len(s) != 6 {
		return "0;0;0"
	}
	r, errR := strconv.ParseUint(s[0:2], 16, 8)
	g, errG := strconv.ParseUint(s[2:4], 16, 8)
	b, errB := strconv.ParseUint(s[4:6], 16, 8)
	if errR != nil || errG != nil || errB != nil {
		return "0;0;0"
	}
	return fmt.Sprintf("%d;%d;%d", r, g, b)
}

// paintCanvasLines 给每行行首添加画布背景 SGR，并把行内 SGR 重置
// （\x1b[0m / \x1b[49m）替换为「重置 + 恢复画布背景」。不经过 lipgloss Render，
// 因此不会触发任何 reflow/wrap。行宽由调用方保证。
func paintCanvasLines(content string, canvas lipgloss.Color) string {
	bgSeq := "\x1b[48;2;" + canvasRGBSeq(canvas) + "m"
	lines := strings.Split(content, "\n")
	var b strings.Builder
	for i, l := range lines {
		if i > 0 {
			b.WriteString("\n")
		}
		l = strings.ReplaceAll(l, "\x1b[0m", "\x1b[0m"+bgSeq)
		l = strings.ReplaceAll(l, "\x1b[49m", "\x1b[49m"+bgSeq)
		b.WriteString(bgSeq + l)
	}
	return b.String()
}

// wrapWithFrame 手动绘制全局外边框：content 每行宽 = width-4（含左右各 1 列
// 内边距），边框行总宽恰为 width。边框色 = Accent。
func wrapWithFrame(content string, width int) string {
	// width = 内容区宽（终端宽 - 4：左右边框 2 + 内边距 2）；外框总宽 = width + 4。
	stFrame := lipgloss.NewStyle().Foreground(cAccent)
	top := stFrame.Render("╭" + strings.Repeat("─", width+2) + "╮")
	bottom := stFrame.Render("╰" + strings.Repeat("─", width+2) + "╯")
	lines := strings.Split(content, "\n")
	var b strings.Builder
	b.WriteString(top)
	for _, l := range lines {
		b.WriteString("\n")
		// T05 样式优化：行尾补齐空格到内容区宽 width（ANSI 安全：pad 只
		// 加在行尾纯文本区域），保证每行右框 │ 对齐同一列——evidence 卡
		// 等内部行宽不足时外框不再出现豁口；顶/底框与行等宽（width+4）。
		if w := lipgloss.Width(l); w < width {
			l += strings.Repeat(" ", width-w)
		}
		b.WriteString(stFrame.Render("│") + " " + l + " " + stFrame.Render("│"))
	}
	b.WriteString("\n" + bottom)
	return b.String()
}

// renderStatusLine T05-07：一条低视觉权重 status + shortcut strip。
// 左侧：模式/spinner 状态（真实不伪造）；右侧：快捷键提示。
