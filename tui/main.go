// SciScope terminal client — a Bubble Tea (Charm) TUI that consumes the agent's
// SSE event stream (/api/agent/stream). The Python agent core is untouched: this
// is purely a presentation client, styled after Claude Code's visual grammar
// (⏺ action bullets, ⎿ tool-result connectors, an animated verb spinner).
//
// Run:  make tui        (requires `make backend` on :8000 and `make llm` on :8001)
package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/lipgloss"
)

// ---- palette (cyan research console, à la Claude Code structure) ----
var (
	cAccent  = lipgloss.Color("#5fd7d7")
	cTool    = lipgloss.Color("#87afff")
	cWarn    = lipgloss.Color("#d7af5f")
	cUser    = lipgloss.Color("#87d787")
	cError   = lipgloss.Color("#ff8787")
	cMuted   = lipgloss.Color("#808080")
	cFaint   = lipgloss.Color("#5f5f5f")
	cInk     = lipgloss.Color("#d7d7d7")
	stAccent = lipgloss.NewStyle().Foreground(cAccent).Bold(true)
	stBullet = lipgloss.NewStyle().Foreground(cAccent).Bold(true) // ⏺
	stConn   = lipgloss.NewStyle().Foreground(cFaint)             // ⎿
	stTool   = lipgloss.NewStyle().Foreground(cTool)
	stWarn   = lipgloss.NewStyle().Foreground(cWarn)
	stError  = lipgloss.NewStyle().Foreground(cError)
	stUser   = lipgloss.NewStyle().Foreground(cUser).Bold(true)
	stMuted  = lipgloss.NewStyle().Foreground(cMuted)
	stFaint  = lipgloss.NewStyle().Foreground(cFaint)
	stInk    = lipgloss.NewStyle().Foreground(cInk)
	stSelCmd = lipgloss.NewStyle().Background(cAccent).Foreground(lipgloss.Color("#1c1c1c")).Bold(true)
	stCmd    = lipgloss.NewStyle().Foreground(cMuted)
)

// rotating "spinner verbs" (Claude Code signature) — localized, research-flavored.
var verbs = []string{
	"检索中", "推敲中", "归纳中", "研判中", "爬梳中", "斟酌中", "综合中",
	"推演中", "酝酿中", "梳理中", "求证中", "琢磨中", "盘点中", "沉思中",
}

// ---- tool icons/labels (Nerd Font / Font Awesome glyphs, U+F0xx PUA) ----
var toolLabels = map[string][2]string{
	"search_literature":     {"\uf002", "检索文献"}, // search
	"get_trends":            {"\uf201", "研究趋势"}, // line-chart
	"recommend_papers":      {"\uf02d", "论文推荐"}, // book
	"get_paper":             {"\uf15c", "论文详情"}, // file-text
	"summarize_field":       {"\uf0ca", "领域综述"}, // list-ul
	"compare_papers":        {"\uf24e", "论文对比"}, // balance-scale
	"export_bibliography":   {"\uf02e", "引文导出"}, // bookmark
	"query_knowledge_graph": {"\uf0e8", "知识图谱"}, // sitemap
	"verify_claim":          {"\uf058", "论断核查"}, // check-circle
}

// Nerd Font glyphs by default; set SCISCOPE_TUI_ICONS=off for plain text (no font
// dependency \u2014 falls back to just the Chinese label, Claude Code-plain style).
var useIcons = os.Getenv("SCISCOPE_TUI_ICONS") != "off"

func toolLabel(name string) string {
	if v, ok := toolLabels[name]; ok {
		if useIcons {
			return v[0] + "  " + v[1]
		}
		return v[1]
	}
	if useIcons {
		return "\uf013  " + name
	}
	return name
}

func toolPlainLabel(name string) string {
	if v, ok := toolLabels[name]; ok {
		return v[1]
	}
	return name
}

type slashCmd struct{ cmd, desc string }

var slashCmds = []slashCmd{
	{"/help", "显示帮助"},
	{"/tools", "列出可用工具"},
	{"/export", "导出 Markdown 会话"},
	{"/retry", "重试上一问"},
	{"/sessions", "列出最近会话"},
	{"/resume", "恢复会话: /resume 1"},
	{"/clear", "清空对话"},
	{"/quit", "退出"},
}

func filterCmds(prefix string) []slashCmd {
	out := []slashCmd{}
	for _, c := range slashCmds {
		if strings.HasPrefix(c.cmd, prefix) {
			out = append(out, c)
		}
	}
	return out
}

// ---- stream messages ----
type turn struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}
type planMsg []string
type textMsg string
type toolCallMsg struct {
	name string
	args map[string]any
}
type toolResultMsg struct{ name, result string }
type reflectMsg string
type finalMsg string
type errMsg string
type doneMsg struct{}

type transcriptEvent struct {
	Kind    string
	Tool    string
	Content string
}

type recoveryHint struct {
	Title     string
	Command   string
	Message   string
	Retryable bool
}

type sessionFile struct {
	Index   int
	Path    string
	Name    string
	ModTime time.Time
	Size    int64
}

type loadedSession struct {
	Path         string
	Content      string
	LastQuestion string
}

type timelineEvent struct {
	Kind     string
	Tool     string
	Label    string
	Detail   string
	Duration time.Duration
}

type evidencePaper struct {
	PaperID string   `json:"paper_id"`
	Title   string   `json:"标题"`
	Year    int      `json:"年份"`
	Authors []string `json:"作者"`
	Snippet string   `json:"摘要片段"`
}

type claimEvidence struct {
	PaperID    string  `json:"paper_id"`
	Title      string  `json:"标题"`
	Year       int     `json:"年份"`
	Similarity float64 `json:"接地相似度"`
}

type claimResult struct {
	Claim         string          `json:"论断"`
	Verdict       string          `json:"支持等级"`
	TopSimilarity float64         `json:"最高接地相似度"`
	Evidence      []claimEvidence `json:"证据"`
}

func backendURL() string {
	if v := os.Getenv("SCISCOPE_BACKEND"); v != "" {
		return v
	}
	return "http://127.0.0.1:8000"
}

// stream POSTs the question and pushes one tea.Msg per SSE event into sub.
func stream(ctx context.Context, backend, q string, history []turn, sub chan tea.Msg) {
	body, _ := json.Marshal(map[string]any{"question": q, "history": history})
	req, _ := http.NewRequestWithContext(ctx, "POST", backend+"/api/agent/stream", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		if ctx.Err() == nil { // not a user interrupt
			sub <- errMsg("无法连接后端 " + backend + ":" + err.Error())
		}
		sub <- doneMsg{}
		return
	}
	defer resp.Body.Close()
	sc := bufio.NewScanner(resp.Body)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		line := sc.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(line[len("data:"):])
		if data == "[DONE]" {
			break
		}
		var ev struct {
			Type    string          `json:"type"`
			Payload json.RawMessage `json:"payload"`
		}
		if json.Unmarshal([]byte(data), &ev) != nil {
			continue
		}
		switch ev.Type {
		case "plan":
			var s []string
			json.Unmarshal(ev.Payload, &s)
			sub <- planMsg(s)
		case "text":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- textMsg(s)
		case "tool_call":
			var t struct {
				Name string         `json:"name"`
				Args map[string]any `json:"args"`
			}
			json.Unmarshal(ev.Payload, &t)
			sub <- toolCallMsg{t.Name, t.Args}
		case "tool_result":
			var t struct {
				Name   string `json:"name"`
				Result string `json:"result"`
			}
			json.Unmarshal(ev.Payload, &t)
			sub <- toolResultMsg{t.Name, t.Result}
		case "reflect":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- reflectMsg(s)
		case "final":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- finalMsg(s)
		case "error":
			var s string
			json.Unmarshal(ev.Payload, &s)
			sub <- errMsg(s)
		}
	}
	sub <- doneMsg{}
}

func listen(sub chan tea.Msg) tea.Cmd {
	return func() tea.Msg { return <-sub }
}

// ---- model ----
type model struct {
	ti             textinput.Model
	vp             viewport.Model
	spin           spinner.Model
	blocks         []string // finalized conversation lines
	answer         string   // current streaming answer
	answering      bool
	verb           string
	tick           int
	start          time.Time // when the current turn began (for the elapsed timer)
	used           []string  // tools called this turn (for the answer footer)
	toolStart      map[string]time.Time
	history        []turn
	transcript     []transcriptEvent
	timeline       []timelineEvent
	recentSessions []sessionFile
	lastExport     string
	lastQuestion   string
	sub            chan tea.Msg
	cancel         context.CancelFunc
	menuIdx        int
	ready          bool
}

func initialModel() model {
	ti := textinput.New()
	ti.Placeholder = "输入科研问题,或 / 看命令"
	ti.Prompt = stAccent.Render("❯ ")
	ti.Focus()
	ti.CharLimit = 2000

	sp := spinner.New()
	sp.Spinner = spinner.Spinner{
		Frames: []string{"✻", "✢", "✳", "∗", "✦", "✶"},
		FPS:    time.Second / 8,
	}
	sp.Style = stAccent
	return model{ti: ti, spin: sp, sub: make(chan tea.Msg, 64)}
}

func (m model) Init() tea.Cmd { return textinput.Blink }

func (m *model) appendBlock(s string) {
	m.blocks = append(m.blocks, s)
	m.refresh()
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

func (m *model) refresh() {
	content := strings.Join(m.blocks, "\n")
	if m.answering && m.answer != "" {
		content += "\n" + stBullet.Render("⏺ ") + stInk.Render(m.answer)
	}
	m.vp.SetContent(content)
	m.vp.GotoBottom()
}

func (m model) argsStr(args map[string]any) string {
	keys := make([]string, 0, len(args))
	for k := range args {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := []string{}
	for _, k := range keys {
		v := args[k]
		if v == nil || v == "" || v == float64(0) {
			continue
		}
		parts = append(parts, fmt.Sprintf("%v", v))
	}
	return strings.Join(parts, " · ")
}

func preview(s string) string {
	s = strings.TrimSpace(strings.ReplaceAll(s, "\n", " "))
	r := []rune(s)
	if len(r) > 84 {
		return string(r[:84]) + "…"
	}
	return s
}

func clip(s string, n int) string {
	s = strings.TrimSpace(s)
	r := []rune(s)
	if len(r) > n {
		return string(r[:n]) + "…"
	}
	return s
}

func elapsedSuffix(d time.Duration) string {
	if d <= 0 {
		return ""
	}
	return stFaint.Render(fmt.Sprintf("  %.1fs", d.Seconds()))
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
	for i, ev := range events {
		label := strings.TrimSpace(ev.Label)
		if label == "" {
			label = toolPlainLabel(ev.Tool)
		}
		line := fmt.Sprintf("%d. %s", i+1, label)
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
	return "## 工具调用时间线\n\n" + body + "\n"
}

func renderTimelineBlock(events []timelineEvent) string {
	if len(events) == 0 {
		return ""
	}
	lines := []string{stBullet.Render("⏺ ") + stAccent.Render("工具调用时间线")}
	for i, ev := range events {
		label := ev.Label
		if label == "" {
			label = toolPlainLabel(ev.Tool)
		}
		line := fmt.Sprintf("[%d] %s", i+1, label)
		if ev.Detail != "" {
			line += " · " + ev.Detail
		}
		if d := durationText(ev.Duration); d != "" {
			line += " · " + d
		}
		lines = append(lines, stConn.Render("  ⎿  ")+stFaint.Render(line))
	}
	return strings.Join(lines, "\n")
}

func renderToolResult(name, result string, width int, elapsed time.Duration) string {
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			lines := []string{stConn.Render("  ⎿  ") + stTool.Render(fmt.Sprintf("证据卡 %d 篇", len(papers))) + elapsedSuffix(elapsed)}
			for i, p := range papers {
				if i >= 4 {
					lines = append(lines, stFaint.Render(fmt.Sprintf("      +%d 篇更多证据", len(papers)-i)))
					break
				}
				meta := []string{p.PaperID}
				if p.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", p.Year))
				}
				if len(p.Authors) > 0 {
					meta = append(meta, strings.Join(p.Authors, ", "))
				}
				lines = append(lines,
					stFaint.Render("      "+fmt.Sprintf("[%d] ", i+1))+stInk.Render(clip(p.Title, 72)),
					stFaint.Render("          "+strings.Join(meta, " · ")),
				)
				if p.Snippet != "" {
					lines = append(lines, stMuted.Render("          "+clip(p.Snippet, 96)))
				}
			}
			return strings.Join(lines, "\n")
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			head := fmt.Sprintf("论断核查 · %s", cr.Verdict)
			if cr.TopSimilarity > 0 {
				head += fmt.Sprintf(" · %.3f", cr.TopSimilarity)
			}
			lines := []string{stConn.Render("  ⎿  ") + stTool.Render(head) + elapsedSuffix(elapsed)}
			if cr.Claim != "" {
				lines = append(lines, stMuted.Render("      "+clip(cr.Claim, 96)))
			}
			for i, ev := range cr.Evidence {
				if i >= 4 {
					break
				}
				meta := []string{ev.PaperID}
				if ev.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", ev.Year))
				}
				if ev.Similarity > 0 {
					meta = append(meta, fmt.Sprintf("相似度 %.3f", ev.Similarity))
				}
				lines = append(lines,
					stFaint.Render("      "+fmt.Sprintf("[%d] ", i+1))+stInk.Render(clip(ev.Title, 78)),
					stFaint.Render("          "+strings.Join(meta, " · ")),
				)
			}
			return strings.Join(lines, "\n")
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			lines := []string{stConn.Render("  ⎿  ") + stTool.Render(fmt.Sprintf("趋势卡 %d 条", len(rows))) + elapsedSuffix(elapsed)}
			for i, row := range rows {
				if i >= 3 {
					break
				}
				kw := fmt.Sprintf("%v", row["关键词"])
				trend := fmt.Sprintf("%v", row["趋势判定"])
				momentum := fmt.Sprintf("%v", row["动量分"])
				lines = append(lines, stFaint.Render("      "+fmt.Sprintf("[%d] ", i+1))+stInk.Render(kw)+" "+stMuted.Render("趋势 "+trend+" · 动量 "+momentum))
			}
			return strings.Join(lines, "\n")
		}
	}
	return stConn.Render("  ⎿  ") + stFaint.Render(preview(result)) + elapsedSuffix(elapsed)
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
				lines = append(lines, fmt.Sprintf("- [%d] %v: 趋势 %v · 动量 %v", i+1, row["关键词"], row["趋势判定"], row["动量分"]))
			}
			return strings.Join(lines, "\n")
		}
	}
	return preview(result)
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

func sessionDir() string {
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
		sessions = append(sessions, sessionFile{
			Path:    path,
			Name:    entry.Name(),
			ModTime: info.ModTime(),
			Size:    info.Size(),
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
			Retryable: true,
		}
	case strings.Contains(low, "llm") || strings.Contains(low, "vllm") || strings.Contains(low, "8001"):
		return recoveryHint{
			Title:     "LLM 服务不可用",
			Command:   "make llm",
			Message:   "建议: 检查 make llm 或 make dev-vllm 是否已启动，然后输入 /retry。",
			Retryable: true,
		}
	case strings.Contains(low, "graphs not built"):
		return recoveryHint{
			Title:     "图谱未构建",
			Command:   "make graph-export",
			Message:   "建议: 运行 make graph-export 后输入 /retry。",
			Retryable: true,
		}
	case strings.Contains(low, "database") || strings.Contains(low, "postgres") || strings.Contains(low, "pgvector"):
		return recoveryHint{
			Title:     "数据库不可用",
			Command:   "make postgres-refresh",
			Message:   "建议: 检查 PostgreSQL, 必要时运行 make postgres-refresh, 然后输入 /retry。",
			Retryable: true,
		}
	default:
		return recoveryHint{
			Title:     "请求失败",
			Message:   "建议: 查看错误详情；如果环境已恢复，可输入 /retry 重试上一问。",
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
	m.verb = verbs[rand.Intn(len(verbs))]
	m.start = time.Now()
	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel
	q := v
	return tea.Batch(
		func() tea.Msg { go stream(ctx, backendURL(), q, hist, m.sub); return nil },
		listen(m.sub),
		m.spin.Tick,
	)
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		header, footer := 3, 4 // bordered banner = 3 lines; spinner/input/status = 4
		vh := msg.Height - header - footer
		if vh < 3 {
			vh = 3
		}
		if !m.ready {
			m.vp = viewport.New(msg.Width, vh)
			m.vp.SetContent(stFaint.Render("输入问题开始 · / 看命令 · Ctrl+C 退出"))
			m.ready = true
		} else {
			m.vp.Width, m.vp.Height = msg.Width, vh
		}
		m.ti.Width = msg.Width - 4

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

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit
		case "esc":
			if m.answering && m.cancel != nil {
				m.cancel()
			}
			return m, nil
		case "up", "down", "tab":
			if strings.HasPrefix(m.ti.Value(), "/") {
				ms := filterCmds(m.ti.Value())
				if len(ms) > 0 {
					switch msg.String() {
					case "up":
						m.menuIdx = (m.menuIdx - 1 + len(ms)) % len(ms)
					case "down":
						m.menuIdx = (m.menuIdx + 1) % len(ms)
					case "tab":
						m.ti.SetValue(ms[m.menuIdx%len(ms)].cmd)
					}
					return m, nil
				}
			}
		case "enter":
			v := strings.TrimSpace(m.ti.Value())
			if v == "" || m.answering {
				return m, nil
			}
			if strings.HasPrefix(v, "/") {
				if ms := filterCmds(m.ti.Value()); len(ms) > 0 && m.menuIdx < len(ms) && !strings.Contains(v, " ") {
					v = ms[m.menuIdx].cmd
				}
				m.ti.SetValue("")
				m.menuIdx = 0
				return m.runSlash(v)
			}
			cmd := m.startQuestion(v, false)
			return m, cmd
		}

	case planMsg:
		lines := []string{stBullet.Render("⏺ ") + stAccent.Render("执行计划")}
		plain := []string{}
		for _, s := range msg {
			lines = append(lines, stConn.Render("  ⎿  ")+stMuted.Render("☐ "+s))
			plain = append(plain, "- "+s)
		}
		m.addTimeline(timelineEvent{Kind: "plan", Label: "执行计划", Detail: strings.Join([]string(msg), " / ")})
		m.record("plan", "", strings.Join(plain, "\n"))
		m.appendBlock(strings.Join(lines, "\n"))
		return m, listen(m.sub)

	case toolCallMsg:
		m.used = append(m.used, msg.name)
		if m.toolStart == nil {
			m.toolStart = map[string]time.Time{}
		}
		m.toolStart[msg.name] = time.Now()
		line := stBullet.Render("⏺ ") + stTool.Render(toolLabel(msg.name))
		detail := m.argsStr(msg.args)
		if a := m.argsStr(msg.args); a != "" {
			line += stFaint.Render("(" + a + ")")
			m.record("tool_call", msg.name, a)
		} else {
			m.record("tool_call", msg.name, toolLabel(msg.name))
		}
		m.addTimeline(timelineEvent{Kind: "tool_call", Tool: msg.name, Label: toolPlainLabel(msg.name), Detail: detail})
		if notice, ok := permissionNotice(msg.name); ok {
			line += "\n" + stWarn.Render("  "+notice)
			m.record("permission", msg.name, notice)
			m.addTimeline(timelineEvent{Kind: "permission", Tool: msg.name, Label: "权限提示", Detail: notice})
		}
		m.appendBlock(line)
		return m, listen(m.sub)

	case toolResultMsg:
		var elapsed time.Duration
		if m.toolStart != nil {
			elapsed = time.Since(m.toolStart[msg.name])
		}
		m.addTimeline(timelineEvent{Kind: "tool_result", Tool: msg.name, Label: toolResultLabel(msg.name, msg.result), Duration: elapsed})
		m.record("tool_result", msg.name, summarizeToolResultMarkdown(msg.name, msg.result))
		m.appendBlock(renderToolResult(msg.name, msg.result, m.vp.Width, elapsed))
		return m, listen(m.sub)

	case reflectMsg:
		m.answer = ""
		m.record("reflect", "", string(msg))
		m.appendBlock(stBullet.Render("⏺ ") + stWarn.Render("自我纠错 ") + stFaint.Render(string(msg)))
		return m, listen(m.sub)

	case textMsg:
		m.answer += string(msg)
		m.refresh()
		return m, listen(m.sub)

	case finalMsg:
		if m.answer == "" {
			m.answer = string(msg)
		}
		return m, listen(m.sub)

	case errMsg:
		errText := friendlyError(string(msg))
		m.record("error", "", errText)
		action := recoveryAction(string(msg))
		m.addTimeline(timelineEvent{Kind: "error", Label: action.Title, Detail: action.Message})
		m.appendBlock(stError.Render("⏺ ✗ " + errText))
		return m, listen(m.sub)

	case doneMsg:
		if m.answer != "" {
			ans := m.answer
			m.answering = false
			m.addTimeline(timelineEvent{Kind: "final", Label: "回答完成"})
			if body := timelineMarkdownBody(m.timeline); body != "" {
				m.record("timeline", "", body)
				m.appendBlock(renderTimelineBlock(m.timeline))
			}
			m.record("assistant", "", ans)
			m.appendBlock(m.renderAnswer())
			m.history = append(m.history, turn{"assistant", ans})
			if len(m.history) > 12 {
				m.history = m.history[len(m.history)-12:]
			}
			if path, err := writeSessionMarkdown(sessionDir(), m.transcript, time.Now()); err == nil {
				m.lastExport = path
				m.appendBlock(stFaint.Render("  会话已保存: " + path))
			} else {
				m.appendBlock(stWarn.Render("  会话保存失败: " + err.Error()))
			}
		}
		m.answer = ""
		m.answering = false
		m.cancel = nil
		m.refresh()
		return m, nil
	}

	m.ti, cmd = m.ti.Update(msg)
	return m, cmd
}

// renderAnswer renders the finished answer as Markdown (glamour) under a ⏺ bullet,
// with a dim footer listing the tools the agent used this turn.
func (m model) renderAnswer() string {
	w := m.vp.Width - 4
	if w < 20 {
		w = 20
	}
	body := strings.Trim(m.answer, "\n")
	// Fixed dark style — NOT WithAutoStyle(), which queries the terminal background
	// (OSC 11) on every render and leaks the response (]11;rgb:…) into the UI.
	if r, err := glamour.NewTermRenderer(glamour.WithStandardStyle("dark"), glamour.WithWordWrap(w)); err == nil {
		if out, e := r.Render(m.answer); e == nil {
			body = strings.Trim(out, "\n")
		}
	}
	out := stBullet.Render("⏺ ") + body
	if len(m.used) > 0 {
		seen := map[string]bool{}
		labels := []string{}
		for _, n := range m.used {
			if !seen[n] {
				seen[n] = true
				labels = append(labels, toolLabel(n))
			}
		}
		out += "\n" + stFaint.Render("  "+strings.Join(labels, "  "))
	}
	return out
}

func (m model) runSlash(v string) (tea.Model, tea.Cmd) {
	fields := strings.Fields(v)
	cmdName := v
	if len(fields) > 0 {
		cmdName = fields[0]
	}
	switch cmdName {
	case "/quit":
		return m, tea.Quit
	case "/clear":
		m.blocks = nil
		m.history = nil
		m.transcript = nil
		m.timeline = nil
		m.lastExport = ""
		m.lastQuestion = ""
		m.refresh()
	case "/help":
		m.appendBlock(stFaint.Render("  命令: /help /tools /sessions /resume N /export /retry /clear /quit · Esc 中断 · Ctrl+C 退出"))
	case "/tools":
		lines := []string{stFaint.Render("  可用工具(LLM 自主调用):")}
		for _, name := range []string{"search_literature", "get_trends", "recommend_papers", "get_paper", "summarize_field", "compare_papers", "export_bibliography", "query_knowledge_graph", "verify_claim"} {
			lines = append(lines, "    "+toolLabel(name))
		}
		m.appendBlock(strings.Join(lines, "\n"))
	case "/sessions":
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err != nil {
			m.appendBlock(stWarn.Render("  读取会话失败: " + err.Error()))
			return m, nil
		}
		m.recentSessions = sessions
		m.appendBlock(renderSessionsList(sessions))
	case "/resume":
		if len(fields) < 2 {
			m.appendBlock(stWarn.Render("  用法: /resume 1。先输入 /sessions 查看最近会话。"))
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
		if _, err := fmt.Sscanf(fields[1], "%d", &idx); err != nil || idx < 1 || idx > len(m.recentSessions) {
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
		m.transcript = []transcriptEvent{{Kind: "session", Content: session.Content}}
		m.lastQuestion = session.LastQuestion
		m.lastExport = session.Path
		m.refresh()
	case "/retry":
		if m.lastQuestion == "" {
			m.appendBlock(stWarn.Render("  暂无可重试的问题。先提一个问题, 或从会话记录中复制问题。"))
			return m, nil
		}
		cmd := m.startQuestion(m.lastQuestion, true)
		return m, cmd
	case "/export":
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
	default:
		m.appendBlock(stWarn.Render("  未知命令 " + v))
	}
	return m, nil
}

func (m model) View() string {
	if !m.ready {
		return "启动中…"
	}
	banner := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).BorderForeground(cAccent).Padding(0, 1)
	header := banner.Render(stAccent.Render("◆ SciScope") + "  " + stInk.Render("科研智能体终端") + "  " + stFaint.Render("evidence · timeline · retry · export"))
	parts := []string{header, m.vp.View()}

	// thinking spinner (Claude Code-style verb + esc hint) while a turn runs
	if m.answering {
		elapsed := int(time.Since(m.start).Seconds())
		parts = append(parts, m.spin.View()+" "+stAccent.Render(m.verb+"…")+stFaint.Render(fmt.Sprintf("  (%ds · esc 中断)", elapsed)))
	} else if strings.HasPrefix(m.ti.Value(), "/") {
		if ms := filterCmds(m.ti.Value()); len(ms) > 0 {
			idx := m.menuIdx % len(ms)
			menu := []string{}
			for i, c := range ms {
				row := fmt.Sprintf(" %-13s %s", c.cmd, c.desc)
				if i == idx {
					menu = append(menu, stSelCmd.Render(row))
				} else {
					menu = append(menu, stCmd.Render(row))
				}
			}
			parts = append(parts, strings.Join(menu, "\n"))
		}
	}

	statusText := fmt.Sprintf("  turns %d · /sessions · /retry · /export · Ctrl+C", len(m.history)/2)
	if m.lastExport != "" {
		statusText += " · saved " + filepath.Base(m.lastExport)
	}
	status := stFaint.Render(statusText)
	parts = append(parts, m.ti.View(), status)
	return strings.Join(parts, "\n")
}

func main() {
	p := tea.NewProgram(initialModel(), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
