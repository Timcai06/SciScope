package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func asciiBrand(width int) string {
	if width < 86 {
		return stAccent.Render("SciScope")
	}
	lines := []string{
		"███████╗ ██████╗██╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗",
		"██╔════╝██╔════╝██║██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝",
		"███████╗██║     ██║███████╗██║     ██║   ██║██████╔╝█████╗  ",
		"╚════██║██║     ██║╚════██║██║     ██║   ██║██╔═══╝ ██╔══╝  ",
		"███████║╚██████╗██║███████║╚██████╗╚██████╔╝██║     ███████╗",
		"╚══════╝ ╚═════╝╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝     ╚══════╝",
	}
	return stAccent.Render(strings.Join(lines, "\n"))
}

func renderSplash(width int, sessions []sessionFile) string {
	_ = sessions
	if width < 60 {
		width = 60
	}
	subtitle := "证据接地的科研文献智能体"
	if width < 76 {
		subtitle = "证据接地的科研智能体"
	}
	prompt := "从一个论断、论文、主题或趋势开始;输入 / 查看命令。"
	body := []string{
		asciiBrand(width),
		stInk.Render("科研智能体终端"),
		stFaint.Render(subtitle),
		"",
		stConn.Render(strings.Repeat("─", minInt(width-12, 72))),
		stFaint.Render(prompt),
		"",
	}
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(cAccent).
		Padding(1, 2).
		Width(width - 4).
		Render(strings.Join(body, "\n"))
}

func renderThemeBlock() string {
	lines := []string{stFaint.Render("  可用主题:")}
	for _, name := range themeOrder {
		theme := themes[name]
		mark := " "
		style := stCmd
		if name == currentTheme {
			mark = "◆"
			style = stAccent
		}
		lines = append(lines, style.Render(fmt.Sprintf("  %s %-8s %s · %s", mark, theme.Name, theme.Title, theme.Desc)))
	}
	lines = append(lines, "")
	lines = append(lines, stFaint.Render("  用法: /theme paper  或启动前设置 SCISCOPE_TUI_THEME=paper"))
	return strings.Join(lines, "\n")
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func splashStatusLines() []string {
	dir := sessionDir()
	return []string{
		stFaint.Render("Backend  check with /doctor"),
		stFaint.Render("LLM      check with /doctor"),
		stFaint.Render("Sessions " + clip(dir, 30)),
	}
}

func recentSplashLines(sessions []sessionFile) []string {
	if len(sessions) == 0 {
		return []string{
			stFaint.Render("暂无本地会话"),
			stFaint.Render("/demo 播放黄金演示流"),
			stFaint.Render("完成回答后自动保存"),
		}
	}
	lines := []string{}
	for i, session := range sessions {
		if i >= 3 {
			break
		}
		question := session.LastQuestion
		if question == "" {
			question = strings.TrimSuffix(session.Name, filepath.Ext(session.Name))
		}
		lines = append(lines, stFaint.Render(fmt.Sprintf("/resume %d  %s", session.Index, clip(question, 32))))
		lines = append(lines, stFaint.Render("  "+session.ModTime.Format("01-02 15:04")))
	}
	return lines
}

// kindIcon previews what a command does before it is run: ◇ expands into an
// agent question, ▤ opens a submenu, • runs instantly.
func kindIcon(k slashCommandKind) string {
	switch k {
	case commandPrompt:
		return "◇"
	case commandUI:
		return "▤"
	default:
		return "•"
	}
}

// styleUsageCell dims a usage hint but renders its "<...>" argument placeholder in
// the accent colour, so commands that take an argument stand out at a glance.
func styleUsageCell(cell string) string {
	if i := strings.IndexByte(cell, '<'); i >= 0 {
		return stFaint.Render(cell[:i]) + stAccent.Render(cell[i:])
	}
	return stFaint.Render(cell)
}

func (m model) renderCommandPalette(width int) string {
	if width < 48 {
		width = 48
	}
	matches := filterCmds(m.ti.Value())
	if len(matches) == 0 {
		return ""
	}
	inner := width - 6
	if inner < 38 {
		inner = 38
	}
	idx := m.menuIdx % len(matches)
	cursorW, iconW, cmdW, titleW, keyW := 2, 2, 12, 10, 18
	descW := inner - cursorW - iconW - cmdW - titleW - keyW
	if descW < 10 {
		descW = 10
	}
	pad := func(s string, w int) string { return lipgloss.NewStyle().Width(w).Render(s) }
	rows := []string{
		stAccent.Render("命令启动器") + stFaint.Render("  · ↑/↓ 选择 · Enter 填入/执行 · Tab 补全 · Esc 关闭"),
	}
	lastCat := ""
	for i, c := range matches {
		if c.category != lastCat { // group commands under faint category headers
			rows = append(rows, stFaint.Render("  "+c.category))
			lastCat = c.category
		}
		sel := i == idx
		marker := "  "
		if sel {
			marker = "▶ "
		}
		cells := []string{
			pad(marker, cursorW),
			pad(kindIcon(c.kind), iconW),
			pad(c.cmd, cmdW),
			pad(clipWidth(c.title, titleW-1), titleW),
			pad(clipWidth(c.desc, descW-1), descW),
			pad(clipWidth(c.key, keyW-1), keyW),
		}
		if sel { // uniform high-contrast highlight for the selected row
			rows = append(rows, stSelCmd.Width(inner).Render(strings.Join(cells, "")))
			continue
		}
		styled := stFaint.Render(cells[0]) + stAccent.Render(cells[1]) + stInk.Render(cells[2]) +
			stMuted.Render(cells[3]) + stFaint.Render(cells[4]) + styleUsageCell(cells[5])
		rows = append(rows, lipgloss.NewStyle().Width(inner).Render(styled))
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(rows, "\n"))
}

func durationText(d time.Duration) string {
	if d <= 0 {
		return ""
	}
	return fmt.Sprintf("%.1fs", d.Seconds())
}

func permissionNotice(name string) (string, bool) {
	switch name {
	case "export_bibliography":
		return "权限提示: 引文导出会生成可复制的外部文本，请确认导出内容适合写入报告或会话记录。", true
	default:
		return "", false
	}
}

func toolResultLabel(name, result string) string {
	if strings.HasPrefix(result, "[未执行]") {
		return "校验拦截"
	}
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			return fmt.Sprintf("证据卡 %d 篇", len(papers))
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			if cr.TopSimilarity > 0 {
				return fmt.Sprintf("论断核查 · %s · %.3f", cr.Verdict, cr.TopSimilarity)
			}
			return "论断核查 · " + cr.Verdict
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			return fmt.Sprintf("趋势卡 %d 条", len(rows))
		}
	}
	return "工具返回"
}

func timelineMarkdownBody(events []timelineEvent) string {
	lines := []string{}
	lastPhase := ""
	for _, ev := range events {
		phase := eventPhase(ev)
		if phase != lastPhase {
			lines = append(lines, "### "+phase)
			lastPhase = phase
		}
		label := strings.TrimSpace(ev.Label)
		if label == "" {
			label = toolPlainLabel(ev.Tool)
		}
		line := "- " + label
		if ev.Detail != "" {
			line += ": " + ev.Detail
		}
		if d := durationText(ev.Duration); d != "" {
			line += " (" + d + ")"
		}
		lines = append(lines, line)
	}
	return strings.Join(lines, "\n")
}

func renderTimelineMarkdown(events []timelineEvent) string {
	body := timelineMarkdownBody(events)
	if body == "" {
		return ""
	}
	return "## 科研工作流时间线\n\n" + body + "\n"
}

func renderTimelineBlock(events []timelineEvent) string {
	if len(events) == 0 {
		return panelRow("timeline", "本轮执行时间线", "empty", []string{
			"暂无本轮执行轨迹。",
			"先输入一个科研问题, 或运行 /demo 播放黄金演示流。",
		})
	}
	body := []string{}
	lastPhase := ""
	for _, ev := range events {
		phase := eventPhase(ev)
		if phase != lastPhase {
			body = append(body, phase)
			lastPhase = phase
		}
		label := ev.Label
		if label == "" {
			label = toolPlainLabel(ev.Tool)
		}
		line := "  - " + label
		if ev.Detail != "" {
			line += " · " + ev.Detail
		}
		if d := durationText(ev.Duration); d != "" {
			line += " · " + d
		}
		body = append(body, line)
	}
	return panelRow("timeline", "本轮执行时间线", fmt.Sprintf("%d events", len(events)), body)
}

func renderPlanBlock(plan planMsg) string {
	body := []string{}
	for i, step := range plan {
		body = append(body, fmt.Sprintf("[%d] %s", i+1, step))
	}
	return panelRow("thinking", "思考过程", fmt.Sprintf("%d 步", len(plan)), body)
}

func renderToolCallBlock(name, args string) string {
	body := []string{}
	if strings.TrimSpace(args) != "" {
		body = append(body, args)
	}
	return panelRow("action", toolPlainLabel(name), "tool call", body)
}

func renderReflectBlock(s string) string {
	return panelRow("thinking", "自我纠错", "", []string{s})
}

func renderToolResult(name, result string, width int, elapsed time.Duration) string {
	// A validation gate rejected the call (e.g. fabricated paper_id). Surface it
	// as a distinct recovery card — the model also gets this back and self-corrects.
	if strings.HasPrefix(result, "[未执行]") {
		reason := strings.TrimSpace(strings.TrimPrefix(result, "[未执行]"))
		return panelRow("recovery", "校验拦截 · "+toolPlainLabel(name), durationText(elapsed), []string{stWarn.Render(reason)})
	}
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			body := []string{}
			for i, p := range papers {
				if i >= 4 {
					body = append(body, fmt.Sprintf("+%d 篇更多证据 · /timeline 查看完整证据链", len(papers)-i))
					break
				}
				meta := []string{p.PaperID}
				if p.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", p.Year))
				}
				if len(p.Authors) > 0 {
					meta = append(meta, strings.Join(p.Authors, ", "))
				}
				body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(p.Title, 72)))
				body = append(body, strings.Join(meta, " · "))
				if p.Snippet != "" {
					body = append(body, clip(p.Snippet, 96))
				}
			}
			return panelRow("evidence", fmt.Sprintf("证据卡 %d 篇", len(papers)), durationText(elapsed), body)
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			meta := cr.Verdict
			if cr.TopSimilarity > 0 {
				meta += fmt.Sprintf(" · %.3f", cr.TopSimilarity)
			}
			if d := durationText(elapsed); d != "" {
				meta += " · " + d
			}
			body := []string{}
			if cr.Claim != "" {
				body = append(body, clip(cr.Claim, 96))
			}
			for i, ev := range cr.Evidence {
				if i >= 4 {
					body = append(body, fmt.Sprintf("+%d 条更多证据 · /timeline 查看", len(cr.Evidence)-i))
					break
				}
				meta := []string{ev.PaperID}
				if ev.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", ev.Year))
				}
				if ev.Similarity > 0 {
					meta = append(meta, fmt.Sprintf("相似度 %.3f", ev.Similarity))
				}
				body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(ev.Title, 78)))
				body = append(body, strings.Join(meta, " · "))
			}
			return panelRow("verify", "论断核查", meta, body)
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			body := []string{}
			for i, row := range rows {
				if i >= 3 {
					body = append(body, fmt.Sprintf("+%d 条更多趋势 · /timeline 查看", len(rows)-i))
					break
				}
				kw := fmt.Sprintf("%v", row["关键词"])
				body = append(body, fmt.Sprintf("[%d] %s · 方向 %s · 阶段 %s · 依据 %s", i+1, kw, trendDirection(row), trendStage(row), trendBasis(row)))
			}
			return panelRow("trend", fmt.Sprintf("趋势卡 %d 条", len(rows)), durationText(elapsed), body)
		}
	}
	return panelRow("result", toolPlainLabel(name), durationText(elapsed), []string{preview(result)})
}

func summarizeToolResultMarkdown(name, result string) string {
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			lines := []string{}
			for i, p := range papers {
				if i >= 8 {
					lines = append(lines, fmt.Sprintf("- 另有 %d 篇证据未展开", len(papers)-i))
					break
				}
				meta := []string{p.PaperID}
				if p.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", p.Year))
				}
				if len(p.Authors) > 0 {
					meta = append(meta, strings.Join(p.Authors, ", "))
				}
				lines = append(lines, fmt.Sprintf("- [%d] %s", i+1, p.Title))
				if len(meta) > 0 {
					lines = append(lines, "  "+strings.Join(meta, " · "))
				}
				if p.Snippet != "" {
					lines = append(lines, "  "+p.Snippet)
				}
			}
			return strings.Join(lines, "\n")
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			head := fmt.Sprintf("论断: %s\n支持等级: %s", cr.Claim, cr.Verdict)
			if cr.TopSimilarity > 0 {
				head += fmt.Sprintf("\n最高接地相似度: %.3f", cr.TopSimilarity)
			}
			lines := []string{head}
			for i, ev := range cr.Evidence {
				if i >= 8 {
					break
				}
				meta := []string{ev.PaperID}
				if ev.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", ev.Year))
				}
				if ev.Similarity > 0 {
					meta = append(meta, fmt.Sprintf("相似度 %.3f", ev.Similarity))
				}
				lines = append(lines, fmt.Sprintf("- [%d] %s", i+1, ev.Title))
				if len(meta) > 0 {
					lines = append(lines, "  "+strings.Join(meta, " · "))
				}
			}
			return strings.Join(lines, "\n")
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			lines := []string{}
			for i, row := range rows {
				if i >= 8 {
					break
				}
				lines = append(lines, fmt.Sprintf("- [%d] %v: 方向 %s · 阶段 %s · 依据 %s", i+1, row["关键词"], trendDirection(row), trendStage(row), trendBasis(row)))
			}
			return strings.Join(lines, "\n")
		}
	}
	return preview(result)
}

func trendDirection(row map[string]any) string {
	if value := stringField(row, "增长方向"); value != "" {
		return value
	}
	if value := stringField(row, "趋势判定"); value != "" {
		return value
	}
	return "待判断"
}

func trendStage(row map[string]any) string {
	if value := stringField(row, "生命周期阶段"); value != "" {
		return value
	}
	return "未分层"
}

func trendBasis(row map[string]any) string {
	stats, _ := row["统计依据"].(map[string]any)
	parts := []string{}
	if value := fieldText(stats, "近期活跃度分"); value != "" {
		parts = append(parts, "近年活跃 "+value)
	} else if value := fieldText(row, "动量分"); value != "" {
		parts = append(parts, "近年活跃 "+value)
	}
	if value := fieldText(stats, "短期加速分"); value != "" {
		parts = append(parts, "短期加速 "+value)
	} else if value := fieldText(row, "爆发分"); value != "" {
		parts = append(parts, "短期加速 "+value)
	}
	if value := fieldText(stats, "稳健年增长斜率"); value != "" {
		parts = append(parts, "年增长 "+value)
	}
	if len(parts) == 0 {
		return "样本年度分布"
	}
	return strings.Join(parts, " · ")
}

func stringField(row map[string]any, key string) string {
	value, ok := row[key]
	if !ok || value == nil {
		return ""
	}
	text := strings.TrimSpace(fmt.Sprintf("%v", value))
	if text == "" || text == "<nil>" {
		return ""
	}
	return text
}

func fieldText(row map[string]any, key string) string {
	if row == nil {
		return ""
	}
	return stringField(row, key)
}

func exportMarkdown(events []transcriptEvent, generatedAt time.Time) string {
	lines := []string{
		"# SciScope 会话导出",
		"",
		"导出时间: " + generatedAt.Format("2006-01-02 15:04:05 MST"),
		"",
	}
	for _, ev := range events {
		content := strings.TrimSpace(ev.Content)
		if content == "" {
			continue
		}
		switch ev.Kind {
		case "user":
			lines = append(lines, "## 用户问题", "", content, "")
		case "plan":
			lines = append(lines, "## 执行计划", "", content, "")
		case "tool_call":
			lines = append(lines, "## 工具调用: "+ev.Tool, "", content, "")
		case "tool_result":
			lines = append(lines, "## 证据结果: "+ev.Tool, "", content, "")
		case "timeline":
			lines = append(lines, "## 工具调用时间线", "", content, "")
		case "permission":
			lines = append(lines, "## 权限提示: "+ev.Tool, "", content, "")
		case "reflect":
			lines = append(lines, "## 自我纠错", "", content, "")
		case "assistant":
			lines = append(lines, "## 智能体回答", "", content, "")
		case "error":
			lines = append(lines, "## 错误与恢复建议", "", content, "")
		default:
			lines = append(lines, "## "+ev.Kind, "", content, "")
		}
	}
	return strings.TrimSpace(strings.Join(lines, "\n")) + "\n"
}

func exportLastSession(dir string) (string, string, error) {
	sessions, err := listSessionFiles(dir, 1)
	if err != nil {
		return "", "", err
	}
	if len(sessions) == 0 {
		return "", "", fmt.Errorf("no saved sessions in %s", dir)
	}
	b, err := os.ReadFile(sessions[0].Path)
	if err != nil {
		return "", "", err
	}
	return string(b), sessions[0].Path, nil
}

func sessionDir() string {
	// Session persistence layout:
	// 1) explicit override via SCISCOPE_SESSION_DIR
	// 2) fallback to ~/.sciscope/sessions
	// 3) final fallback to ./sessions
	if v := os.Getenv("SCISCOPE_SESSION_DIR"); v != "" {
		return v
	}
	if home, err := os.UserHomeDir(); err == nil {
		return filepath.Join(home, ".sciscope", "sessions")
	}
	return "sessions"
}

func listSessionFiles(dir string, limit int) ([]sessionFile, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	sessions := []sessionFile{}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".md" {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		lastQuestion := ""
		if b, err := os.ReadFile(path); err == nil {
			lastQuestion = extractLastQuestion(string(b))
		}
		sessions = append(sessions, sessionFile{
			Path:         path,
			Name:         entry.Name(),
			LastQuestion: lastQuestion,
			ModTime:      info.ModTime(),
			Size:         info.Size(),
		})
	}
	sort.Slice(sessions, func(i, j int) bool {
		return sessions[i].ModTime.After(sessions[j].ModTime)
	})
	if limit > 0 && len(sessions) > limit {
		sessions = sessions[:limit]
	}
	for i := range sessions {
		sessions[i].Index = i + 1
	}
	return sessions, nil
}

func extractLastQuestion(markdown string) string {
	lines := strings.Split(markdown, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) != "## 用户问题" {
			continue
		}
		chunk := []string{}
		for j := i + 1; j < len(lines); j++ {
			line := strings.TrimSpace(lines[j])
			if strings.HasPrefix(line, "## ") {
				break
			}
			if line != "" {
				chunk = append(chunk, line)
			}
		}
		return strings.TrimSpace(strings.Join(chunk, "\n"))
	}
	return ""
}

func loadSessionMarkdown(path string) (loadedSession, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return loadedSession{}, err
	}
	content := string(b)
	return loadedSession{
		Path:         path,
		Content:      content,
		LastQuestion: extractLastQuestion(content),
	}, nil
}

func renderSessionsList(sessions []sessionFile) string {
	if len(sessions) == 0 {
		return stWarn.Render("  没有找到已保存会话。完成一次回答后会自动保存。")
	}
	lines := []string{stBullet.Render("⏺ ") + stAccent.Render("最近会话")}
	for _, s := range sessions {
		sizeKB := float64(s.Size) / 1024
		meta := fmt.Sprintf("/resume %d · %s · %.1f KB", s.Index, s.ModTime.Format("01-02 15:04"), sizeKB)
		lines = append(lines,
			stConn.Render("  ⎿  ")+stInk.Render(s.Name),
			stFaint.Render("      "+meta),
		)
	}
	return strings.Join(lines, "\n")
}

func writeSessionMarkdown(dir string, events []transcriptEvent, now time.Time) (string, error) {
	// Persisted sessions are append-only; if a timestamped filename exists,
	// a numeric suffix is appended to avoid overwrite.
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	base := "sciscope-session-" + now.Format("20060102-150405")
	path := filepath.Join(dir, base+".md")
	for i := 2; ; i++ {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			break
		}
		path = filepath.Join(dir, fmt.Sprintf("%s-%02d.md", base, i))
	}
	if err := os.WriteFile(path, []byte(exportMarkdown(events, now)), 0o644); err != nil {
		return "", err
	}
	return path, nil
}

func recoveryAction(s string) recoveryHint {
	low := strings.ToLower(s)
	switch {
	case strings.Contains(low, "connection refused") || strings.Contains(low, "无法连接后端"):
		return recoveryHint{
			Title:     "后端未连接",
			Command:   "make backend",
			Message:   "建议: 先运行 make backend, 然后输入 /retry 重试上一问。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "llm") || strings.Contains(low, "vllm") || strings.Contains(low, "8001"):
		return recoveryHint{
			Title:     "LLM 服务不可用",
			Command:   "make llm",
			Message:   "建议: 检查 make llm 或 make dev-vllm 是否已启动，然后输入 /retry。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "graphs not built"):
		return recoveryHint{
			Title:     "图谱未构建",
			Command:   "make graph-export",
			Message:   "建议: 运行 make graph-export 后输入 /retry。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "database") || strings.Contains(low, "postgres") || strings.Contains(low, "pgvector"):
		return recoveryHint{
			Title:     "数据库不可用",
			Command:   "make postgres-refresh",
			Message:   "建议: 检查 PostgreSQL, 必要时运行 make postgres-refresh, 然后输入 /retry。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: true,
		}
	default:
		return recoveryHint{
			Title:     "请求失败",
			Message:   "建议: 查看错误详情；如果环境已恢复，可输入 /retry 重试上一问。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	}
}

func friendlyError(s string) string {
	action := recoveryAction(s)
	lines := []string{s, "  " + action.Message}
	if action.Command != "" {
		lines = append(lines, "  恢复动作: "+action.Command)
	}
	return strings.Join(lines, "\n")
}

func renderRecoveryPanel(s string) string {
	action := recoveryAction(s)
	meta := action.Severity
	if meta == "" {
		meta = "recoverable"
	}
	body := []string{
		"error   " + preview(s),
		"reason  " + action.Message,
	}
	if action.Command != "" {
		body = append(body, "primary "+action.Command)
	}
	if action.Retryable {
		body = append(body, "next    /retry")
	}
	if action.Inspect != "" {
		body = append(body, "inspect "+action.Inspect)
	}
	return panelRow("recovery", action.Title, meta, body)
}

func (m *model) startQuestion(v string, retry bool) tea.Cmd {
	prefix := "❯ "
	if retry {
		prefix = "↻ "
	}
	hist := append([]turn(nil), m.history...)
	m.ti.SetValue("")
	m.appendBlock(stUser.Render(prefix) + stInk.Render(v))
	m.record("user", "", v)
	m.history = append(m.history, turn{"user", v})
	m.lastQuestion = v
	m.answering = true
	m.answer = ""
	m.used = nil
	m.toolStart = map[string]time.Time{}
	m.timeline = nil
	m.lastMeta = eventMeta{}
	m.lastStreamKind = ""
	m.nodeSeen = nil
	m.livePlan = nil
	m.liveReflect = ""
	m.verb = verbs[rand.Intn(len(verbs))]
	m.start = time.Now()
	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel
	q := v
	return tea.Batch(
		func() tea.Msg { go stream(ctx, backendURL(), q, hist, m.sessionID, retry, m.sub); return nil },
		listen(m.sub),
		m.spin.Tick,
	)
}
