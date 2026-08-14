// view_conversation.go — T05-10 文件职责收敛：对话渲染（单一视觉职责）。
//
// 从 main.go 搬移（行为零变化，纯文件拆分）：
//   - 对话块组装与折叠：renderBlocksContent / collapseTraceBlock / renderTranscriptContent
//   - 消息渲染：renderConversationBlock / renderUserMessage / renderAnswerMessage
//   - 答案语义高亮：styleAnswerBody/Line、semanticHighlightSpans 等
//   - ANSI 工具：stripANSI
package main

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync/atomic"

	"github.com/charmbracelet/lipgloss"
)

func (m *model) renderBlocksContent(width int) string {
	m.syncBlockItems()
	if len(m.blockItems) == 0 {
		return ""
	}
	parts := make([]string, 0, len(m.blockItems))
	inToolGroup := false // T05-04: 连续 research tools 语义 grouping
	// T05-12：记录每块起始行号，供 block 选择模式（ctrl+g）定位。
	m.blockStartLines = make([]int, 0, len(m.blockItems))
	lineNo := 0
	for i := range m.blockItems {
		m.blockStartLines = append(m.blockStartLines, lineNo)
		block := &m.blockItems[i]
		if block.Rendered == "" || block.RenderWidth != width {
			block.Rendered = renderConversationBlock(*block, width)
			block.RenderWidth = width
			block.RenderVersion++
		}
		out := block.Rendered
		// T05-05：finished 且未展开的轨迹块收敛为一行（Enter 展开）。
		if (block.Kind == BlockResearchPlan || block.Kind == BlockResearchTrace || block.Kind == BlockEvidence) &&
			block.Status == BlockFinished && !block.Expanded {
			out = m.collapseTraceBlock(block)
		}
		if block.Kind == BlockToolCall {
			if inToolGroup {
				// 组内成员：缩进 + ⎿ 替代 ⏺，降低重复视觉噪声。
				out = indentToolGroupLine(out)
			} else {
				inToolGroup = true
			}
		} else if block.Kind != BlockToolResult {
			inToolGroup = false
		}
		parts = append(parts, out)
		lineNo += strings.Count(out, "\n") + 1
	}
	return strings.Join(parts, "\n")
}

// indentToolGroupLine 把连续工具组内的调用行从状态图标降为缩进 ⎿。
// 状态图标包括：⏺（running）、✓（succeeded）、✗（failed）。图标为 1-3 字节
// rune + 空格，故空格字节索引在 1..4 内。
func indentToolGroupLine(line string) string {
	if i := strings.Index(line, " "); i >= 0 && i <= 4 {
		line = "⎿ " + line[i+1:]
	}
	return "  " + line
}

// collapseTraceBlock T05-05：折叠轨迹块为一行——首行标题 + 步骤数/工具数 + 展开提示。
func (m *model) collapseTraceBlock(block *ScrollbackBlock) string {
	lines := strings.Split(block.Rendered, "\n")
	first := lines[0]
	// T05 样式优化（项目负责人反馈）：evidence 卡折叠为一行摘要——
	// 不再把整卡细节堆在结论上方挤压回答内容；Enter 展开查看。
	if block.Kind == BlockEvidence {
		summary := evidenceCollapseSummary(lines)
		return stBullet.Render("⏺ ") + stAccent.Render("证据卡") +
			stFaint.Render(" · "+summary+" · Enter 展开")
	}
	steps := strings.Count(block.Raw, "\n")
	parts := []string{first}
	if steps > 0 {
		parts = append(parts, fmt.Sprintf("%d 步", steps))
	}
	if len(m.used) > 0 {
		parts = append(parts, fmt.Sprintf("%d 工具", len(m.used)))
	}
	parts = append(parts, "Enter 展开")
	return first + stFaint.Render(" · "+strings.Join(parts[1:], " · "))
}

// evidenceCollapseSummary 从证据卡渲染行提取折叠摘要（stance/条数等）。
func evidenceCollapseSummary(lines []string) string {
	joined := strings.Join(lines, " ")
	plain := stripANSI(joined)
	// 立场词优先（强支持/部分支持/证据不足）
	for _, s := range []string{"强支持", "部分支持", "证据不足", "不支持"} {
		if strings.Contains(plain, s) {
			return s
		}
	}
	// 条数（N 条证据）
	if n := strings.Count(plain, "["); n > 0 {
		return fmt.Sprintf("%d 条", n)
	}
	return "证据详情"
}

// maybeAnchorToPrompt T05-04 发送后锚定（feature gate：SCISCOPE_TUI_SEND_ANCHOR=1）：
// 本轮第一个响应事件到达时，把用户问题行锚到 viewport 顶部，让本轮 response
// 拥有干净页面；用户手工滚动后恢复既有 follow 纪律。
func (m *model) maybeAnchorToPrompt() {
	if !m.anchorNextTurn {
		return
	}
	m.anchorNextTurn = false
	lines := strings.Split(m.viewportContent, "\n")
	lastPrompt := -1
	for i, ln := range lines {
		plain := stripANSI(ln)
		if strings.Contains(plain, "用户问题") || strings.Contains(plain, "重试问题") {
			lastPrompt = i
		}
	}
	if lastPrompt < 0 {
		return
	}
	m.vp.GotoTop()
	m.vp.SetYOffset(lastPrompt)
}

func (m *model) renderTranscriptContent(width int) string {
	m.syncBlockItems()
	if m.transcriptCacheWidth == width && m.transcriptCacheBlockVersion == m.blocksVersion {
		return m.transcriptCache
	}
	m.transcriptCache = m.renderBlocksContent(width)
	m.transcriptCacheWidth = width
	m.transcriptCacheBlockVersion = m.blocksVersion
	m.transcriptCacheVersion++
	return m.transcriptCache
}

func renderConversationBlock(block ScrollbackBlock, width int) string {
	switch block.Kind {
	case BlockUser:
		return renderUserMessage(block.Raw, block.Retry)
	case BlockAnswer:
		if block.Status == BlockRunning {
			// T05-04: running 块 animated accent —— 流式正文 + 光标。
			// T05 样式优化：流式期间同样走轻量 markdown 结构渲染，
			// 否则 LLM 的 # / * 语法符号在流式过程中裸露（final 才转正）。
			// 已换行成型的行做完整结构渲染；最后一行（可能未写完）只做
			// 行内样式 + 光标。
			raw := strings.TrimRight(block.Raw, "\n")
			lines := strings.Split(raw, "\n")
			var body string
			if len(lines) > 1 {
				body = renderMarkdownPlain(strings.Join(lines[:len(lines)-1], "\n"), width) + "\n" +
					stInk.Render(renderMarkdownInline(lines[len(lines)-1]))
			} else {
				body = stInk.Render(renderMarkdownInline(raw))
			}
			return stBullet.Render("⏺ ") + stAccent.Render("研究结论") + "\n" +
				body + stAccent.Render("▌")
		}
		return renderAnswerMessage(block.Raw, block.Tools, width)
	case BlockToolCall:
		// 三态生命周期渲染（提示词：Running → Success → Failed），无框摘要式。
		return renderToolCallBlock(&block, width)
	case BlockResearchPlan:
		// 语义化：PlanSteps 结构化，无框紧凑展示（提示词：Plan 不抢空间）。
		return renderPlanBlockSemantic(&block)
	case BlockResearchTrace:
		if block.Meta == "timeline" {
			// /timeline 审计时间线：Events 结构化，渲染层重建（领域对象允许边框）。
			return renderTimelineBlock(block.Events)
		}
		return renderReflectBlockSemantic(&block)
	case BlockRecovery:
		// 语义化：Raw=原始错误文本，渲染层重建 recovery 面板。
		return renderRecoveryPanel(block.Raw)
	case BlockContract:
		return renderContractBlock(&block)
	case BlockEvidence:
		// 语义化：Raw=工具结果 JSON 原文，渲染层解析证据卡（不预渲染 ANSI）。
		return renderEvidenceBlock(&block, width)
	case BlockToolResult:
		// 旧数据兼容透传；新数据流不再产生 BlockToolResult（摘要并入 tool 行）。
		return block.Raw
	default:
		return block.Raw
	}
}

// renderToolCallBlock 渲染 Tool Call 三态（无框、摘要式，提示词「Tool 不要像日志」）：
//
//	running:   ⏺ 搜索论文数据库…
//	succeeded: ✓ 搜索论文数据库 · 找到 15 篇论文 · 完成 2.4s
//	failed:    ✗ 校验拦截 · 校验拦截原因 · 0.3s
//
// Wide 档位（>110 列）额外显示参数 metadata。
// 注意用 toolPlainLabel（不带工具图标）：状态图标（⏺/✓/✗）是本渲染层唯一
// 的图标源，避免与 toolLabel 的工具图标叠加成「✓ ✓ 论断核查」。
func renderToolCallBlock(b *ScrollbackBlock, width int) string {
	label := toolPlainLabel(b.ToolName)
	if label == "" {
		label = b.Raw
	}
	meta := ""
	if layoutTierFor(width) == tierWide && b.ToolArgs != "" {
		meta = "  " + clip(b.ToolArgs, 40)
	}
	switch b.Status {
	case BlockRunning:
		return stBullet.Render("⏺ ") + stAccent.Render(label+"…") + stFaint.Render(meta)
	case BlockSucceeded:
		line := stBullet.Render("✓ ") + stInk.Render(label)
		if b.ToolSummary != "" {
			line += stMuted.Render(" · " + b.ToolSummary)
		}
		if d := durationText(b.ToolDuration); d != "" {
			line += stFaint.Render(" · " + d)
		}
		return line + stFaint.Render(meta)
	case BlockFailed:
		line := stBullet.Render("✗ ") + stError.Render(label)
		if b.ToolSummary != "" {
			line += stError.Render(" · " + b.ToolSummary)
		}
		return line + stFaint.Render(meta)
	default:
		if b.Raw != "" {
			return b.Raw
		}
		return stInk.Render(label)
	}
}

// renderPlanBlockSemantic 渲染研究计划块（无框、缩进、紧凑）。
func renderPlanBlockSemantic(b *ScrollbackBlock) string {
	lines := []string{stBullet.Render("⏺ ") + stAccent.Render("研究计划")}
	steps := b.PlanSteps
	if len(steps) == 0 && b.Raw != "" {
		for _, ln := range strings.Split(b.Raw, "\n") {
			steps = append(steps, strings.TrimSpace(strings.TrimPrefix(ln, "- ")))
		}
	}
	for _, s := range steps {
		lines = append(lines, stConn.Render("  ⎿ ")+stInk.Render(s))
	}
	return strings.Join(lines, "\n")
}

// renderReflectBlockSemantic 渲染自检修正块（无框）。
func renderReflectBlockSemantic(b *ScrollbackBlock) string {
	return stBullet.Render("⏺ ") + stWarn.Render("自检修正") + "\n" +
		stConn.Render("  ⎿ ") + stFaint.Render(b.Raw)
}

// renderContractBlock 渲染 answer-contract 压缩行（首段 Accent，其余 Muted）。
func renderContractBlock(b *ScrollbackBlock) string {
	if b.Raw == "" {
		return ""
	}
	parts := strings.Split(b.Raw, " · ")
	out := make([]string, 0, len(parts))
	for i, p := range parts {
		if i == 0 {
			out = append(out, stAccent.Render(p))
		} else {
			out = append(out, stMuted.Render(p))
		}
	}
	return "  " + strings.Join(out, " · ")
}

// renderEvidenceBlock 渲染证据领域对象卡（Raw=结果 JSON，渲染层解析）。
func renderEvidenceBlock(b *ScrollbackBlock, width int) string {
	return renderEvidenceToolResult(b.ToolName, b.Raw, width, b.ToolDuration)
}

func renderUserMessage(text string, retry bool) string {
	text = strings.TrimSpace(text)
	prefix := "❯"
	title := "用户问题"
	if retry {
		prefix = "↻"
		title = "重试问题"
	}
	// T05 样式优化（项目负责人反馈）：用户输入在长对话中易被埋没——
	// 用左侧 Accent 亮条 + 缩进做视觉锚点（grok 用户消息语义），
	// 上下文各空一行形成独立区块。不用背景色：行内 reset 会与
	// paintCanvasLines 的黑底恢复冲突。
	inner := stUser.Render(prefix+" "+title) + "\n" +
		stInk.Render("  "+text)
	return lipgloss.NewStyle().
		Border(lipgloss.Border{Left: "▎"}).
		BorderForeground(activeTheme().Accent).
		Padding(0, 1).
		Render(inner)
}

func glamourStyleName() string {
	switch currentTheme {
	case "paper", "light":
		return "light"
	default:
		return "dark"
	}
}

// glamourRenderCount 统计 Glamour 渲染次数（T05-11 cache hit 证据与性能预算）。
var glamourRenderCount int64

func renderAnswerMessage(answer string, tools []string, width int) string {
	atomic.AddInt64(&glamourRenderCount, 1)
	// 宽度预算：viewport 内容宽 width；markdown 重排后的行若显示宽恰好
	// 等于视口宽，viewport 会在含 ANSI 的行上 wrap，把序列从中间切断
	// （ESC 留上一行、参数落到下一行 → 字面 [0m[38;5;252m 乱码）。
	// 因此再留 1 列余量（-5），使行宽恒 < 视口宽，wrap 永不触发。
	w := width - 5
	if w < 20 {
		w = 20
	}
	// 轻量 markdown 结构渲染（T05 样式优化，项目负责人反馈）：
	// 不再依赖 Glamour——其输出剥色后只剩裸露的 # / - 符号，观感混乱。
	// 自有渲染器把标题/列表/粗体等结构转成 theme token 样式，
	// 不残留任何 markdown 语法符号；颜色全 RGB（与欢迎页/面板同源）。
	body := strings.Trim(renderMarkdownPlain(answer, w), "\n")
	body = styleAnswerBody(body)
	header := stBullet.Render("⏺ ") + stAccent.Render("研究结论")
	out := header + "\n" + body
	if len(tools) > 0 {
		seen := map[string]bool{}
		labels := []string{}
		for _, n := range tools {
			if !seen[n] {
				seen[n] = true
				labels = append(labels, toolLabel(n))
			}
		}
		out += "\n" + stFaint.Render("  证据工具: "+strings.Join(labels, "  ")+" · /timeline 查看过程")
	}
	return out
}

// renderAnswer renders the finished answer as a chat message. Tool traces are
// kept in /timeline so the main conversation stays readable.
func (m model) renderAnswer() string {
	return renderAnswerMessage(m.answer, m.used, m.vp.Width)
}

func styleAnswerBody(body string) string {
	lines := strings.Split(body, "\n")
	for i, line := range lines {
		lines[i] = styleAnswerLine(line)
	}
	return strings.Join(lines, "\n")
}

func styleAnswerLine(line string) string {
	raw := strings.TrimSpace(stripANSI(line))
	if raw == "" {
		return line
	}
	indent := leadingWhitespace(line)
	if label := answerSectionLabel(raw); label != "" {
		text := strings.TrimLeft(strings.TrimPrefix(raw, label), "：: #")
		if text == "" {
			return indent + stAccent.Render(label)
		}
		return indent + stAccent.Render(label) + stInk.Render("  ") + styleSemanticText(text)
	}
	if highlighted := styleSemanticText(raw); highlighted != raw {
		return indent + highlighted
	}
	return line
}

type highlightSpan struct {
	start    int
	end      int
	priority int
	style    lipgloss.Style
}

func styleSemanticText(text string) string {
	spans := semanticHighlightSpans(text)
	if len(spans) == 0 {
		return text
	}
	resolved := resolveHighlightSpans(spans)
	if len(resolved) == 0 {
		return text
	}
	var b strings.Builder
	cursor := 0
	for _, span := range resolved {
		if span.start > cursor {
			b.WriteString(text[cursor:span.start])
		}
		b.WriteString(span.style.Render(text[span.start:span.end]))
		cursor = span.end
	}
	if cursor < len(text) {
		b.WriteString(text[cursor:])
	}
	return b.String()
}

func semanticHighlightSpans(text string) []highlightSpan {
	spans := []highlightSpan{}
	addPatternSpans := func(pattern *regexp.Regexp, priority int, style lipgloss.Style) {
		for _, loc := range pattern.FindAllStringIndex(text, -1) {
			spans = append(spans, highlightSpan{start: loc[0], end: loc[1], priority: priority, style: style})
		}
	}
	addPatternSpans(commandPattern, 80, stAccent)
	addPatternSpans(toolNamePattern, 78, stTool)
	addPatternSpans(paperIDPattern, 72, stTool)
	addPatternSpans(verdictPattern, 70, stAccent)
	addPatternSpans(cautionPattern, 64, stWarn)
	addPatternSpans(metricPattern, 58, stAccent)
	addPatternSpans(yearPattern, 48, stFaint)
	return spans
}

func resolveHighlightSpans(spans []highlightSpan) []highlightSpan {
	sort.SliceStable(spans, func(i, j int) bool {
		if spans[i].start != spans[j].start {
			return spans[i].start < spans[j].start
		}
		if spans[i].priority != spans[j].priority {
			return spans[i].priority > spans[j].priority
		}
		return spans[i].end > spans[j].end
	})
	resolved := []highlightSpan{}
	for _, span := range spans {
		if span.start >= span.end {
			continue
		}
		overlap := false
		for _, used := range resolved {
			if span.start < used.end && span.end > used.start {
				overlap = true
				break
			}
		}
		if !overlap {
			resolved = append(resolved, span)
		}
	}
	sort.SliceStable(resolved, func(i, j int) bool {
		return resolved[i].start < resolved[j].start
	})
	return resolved
}

func answerSectionLabel(s string) string {
	s = strings.TrimLeft(s, "#-*0123456789. ")
	s = strings.TrimSpace(strings.TrimSuffix(strings.TrimSuffix(s, ":"), "："))
	switch {
	case strings.HasPrefix(s, "结论"), strings.HasPrefix(s, "研究结论"), strings.HasPrefix(s, "最终结论"):
		return "结论"
	case strings.HasPrefix(s, "证据"), strings.HasPrefix(s, "依据"), strings.HasPrefix(s, "出处"):
		return "证据"
	case strings.HasPrefix(s, "风险"), strings.HasPrefix(s, "限制"), strings.HasPrefix(s, "边界"), strings.HasPrefix(s, "注意"):
		return "边界"
	case strings.HasPrefix(s, "建议"), strings.HasPrefix(s, "下一步"), strings.HasPrefix(s, "行动"):
		return "建议"
	case strings.HasPrefix(s, "摘要"), strings.HasPrefix(s, "概括"):
		return "摘要"
	default:
		return ""
	}
}

func hasCautionToken(s string) bool {
	for _, token := range []string{"风险", "限制", "边界", "但", "然而", "取决于", "不应", "不能", "可能", "仍需", "谨慎"} {
		if strings.Contains(s, token) {
			return true
		}
	}
	return false
}

func hasMetricToken(s string) bool {
	if strings.ContainsAny(s, "%％") {
		return true
	}
	digits := 0
	for _, r := range s {
		if r >= '0' && r <= '9' {
			digits++
			if digits >= 2 {
				return true
			}
		}
	}
	return false
}

func leadingWhitespace(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r != ' ' && r != '\t' {
			break
		}
		b.WriteRune(r)
	}
	return b.String()
}

func stripANSI(s string) string {
	var b strings.Builder
	inEsc := false
	for i := 0; i < len(s); i++ {
		ch := s[i]
		if inEsc {
			if (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') {
				inEsc = false
			}
			continue
		}
		if ch == 0x1b {
			inEsc = true
			continue
		}
		b.WriteByte(ch)
	}
	return b.String()
}

// ---- 轻量 markdown 结构渲染（替换 Glamour，无语法符号残留）----

var (
	mdBoldRe = regexp.MustCompile(`\*\*([^*\n]+)\*\*`)
	mdEmRe   = regexp.MustCompile(`\*([^*\n]+)\*`)
	mdCodeRe = regexp.MustCompile("`([^`\n]+)`")
)

// renderMarkdownInline 行内样式：`code` 保留反引号（faint）→ **bold** 去
// 星号（Ink 加粗）→ *em* 去星号（Ink 斜体）。
// 嵌套安全：code 先替换为占位符，bold/em 在其外匹配，最后恢复占位符——
// 避免样式 ANSI 嵌套进后续正则匹配内容（嵌套样式曾在渲染层引发 ANSI
// 切碎乱码，见 doneMsg Raw 语义修复）。
func renderMarkdownInline(s string) string {
	var codes []string
	s = mdCodeRe.ReplaceAllStringFunc(s, func(m string) string {
		inner := mdCodeRe.FindStringSubmatch(m)[1]
		codes = append(codes, "`"+inner+"`")
		return "\x00code" + string(rune(len(codes)-1)) + "\x00"
	})
	s = mdBoldRe.ReplaceAllStringFunc(s, func(m string) string {
		inner := mdBoldRe.FindStringSubmatch(m)[1]
		return lipgloss.NewStyle().Bold(true).Foreground(cInk).Render(inner)
	})
	s = mdEmRe.ReplaceAllStringFunc(s, func(m string) string {
		inner := mdEmRe.FindStringSubmatch(m)[1]
		return lipgloss.NewStyle().Italic(true).Foreground(cInk).Render(inner)
	})
	for i, c := range codes {
		s = strings.ReplaceAll(s, "\x00code"+string(rune(i))+"\x00", stMuted.Render(c))
	}
	return s
}

// renderMarkdownPlain 把 markdown 文本渲染为结构化纯样式输出（无 # / - /
// ** 等语法符号残留）：
//
//	#/##/### 标题   → Accent 加粗文本（去 #，上下留白）
//	- /*/1. 列表项  → 「· 」前缀（Accent 点 + Ink 内容，保持缩进层级）
//	段落            → 原样 + 行内样式
//	空行            → 段落分隔
//
// 行宽控制：调用方负责整体宽度预算（renderAnswerMessage 的 width-5），
// 本函数不做 wordwrap——长行由内容自然换行，避免再引入切 ANSI 的 wrap 源。
func renderMarkdownPlain(answer string, width int) string {
	lines := strings.Split(answer, "\n")
	var b strings.Builder
	inCode := false // ``` 围栏代码块
	for _, raw := range lines {
		line := strings.TrimRight(raw, " ")
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			b.WriteString("\n")
			continue
		}
		indent := leadingWhitespace(line)
		// 围栏代码块：``` 开始/结束，内部原样 Muted（代码语义，不做样式）。
		if strings.HasPrefix(trimmed, "```") {
			inCode = !inCode
			b.WriteString(indent + stFaint.Render("┄┄┄") + "\n")
			continue
		}
		if inCode {
			b.WriteString(indent + stMuted.Render(trimmed) + "\n")
			continue
		}
		// 引用：> 前缀 → 「▎ 」+ Muted 斜体。
		if strings.HasPrefix(trimmed, "> ") || trimmed == ">" {
			text := strings.TrimSpace(strings.TrimPrefix(trimmed, ">"))
			b.WriteString(indent + stAccent.Render("▎ ") +
				lipgloss.NewStyle().Italic(true).Foreground(cMuted).Render(renderMarkdownInline(text)) + "\n")
			continue
		}
		// 表格行（| 分隔）：保留结构但 Muted 渲染表头与分隔行。
		if strings.HasPrefix(trimmed, "|") && strings.Contains(trimmed[1:], "|") {
			b.WriteString(indent + stMuted.Render(renderMarkdownInline(trimmed)) + "\n")
			continue
		}
		switch {
		case strings.HasPrefix(trimmed, "###"):
			text := strings.TrimSpace(strings.TrimPrefix(trimmed, "###"))
			if text != "" {
				b.WriteString("\n" + indent + stAccent.Render(text) + "\n")
			}
		case strings.HasPrefix(trimmed, "##"):
			text := strings.TrimSpace(strings.TrimPrefix(trimmed, "##"))
			if text != "" {
				b.WriteString("\n" + indent + stAccent.Render(text) + "\n")
			}
		case strings.HasPrefix(trimmed, "#"):
			text := strings.TrimSpace(strings.TrimPrefix(trimmed, "#"))
			if text != "" {
				b.WriteString("\n" + indent + stAccent.Render(text) + "\n")
			}
		case listMarker(trimmed) != "":
			marker := listMarker(trimmed)
			text := strings.TrimSpace(trimmed[len(marker):])
			b.WriteString(indent + stAccent.Render("· ") + renderMarkdownInline(text) + "\n")
		default:
			b.WriteString(indent + renderMarkdownInline(trimmed) + "\n")
		}
	}
	return strings.Trim(b.String(), "\n")
}

// listMarker 返回行首的列表标记（"- "、"* "、"1. " 等）或空串。
func listMarker(trimmed string) string {
	if len(trimmed) >= 2 && (trimmed[0] == '-' || trimmed[0] == '*' || trimmed[0] == '+') && trimmed[1] == ' ' {
		return trimmed[:2]
	}
	for i := 0; i < len(trimmed) && trimmed[i] >= '0' && trimmed[i] <= '9'; i++ {
		if i+1 < len(trimmed) && trimmed[i+1] == '.' && i+2 < len(trimmed) && trimmed[i+2] == ' ' {
			return trimmed[:i+3]
		}
	}
	return ""
}
