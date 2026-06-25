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
	"flag"
	"fmt"
	"io"
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

var version = "dev"

type cliOptions struct {
	Command    string
	Demo       bool
	Doctor     bool
	ExportLast bool
	Version    bool
	Help       bool
}

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

type slashCmd struct {
	cmd       string
	title     string
	desc      string
	category  string
	key       string
	suggested bool
}

var slashCmds = []slashCmd{
	{cmd: "/demo", title: "Golden demo", desc: "播放可验证证据流", category: "Suggested", key: "demo", suggested: true},
	{cmd: "/doctor", title: "Status check", desc: "检查后端、LLM、会话与图谱", category: "Suggested", key: "doctor", suggested: true},
	{cmd: "/retry", title: "Retry last turn", desc: "同一 LangGraph 会话线程恢复上一问", category: "Suggested", key: "retry", suggested: true},
	{cmd: "/export", title: "Export report", desc: "导出 Markdown 会话与证据", category: "Suggested", key: "export", suggested: true},
	{cmd: "/sessions", title: "Recent sessions", desc: "列出最近研究会话", category: "Session", key: "sessions"},
	{cmd: "/resume", title: "Resume session", desc: "恢复会话: /resume 1", category: "Session", key: "resume N"},
	{cmd: "/tools", title: "Agent tools", desc: "列出 LLM 可自主调用的科研工具", category: "Evidence", key: "tools"},
	{cmd: "/help", title: "Help", desc: "显示命令与快捷键", category: "System", key: "?"},
	{cmd: "/clear", title: "Clear view", desc: "清空当前对话视图", category: "System", key: "clear"},
	{cmd: "/quit", title: "Quit", desc: "退出 SciScope TUI", category: "System", key: "ctrl+c"},
}

func filterCmds(prefix string) []slashCmd {
	query := strings.TrimSpace(strings.TrimPrefix(prefix, "/"))
	query = strings.ToLower(query)
	matches := []slashCmd{}
	for _, c := range slashCmds {
		haystack := strings.ToLower(strings.Join([]string{c.cmd, c.title, c.desc, c.category}, " "))
		if query == "" || strings.Contains(haystack, query) {
			matches = append(matches, c)
		}
	}
	if query != "" {
		return matches
	}
	out := []slashCmd{}
	for _, c := range matches {
		if c.suggested {
			out = append(out, c)
		}
	}
	for _, c := range matches {
		if !c.suggested {
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
type eventMeta struct {
	Runtime   string `json:"runtime"`
	Node      string `json:"node"`
	SessionID string `json:"session_id"`
	ElapsedMS int    `json:"elapsed_ms"`
	Retry     bool   `json:"retry"`
}
type planMsg []string
type textMsg string
type toolCallMsg struct {
	name string
	args map[string]any
	meta eventMeta
}
type toolResultMsg struct {
	name   string
	result string
	meta   eventMeta
}
type reflectMsg string
type finalMsg string
type errMsg string
type doneMsg struct{}
type demoStartMsg string
type nodePulseMsg struct {
	kind string
	meta eventMeta
}

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

type doctorCheck struct {
	Name   string
	Status string
	Detail string
}

type sessionFile struct {
	Index        int
	Path         string
	Name         string
	LastQuestion string
	ModTime      time.Time
	Size         int64
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

func demoMode() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("SCISCOPE_TUI_DEMO")))
	return v == "1" || v == "true" || v == "yes"
}

func parseCLIOptions(args []string) (cliOptions, error) {
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		cmd := args[0]
		switch cmd {
		case "demo":
			return cliOptions{Command: cmd, Demo: true}, nil
		case "doctor":
			return cliOptions{Command: cmd, Doctor: true}, nil
		case "export":
			opts := cliOptions{Command: cmd}
			for _, arg := range args[1:] {
				switch arg {
				case "--last":
					opts.ExportLast = true
				case "--help", "-h":
					opts.Help = true
				default:
					return opts, fmt.Errorf("unknown export option %q", arg)
				}
			}
			if !opts.Help && !opts.ExportLast {
				return opts, fmt.Errorf("export requires --last")
			}
			return opts, nil
		default:
			return cliOptions{Command: cmd}, fmt.Errorf("unknown command %q", cmd)
		}
	}
	fs := flag.NewFlagSet("sciscope-tui", flag.ContinueOnError)
	fs.SetOutput(new(bytes.Buffer))
	var opts cliOptions
	fs.BoolVar(&opts.Demo, "demo", false, "play the offline SciScope golden demo")
	fs.BoolVar(&opts.Version, "version", false, "print version")
	fs.BoolVar(&opts.Version, "v", false, "print version")
	fs.BoolVar(&opts.Help, "help", false, "print help")
	fs.BoolVar(&opts.Help, "h", false, "print help")
	if err := fs.Parse(args); err != nil {
		return opts, err
	}
	return opts, nil
}

func versionString(v string) string {
	return "sciscope-tui " + v
}

func helpString() string {
	return strings.Join([]string{
		"sciscope-tui - SciScope research agent terminal",
		"",
		"Usage:",
		"  sciscope-tui          start the TUI",
		"  sciscope-tui doctor   check backend, LLM, sessions and assets",
		"  sciscope-tui demo     play the offline golden demo",
		"  sciscope-tui export --last",
		"  sciscope-tui --demo   play the offline golden demo",
		"  sciscope-tui --version",
		"",
		"Environment:",
		"  SCISCOPE_BACKEND              backend URL, default http://127.0.0.1:8000",
		"  SCISCOPE_TUI_DEMO_DELAY_MS    demo playback delay",
	}, "\n")
}

func healthURL() string {
	return strings.TrimRight(backendURL(), "/") + "/health"
}

func llmURL() string {
	if v := os.Getenv("LOCAL_LLM_BASE_URL"); v != "" {
		return strings.TrimRight(v, "/") + "/models"
	}
	return "http://127.0.0.1:8001/v1/models"
}

func httpReachable(url string, timeout time.Duration) bool {
	client := http.Client{Timeout: timeout}
	resp, err := client.Get(url)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 500
}

func collectDoctorChecks() []doctorCheck {
	checks := []doctorCheck{}
	if httpReachable(healthURL(), 700*time.Millisecond) {
		checks = append(checks, doctorCheck{"Backend", "ok", healthURL()})
	} else {
		checks = append(checks, doctorCheck{"Backend", "warn", "not reachable; run make backend"})
	}
	if httpReachable(llmURL(), 700*time.Millisecond) {
		checks = append(checks, doctorCheck{"LLM", "ok", llmURL()})
	} else {
		checks = append(checks, doctorCheck{"LLM", "warn", "not reachable; run make llm or use --demo"})
	}
	dir := sessionDir()
	if err := os.MkdirAll(dir, 0o755); err == nil {
		checks = append(checks, doctorCheck{"Sessions", "ok", dir})
	} else {
		checks = append(checks, doctorCheck{"Sessions", "error", err.Error()})
	}
	if _, err := os.Stat(filepath.Join("..", "output", "graphs")); err == nil {
		checks = append(checks, doctorCheck{"Graph assets", "ok", "output/graphs"})
	} else if _, err := os.Stat(filepath.Join("output", "graphs")); err == nil {
		checks = append(checks, doctorCheck{"Graph assets", "ok", "output/graphs"})
	} else {
		checks = append(checks, doctorCheck{"Graph assets", "warn", "missing; run make graph-export"})
	}
	return checks
}

func renderDoctorReport(checks []doctorCheck) string {
	lines := []string{"SciScope doctor", ""}
	for _, check := range checks {
		mark := "unknown"
		switch check.Status {
		case "ok":
			mark = "ok"
		case "warn":
			mark = "warn"
		case "error":
			mark = "error"
		}
		lines = append(lines, fmt.Sprintf("%-12s %-4s %s", check.Name, mark, check.Detail))
	}
	lines = append(lines, "", "Next: sciscope-tui demo | sciscope-tui export --last")
	return strings.Join(lines, "\n")
}

func demoDelay() time.Duration {
	v := strings.TrimSpace(os.Getenv("SCISCOPE_TUI_DEMO_DELAY_MS"))
	if v == "" {
		return 420 * time.Millisecond
	}
	var ms int
	if _, err := fmt.Sscanf(v, "%d", &ms); err != nil || ms < 0 {
		return 420 * time.Millisecond
	}
	return time.Duration(ms) * time.Millisecond
}

func demoScriptMessages() []tea.Msg {
	verifyResult := `{
		"论断":"检索增强生成能够降低大语言模型回答中的幻觉风险",
		"支持等级":"强支持",
		"最高接地相似度":0.846,
		"证据":[
			{"paper_id":"W4411065983","标题":"Retrieval-Augmented Generation and Hallucination Mitigation","年份":2025,"接地相似度":0.846},
			{"paper_id":"2309.01431","标题":"Benchmarking Large Language Models in Retrieval-Augmented Generation","年份":2023,"接地相似度":0.827}
		]
	}`
	searchResult := `[
		{"paper_id":"W4411065983","标题":"Retrieval-Augmented Generation and Hallucination Mitigation","年份":2025,"作者":["Li","Zhang"],"摘要片段":"Retrieved evidence improves factual grounding and reduces unsupported generations."},
		{"paper_id":"2309.01431","标题":"Benchmarking Large Language Models in Retrieval-Augmented Generation","年份":2023,"作者":["Chen","Wang"],"摘要片段":"RAG evaluation links answer faithfulness to evidence quality."},
		{"paper_id":"W4399001120","标题":"Evidence-grounded Scientific Question Answering","年份":2024,"作者":["Kumar"],"摘要片段":"Scientific QA benefits from citation-aware retrieval and claim verification."}
	]`
	return []tea.Msg{
		demoStartMsg("核查：RAG（检索增强生成）能够降低大语言模型回答中的幻觉风险，并给出可验证证据。"),
		planMsg{"解析中文论断并生成英文检索表达", "调用 verify_claim 做跨语言接地核查", "补充检索高相关论文并输出证据卡", "汇总支持等级、证据出处和可复现结论"},
		toolCallMsg{name: "verify_claim", args: map[string]any{"claim": "检索增强生成能够降低大语言模型回答中的幻觉风险"}},
		toolResultMsg{name: "verify_claim", result: verifyResult},
		toolCallMsg{name: "search_literature", args: map[string]any{"query": "retrieval augmented generation hallucination mitigation", "top_k": 3}},
		toolResultMsg{name: "search_literature", result: searchResult},
		reflectMsg("证据相似度与论文主题一致，结论限定为“降低风险”，不夸大为完全消除。"),
		finalMsg("结论：该论断获得强支持。SciScope 将中文论断映射到英文前沿文献，通过 verify_claim 给出最高接地相似度 0.846，并列出可追溯、可验证的论文证据。更稳妥的表述是：RAG 能显著降低无依据回答的风险，但效果取决于检索质量、证据覆盖和生成模型是否忠实使用证据。"),
		doneMsg{},
	}
}

// playDemo replays a deterministic offline sequence so "/demo" and the
// environment-gated startup path work without backend/LLM/network.
// The sequence is fixed: user prompt -> plan -> tool calls/results ->
// reflect -> final, ending with doneMsg.
func playDemo(sub chan tea.Msg) {
	delay := demoDelay()
	for _, msg := range demoScriptMessages() {
		if delay > 0 {
			time.Sleep(delay)
		}
		sub <- msg
	}
}

// stream POSTs the question and pushes one tea.Msg per valid SSE payload.
// Supported event types:
//
//	plan      -> []string{"..."}
//	text      -> incremental answer chunk
//	tool_call -> {name,args}
//	tool_result-> {name,result}
//	reflect   -> self-check text
//	final     -> final answer block
//	error     -> recoverable error text
//
// Scanner keeps only lines starting with "data:" and stops at "[DONE]".
func stream(ctx context.Context, backend, q string, history []turn, sessionID string, retry bool, sub chan tea.Msg) {
	body, _ := json.Marshal(map[string]any{"question": q, "history": history, "session_id": sessionID, "retry": retry})
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
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		sub <- errMsg(formatHTTPError(resp))
		sub <- doneMsg{}
		return
	}
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
			Meta    eventMeta       `json:"meta"`
		}
		if json.Unmarshal([]byte(data), &ev) != nil {
			continue
		}
		if !metaEmpty(ev.Meta) {
			sub <- nodePulseMsg{kind: ev.Type, meta: ev.Meta}
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
			sub <- toolCallMsg{name: t.Name, args: t.Args, meta: ev.Meta}
		case "tool_result":
			var t struct {
				Name   string `json:"name"`
				Result string `json:"result"`
			}
			json.Unmarshal(ev.Payload, &t)
			sub <- toolResultMsg{name: t.Name, result: t.Result, meta: ev.Meta}
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
	sessionID      string
	lastMeta       eventMeta
	lastStreamKind string
	nodeSeen       []string
	sub            chan tea.Msg
	cancel         context.CancelFunc
	menuIdx        int
	ready          bool
	demo           bool
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
	return model{ti: ti, spin: sp, sub: make(chan tea.Msg, 64), demo: demoMode(), sessionID: newSessionID()}
}

func newSessionID() string {
	return "tui-" + time.Now().UTC().Format("20060102T150405.000000000")
}

func (m model) Init() tea.Cmd {
	if m.demo {
		return tea.Batch(textinput.Blink, func() tea.Msg {
			go playDemo(m.sub)
			return nil
		}, listen(m.sub), m.spin.Tick)
	}
	return textinput.Blink
}

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

func metaDetail(meta eventMeta) string {
	parts := []string{}
	if meta.Node != "" {
		parts = append(parts, "node "+meta.Node)
	}
	if meta.ElapsedMS > 0 {
		parts = append(parts, fmt.Sprintf("%dms", meta.ElapsedMS))
	}
	if meta.Retry {
		parts = append(parts, "retry")
	}
	return strings.Join(parts, " · ")
}

func metaEmpty(meta eventMeta) bool {
	return meta.Runtime == "" && meta.Node == "" && meta.SessionID == "" && meta.ElapsedMS == 0 && !meta.Retry
}

func nodeLabel(node string) string {
	switch node {
	case "prepare":
		return "准备上下文"
	case "plan":
		return "规划步骤"
	case "llm_step":
		return "模型推理"
	case "execute_tools":
		return "调用工具"
	case "reflect":
		return "证据反思"
	case "force_synthesis":
		return "强制综合"
	default:
		if node == "" {
			return "等待事件"
		}
		return node
	}
}

func streamKindLabel(kind string) string {
	switch kind {
	case "plan":
		return "plan"
	case "text":
		return "text"
	case "tool_call":
		return "tool call"
	case "tool_result":
		return "tool result"
	case "reflect":
		return "reflect"
	case "final":
		return "final"
	case "error":
		return "error"
	default:
		return "stream"
	}
}

func appendUniqueNode(nodes []string, node string) []string {
	node = strings.TrimSpace(node)
	if node == "" {
		return nodes
	}
	for _, seen := range nodes {
		if seen == node {
			return nodes
		}
	}
	return append(nodes, node)
}

func (m *model) loadRecentSessions() {
	sessions, err := listSessionFiles(sessionDir(), 3)
	if err == nil {
		m.recentSessions = sessions
	}
}

func formatHTTPError(resp *http.Response) string {
	payload, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	detail := strings.TrimSpace(string(payload))
	if detail == "" {
		detail = resp.Status
	}
	return fmt.Sprintf("后端返回 %s: %s", resp.Status, detail)
}

func (m *model) refresh() {
	content := strings.Join(m.blocks, "\n")
	if m.answering && m.answer != "" {
		content += "\n" + stBullet.Render("⏺ ") + stInk.Render(m.answer)
	}
	if strings.TrimSpace(content) == "" && m.vp.Width > 0 {
		m.loadRecentSessions()
		content = renderSplash(m.vp.Width, m.recentSessions)
	}
	m.vp.SetContent(content)
	m.vp.GotoBottom()
}

func renderStreamRail(events []timelineEvent, meta eventMeta, nodes []string, kind string, elapsed time.Duration, width int) string {
	if width < 48 {
		width = 48
	}
	runtime := meta.Runtime
	if runtime == "" {
		runtime = "langgraph"
	}
	node := nodeLabel(meta.Node)
	if meta.Node == "" && len(nodes) > 0 {
		node = nodeLabel(nodes[len(nodes)-1])
	}
	session := meta.SessionID
	if session == "" {
		session = "local session"
	}
	status := []string{
		stAccent.Render(runtime),
		stFaint.Render("node ") + stInk.Render(node),
		stFaint.Render(streamKindLabel(kind)),
		stFaint.Render(fmt.Sprintf("%.0fs", elapsed.Seconds())),
	}
	if meta.Retry {
		status = append(status, stWarn.Render("retry"))
	}
	if meta.ElapsedMS > 0 {
		status = append(status, stFaint.Render(fmt.Sprintf("%dms", meta.ElapsedMS)))
	}

	body := []string{
		strings.Join(status, stFaint.Render(" · ")),
		stFaint.Render("thread " + clip(session, 38)),
	}
	if len(nodes) > 0 {
		labels := []string{}
		start := len(nodes) - 5
		if start < 0 {
			start = 0
		}
		for _, node := range nodes[start:] {
			labels = append(labels, nodeLabel(node))
		}
		body = append(body, stFaint.Render("graph  ")+stInk.Render(strings.Join(labels, stFaint.Render(" → "))))
	}
	if len(events) > 0 {
		body = append(body, stFaint.Render("latest"))
		start := len(events) - 4
		if start < 0 {
			start = 0
		}
		for _, ev := range events[start:] {
			label := ev.Label
			if label == "" {
				label = toolPlainLabel(ev.Tool)
			}
			line := "  " + label
			if ev.Detail != "" {
				line += " · " + clip(ev.Detail, 54)
			}
			if d := durationText(ev.Duration); d != "" {
				line += " · " + d
			}
			body = append(body, line)
		}
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(body, "\n"))
}

func (m model) renderComposer(width int) string {
	if width < 48 {
		width = 48
	}
	raw := strings.TrimSpace(m.ti.Value())
	inputWidth := width - 8
	if inputWidth < 34 {
		inputWidth = 34
	}
	value := raw
	if value == "" {
		value = stFaint.Render("Ask a research question, verify a claim, or type /")
	} else {
		value = strings.ReplaceAll(value, "\n", "\n"+strings.Repeat(" ", 2))
	}
	mode := "ready"
	if m.answering {
		mode = "streaming"
	} else if strings.Contains(raw, "\n") {
		mode = "multi-line · Shift+Enter"
	} else {
		mode = "Shift+Enter 多行"
	}
	runtime := m.lastMeta.Runtime
	if runtime == "" {
		runtime = "langgraph"
	}
	session := clip(m.sessionID, 20)
	if m.lastMeta.SessionID != "" {
		session = clip(m.lastMeta.SessionID, 20)
	}
	leftMeta := lipgloss.JoinHorizontal(
		lipgloss.Top,
		stAccent.Render("agent"),
		stFaint.Render(" · "),
		stInk.Render(runtime),
		stFaint.Render(" · session "),
		stInk.Render(session),
	)
	rightMeta := mode
	if m.lastExport != "" {
		rightMeta += " · saved " + filepath.Base(m.lastExport)
	}
	head := lipgloss.JoinHorizontal(
		lipgloss.Top,
		lipgloss.NewStyle().Width(inputWidth-26).Render(leftMeta),
		stFaint.Render(clip(rightMeta, 26)),
	)
	promptSymbol := "❯"
	if m.answering {
		promptSymbol = "●"
	}
	inputLine := lipgloss.NewStyle().
		Width(inputWidth).
		Render(stAccent.Render(promptSymbol+" ") + value)
	hint := lipgloss.JoinHorizontal(
		lipgloss.Top,
		stAccent.Render("Enter"),
		stFaint.Render(" send"),
		stFaint.Render("  ·  "),
		stAccent.Render("Esc"),
		stFaint.Render(" interrupt"),
		stFaint.Render("  ·  "),
		stAccent.Render("/"),
		stFaint.Render(" commands"),
		stFaint.Render("  ·  "),
		stAccent.Render("/retry"),
		stFaint.Render(" recover"),
	)
	body := strings.Join([]string{
		head,
		inputLine,
		hint,
	}, "\n")
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cAccent).
		Padding(0, 1).
		Width(width - 2).
		Render(body)
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

func panelRow(kind, title, meta string, body []string) string {
	// panelRow is the internal line grammar for dashboard/splash/tool blocks:
	//   header: "╭─ <kind> · <title> [· <meta>]"
	//   body: each logical row prefixed with "│  "
	//   footer: "╰─"
	head := "╭─ " + kind + " · " + title
	if strings.TrimSpace(meta) != "" {
		head += " · " + meta
	}
	lines := []string{stConn.Render(head)}
	for _, line := range body {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		lines = append(lines, stFaint.Render("│  ")+line)
	}
	lines = append(lines, stConn.Render("╰─"))
	return strings.Join(lines, "\n")
}

func miniPanel(title string, lines []string, width int) string {
	body := append([]string{stAccent.Render(title)}, lines...)
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width).
		Render(strings.Join(body, "\n"))
}

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
	subtitle := "Evidence-grounded research agent for literature intelligence"
	if width < 76 {
		subtitle = "Evidence-grounded research agent"
	}
	prompt := "Start with a claim, paper, topic, or trend. Type / for commands."
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
	rows := []string{
		lipgloss.JoinHorizontal(
			lipgloss.Top,
			stAccent.Render("Commands"),
			stFaint.Render(" · type to filter · ↑/↓ select · Enter run"),
		),
	}
	lastCategory := ""
	for i, c := range matches {
		if c.category != lastCategory {
			rows = append(rows, stFaint.Render("  "+c.category))
			lastCategory = c.category
		}
		marker := " "
		if c.suggested {
			marker = "•"
		}
		left := fmt.Sprintf("%s %-12s %-18s", marker, c.cmd, clip(c.title, 18))
		midWidth := inner - lipgloss.Width(left) - 16
		if midWidth < 12 {
			midWidth = 12
		}
		row := lipgloss.JoinHorizontal(
			lipgloss.Top,
			stInk.Render(left),
			stFaint.Render(lipgloss.NewStyle().Width(midWidth).Render(clip(c.desc, midWidth))),
			stFaint.Render(" "+clip(c.key, 14)),
		)
		row = lipgloss.NewStyle().Width(inner).Render(row)
		if i == idx {
			rows = append(rows, stSelCmd.Width(inner).Render(row))
			continue
		}
		rows = append(rows, stCmd.Width(inner).Render(row))
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
	body := []string{}
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
		body = append(body, line)
	}
	return panelRow("timeline", "工具调用时间线", "", body)
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
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			body := []string{}
			for i, p := range papers {
				if i >= 4 {
					body = append(body, fmt.Sprintf("+%d 篇更多证据", len(papers)-i))
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
					break
				}
				kw := fmt.Sprintf("%v", row["关键词"])
				trend := fmt.Sprintf("%v", row["趋势判定"])
				momentum := fmt.Sprintf("%v", row["动量分"])
				body = append(body, fmt.Sprintf("[%d] %s · 趋势 %s · 动量 %s", i+1, kw, trend, momentum))
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

func renderRecoveryPanel(s string) string {
	action := recoveryAction(s)
	body := []string{s, action.Message}
	if action.Command != "" {
		body = append(body, "恢复动作: "+action.Command)
	}
	return panelRow("recovery", action.Title, "", body)
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

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		header, footer := 3, 6 // bordered banner = 3 lines; composer/status = 6
		vh := msg.Height - header - footer
		if vh < 3 {
			vh = 3
		}
		if !m.ready {
			m.vp = viewport.New(msg.Width, vh)
			m.loadRecentSessions()
			m.vp.SetContent(renderSplash(msg.Width, m.recentSessions))
			m.ready = true
		} else {
			m.vp.Width, m.vp.Height = msg.Width, vh
			if len(m.blocks) == 0 && m.answer == "" {
				m.loadRecentSessions()
				m.vp.SetContent(renderSplash(msg.Width, m.recentSessions))
			}
		}
		m.ti.Width = msg.Width - 4

	case demoStartMsg:
		v := string(msg)
		m.ti.SetValue("")
		m.appendBlock(stUser.Render("◈ ") + stInk.Render(v))
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
		m.verb = "演示中"
		m.start = time.Now()
		return m, listen(m.sub)

	case nodePulseMsg:
		m.lastMeta = msg.meta
		m.lastStreamKind = msg.kind
		m.nodeSeen = appendUniqueNode(m.nodeSeen, msg.meta.Node)
		m.refresh()
		return m, listen(m.sub)

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
		plain := []string{}
		for _, s := range msg {
			plain = append(plain, "- "+s)
		}
		m.addTimeline(timelineEvent{Kind: "plan", Label: "执行计划", Detail: strings.Join([]string(msg), " / ")})
		m.record("plan", "", strings.Join(plain, "\n"))
		m.appendBlock(renderPlanBlock(msg))
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
		m.addTimeline(timelineEvent{Kind: "tool_call", Tool: msg.name, Label: toolPlainLabel(msg.name), Detail: detail})
		body := []string{}
		if detail != "" {
			body = append(body, detail)
		}
		if notice, ok := permissionNotice(msg.name); ok {
			body = append(body, notice)
			m.record("permission", msg.name, notice)
			m.addTimeline(timelineEvent{Kind: "permission", Tool: msg.name, Label: "权限提示", Detail: notice})
		}
		m.appendBlock(panelRow("action", toolPlainLabel(msg.name), "tool call", body))
		return m, listen(m.sub)

	case toolResultMsg:
		var elapsed time.Duration
		if m.toolStart != nil {
			elapsed = time.Since(m.toolStart[msg.name])
		}
		m.addTimeline(timelineEvent{Kind: "tool_result", Tool: msg.name, Label: toolResultLabel(msg.name, msg.result), Detail: metaDetail(msg.meta), Duration: elapsed})
		m.record("tool_result", msg.name, summarizeToolResultMarkdown(msg.name, msg.result))
		m.appendBlock(renderToolResult(msg.name, msg.result, m.vp.Width, elapsed))
		return m, listen(m.sub)

	case reflectMsg:
		m.answer = ""
		m.record("reflect", "", string(msg))
		m.appendBlock(renderReflectBlock(string(msg)))
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
		m.appendBlock(stError.Render("⏺ ✗ ") + renderRecoveryPanel(string(msg)))
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
		m.appendBlock(stFaint.Render("  命令: /help /tools /demo /sessions /resume N /export /retry /clear /quit · Esc 中断 · Ctrl+C 退出"))
	case "/tools":
		lines := []string{stFaint.Render("  可用工具(LLM 自主调用):")}
		for _, name := range []string{"search_literature", "get_trends", "recommend_papers", "get_paper", "summarize_field", "compare_papers", "export_bibliography", "query_knowledge_graph", "verify_claim"} {
			lines = append(lines, "    "+toolLabel(name))
		}
		m.appendBlock(strings.Join(lines, "\n"))
	case "/doctor":
		m.appendBlock(panelRow("doctor", "System status", "", []string{
			"Backend: " + healthURL(),
			"LLM: " + llmURL(),
			"Sessions: " + sessionDir(),
			"Run `sciscope-tui doctor` for live checks.",
		}))
	case "/demo":
		go playDemo(m.sub)
		return m, listen(m.sub)
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
		parts = append(parts, renderStreamRail(m.timeline, m.lastMeta, m.nodeSeen, m.lastStreamKind, time.Since(m.start), m.vp.Width))
		elapsed := int(time.Since(m.start).Seconds())
		parts = append(parts, m.spin.View()+" "+stAccent.Render(m.verb+"…")+stFaint.Render(fmt.Sprintf("  (%ds · esc 中断)", elapsed)))
	} else if strings.HasPrefix(m.ti.Value(), "/") {
		if menu := m.renderCommandPalette(m.vp.Width); menu != "" {
			parts = append(parts, menu)
		}
	}

	statusText := fmt.Sprintf("  turns %d · /demo · /sessions · /retry · /export · Ctrl+C", len(m.history)/2)
	if m.lastExport != "" {
		statusText += " · saved " + filepath.Base(m.lastExport)
	}
	status := stFaint.Render(statusText)
	parts = append(parts, m.renderComposer(m.vp.Width), status)
	return strings.Join(parts, "\n")
}

func main() {
	opts, err := parseCLIOptions(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		fmt.Fprintln(os.Stderr, helpString())
		os.Exit(2)
	}
	if opts.Help {
		fmt.Println(helpString())
		return
	}
	if opts.Version {
		fmt.Println(versionString(version))
		return
	}
	if opts.Doctor {
		fmt.Println(renderDoctorReport(collectDoctorChecks()))
		return
	}
	if opts.ExportLast {
		content, path, err := exportLastSession(sessionDir())
		if err != nil {
			fmt.Fprintln(os.Stderr, "error:", err)
			os.Exit(1)
		}
		fmt.Fprintln(os.Stderr, "exported:", path)
		fmt.Print(content)
		return
	}
	m := initialModel()
	if opts.Demo {
		m.demo = true
	}
	p := tea.NewProgram(m, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
