// SciScope terminal client — a Bubble Tea (Charm) TUI that consumes the agent's
// SSE event stream (/api/agent/stream). The Python agent core is untouched: this
// is purely a presentation client, so the look can match Claude Code's polish
// while plan/tool/reflect/answer logic stays server-side.
//
// Run:  make tui        (requires `make backend` on :8000 and `make llm` on :8001)
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sort"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/lipgloss"
)

// ---- palette (matches the rich CLI: warm terracotta accent) ----
var (
	cAccent  = lipgloss.Color("#d7875f")
	cTool    = lipgloss.Color("#5fafd7")
	cWarn    = lipgloss.Color("#d7af5f")
	cUser    = lipgloss.Color("#87d787")
	cMuted   = lipgloss.Color("#808080")
	cFaint   = lipgloss.Color("#5f5f5f")
	cInk     = lipgloss.Color("#d7d7d7")
	stAccent = lipgloss.NewStyle().Foreground(cAccent).Bold(true)
	stTool   = lipgloss.NewStyle().Foreground(cTool)
	stWarn   = lipgloss.NewStyle().Foreground(cWarn)
	stUser   = lipgloss.NewStyle().Foreground(cUser).Bold(true)
	stMuted  = lipgloss.NewStyle().Foreground(cMuted)
	stFaint  = lipgloss.NewStyle().Foreground(cFaint)
	stInk    = lipgloss.NewStyle().Foreground(cInk)
	stSelCmd = lipgloss.NewStyle().Background(cAccent).Foreground(lipgloss.Color("#1c1c1c")).Bold(true)
	stCmd    = lipgloss.NewStyle().Foreground(cMuted)
)

// ---- tool icons/labels (mirror the Python client) ----
var toolLabels = map[string][2]string{
	"search_literature":     {"🔍", "检索文献"},
	"get_trends":            {"📈", "研究趋势"},
	"recommend_papers":      {"📚", "论文推荐"},
	"get_paper":             {"📄", "论文详情"},
	"summarize_field":       {"📝", "领域综述"},
	"compare_papers":        {"⚖️", "论文对比"},
	"export_bibliography":   {"🔖", "引文导出"},
	"query_knowledge_graph": {"🕸️", "知识图谱"},
	"verify_claim":          {"✅", "论断核查"},
}

func toolLabel(name string) string {
	if v, ok := toolLabels[name]; ok {
		return v[0] + " " + v[1]
	}
	return "⚙ " + name
}

type slashCmd struct{ cmd, desc string }

var slashCmds = []slashCmd{
	{"/help", "显示帮助"},
	{"/tools", "列出可用工具"},
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
type reflectMsg string
type finalMsg string
type errMsg string
type doneMsg struct{}

func backendURL() string {
	if v := os.Getenv("SCISCOPE_BACKEND"); v != "" {
		return v
	}
	return "http://127.0.0.1:8000"
}

// stream POSTs the question and pushes one tea.Msg per SSE event into sub.
func stream(backend, q string, history []turn, sub chan tea.Msg) {
	body, _ := json.Marshal(map[string]any{"question": q, "history": history})
	resp, err := http.Post(backend+"/api/agent/stream", "application/json", bytes.NewReader(body))
	if err != nil {
		sub <- errMsg("无法连接后端 " + backend + ":" + err.Error())
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
	ti        textinput.Model
	vp        viewport.Model
	blocks    []string // finalized conversation lines
	answer    string   // current streaming answer
	answering bool
	used      []string // tools called this turn (for the answer footer)
	history   []turn
	sub       chan tea.Msg
	menuIdx   int
	ready     bool
	w, h      int
}

func initialModel() model {
	ti := textinput.New()
	ti.Placeholder = "输入科研问题,或 / 看命令"
	ti.Prompt = stAccent.Render("❯ ")
	ti.Focus()
	ti.CharLimit = 2000
	return model{ti: ti, sub: make(chan tea.Msg, 64)}
}

func (m model) Init() tea.Cmd { return textinput.Blink }

func (m *model) appendBlock(s string) {
	m.blocks = append(m.blocks, s)
	m.refresh()
}

func (m *model) refresh() {
	content := strings.Join(m.blocks, "\n")
	if m.answering && m.answer != "" {
		content += "\n" + stInk.Render(m.answer)
	}
	m.vp.SetContent(content)
	m.vp.GotoBottom()
}

func (m model) argsStr(args map[string]any) string {
	parts := []string{}
	keys := make([]string, 0, len(args))
	for k := range args {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		v := args[k]
		if v == nil || v == "" || v == float64(0) {
			continue
		}
		parts = append(parts, fmt.Sprintf("%v", v))
	}
	return strings.Join(parts, " · ")
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		m.w, m.h = msg.Width, msg.Height
		header, footer := 3, 4 // bordered banner = 3 lines; input+status+margin = 4
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

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit
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
				if ms := filterCmds(m.ti.Value()); len(ms) > 0 && m.menuIdx < len(ms) {
					v = ms[m.menuIdx].cmd
				}
				m.ti.SetValue("")
				m.menuIdx = 0
				return m.runSlash(v)
			}
			// send to agent
			m.ti.SetValue("")
			m.appendBlock(stUser.Render("你  ") + v)
			m.history = append(m.history, turn{"user", v})
			m.answering = true
			m.answer = ""
			m.used = nil
			q := v
			hist := append([]turn(nil), m.history...)
			return m, tea.Batch(
				func() tea.Msg { go stream(backendURL(), q, hist, m.sub); return nil },
				listen(m.sub),
			)
		}

	case planMsg:
		lines := []string{stAccent.Render("🗺 执行计划")}
		for i, s := range msg {
			lines = append(lines, stFaint.Render(fmt.Sprintf("   %d. ", i+1))+stMuted.Render(s))
		}
		m.appendBlock(strings.Join(lines, "\n"))
		return m, listen(m.sub)

	case toolCallMsg:
		m.used = append(m.used, msg.name)
		m.appendBlock(stTool.Render("  "+toolLabel(msg.name)) + "  " + stFaint.Render(m.argsStr(msg.args)))
		return m, listen(m.sub)

	case reflectMsg:
		m.answer = ""
		m.appendBlock(stWarn.Render("  🔄 自我纠错 ") + stFaint.Render(string(msg)))
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
		m.appendBlock(lipgloss.NewStyle().Foreground(lipgloss.Color("#d75f5f")).Render("  ✗ " + string(msg)))
		return m, listen(m.sub)

	case doneMsg:
		if m.answer != "" {
			ans := m.answer
			rendered := m.renderAnswer()
			m.answer = ""
			m.answering = false
			m.appendBlock(rendered)
			m.history = append(m.history, turn{"assistant", ans})
			if len(m.history) > 12 {
				m.history = m.history[len(m.history)-12:]
			}
		}
		m.answer = ""
		m.answering = false
		m.refresh()
		return m, nil
	}

	m.ti, cmd = m.ti.Update(msg)
	return m, cmd
}

// renderAnswer turns the finished answer into a polished block: glamour-rendered
// Markdown behind a terracotta left-bar, with a "✦ 回答" title and a footer listing
// the tools the agent used this turn.
func (m model) renderAnswer() string {
	w := m.vp.Width - 4
	if w < 20 {
		w = 20
	}
	body := m.answer
	if r, err := glamour.NewTermRenderer(glamour.WithAutoStyle(), glamour.WithWordWrap(w)); err == nil {
		if out, e := r.Render(m.answer); e == nil {
			body = strings.TrimRight(out, "\n")
		}
	}
	parts := []string{stAccent.Render("✦ 回答"), body}
	if len(m.used) > 0 {
		seen := map[string]bool{}
		labels := []string{}
		for _, n := range m.used {
			if !seen[n] {
				seen[n] = true
				labels = append(labels, toolLabel(n))
			}
		}
		parts = append(parts, stFaint.Render("— "+strings.Join(labels, "  ")+" —"))
	}
	bar := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), false, false, false, true).
		BorderForeground(cAccent).PaddingLeft(1)
	return bar.Render(strings.Join(parts, "\n"))
}

func (m model) runSlash(v string) (tea.Model, tea.Cmd) {
	switch v {
	case "/quit":
		return m, tea.Quit
	case "/clear":
		m.blocks = nil
		m.history = nil
		m.refresh()
	case "/help":
		m.appendBlock(stFaint.Render("  命令: /help /tools /clear /quit"))
	case "/tools":
		lines := []string{stFaint.Render("  可用工具(LLM 自主调用):")}
		for _, name := range []string{"search_literature", "get_trends", "recommend_papers", "get_paper", "summarize_field", "compare_papers", "export_bibliography", "query_knowledge_graph", "verify_claim"} {
			lines = append(lines, "    "+toolLabel(name))
		}
		m.appendBlock(strings.Join(lines, "\n"))
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
		Border(lipgloss.RoundedBorder()).BorderForeground(cAccent).
		Padding(0, 1)
	header := banner.Render(stAccent.Render("✦ SciScope 科研智能体") + "  " + stFaint.Render("检索·趋势·推荐·图谱·综述·对比·引文·核查"))
	parts := []string{header, m.vp.View()}

	// inline slash menu (Claude Code-style flush list)
	if strings.HasPrefix(m.ti.Value(), "/") {
		if ms := filterCmds(m.ti.Value()); len(ms) > 0 {
			idx := m.menuIdx % len(ms)
			menu := []string{}
			for i, c := range ms {
				row := fmt.Sprintf(" %-11s %s", c.cmd, c.desc)
				if i == idx {
					menu = append(menu, stSelCmd.Render(row))
				} else {
					menu = append(menu, stCmd.Render(row))
				}
			}
			parts = append(parts, strings.Join(menu, "\n"))
		}
	}

	status := stFaint.Render(fmt.Sprintf("  对话 %d 轮 · /help 命令 · Ctrl+C 退出", len(m.history)/2))
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
