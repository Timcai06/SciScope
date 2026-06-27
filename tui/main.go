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

// ---- themes (research-console palettes, à la Claude Code structure) ----
type tuiTheme struct {
	Name     string
	Title    string
	Desc     string
	Accent   lipgloss.Color
	Tool     lipgloss.Color
	Warn     lipgloss.Color
	User     lipgloss.Color
	Error    lipgloss.Color
	Muted    lipgloss.Color
	Faint    lipgloss.Color
	Ink      lipgloss.Color
	Selected lipgloss.Color
}

var (
	themes = map[string]tuiTheme{
		"dark": {
			Name: "dark", Title: "深色研究台", Desc: "默认青色证据流,适合深色终端和演示录屏",
			Accent: "#5fd7d7", Tool: "#87afff", Warn: "#d7af5f", User: "#87d787", Error: "#ff8787",
			Muted: "#808080", Faint: "#5f5f5f", Ink: "#d7d7d7", Selected: "#1c1c1c",
		},
		"paper": {
			Name: "paper", Title: "报告纸面", Desc: "贴近 PDF 报告的青绿品牌色,适合答辩截图",
			Accent: "#16847D", Tool: "#4E6F40", Warn: "#B8872B", User: "#0B4F4A", Error: "#B55A5A",
			Muted: "#667276", Faint: "#9AA8A6", Ink: "#1C2326", Selected: "#F7FBFA",
		},
		"light": {
			Name: "light", Title: "浅色终端", Desc: "提高浅色背景可读性,减少低对比灰字",
			Accent: "#006D77", Tool: "#255C99", Warn: "#8A5A00", User: "#2F6F3E", Error: "#A23B3B",
			Muted: "#5D666A", Faint: "#8A9498", Ink: "#1B1F22", Selected: "#F4F7F7",
		},
		"contrast": {
			Name: "contrast", Title: "高对比", Desc: "更亮的强调色和警告色,适合投影或低质量屏幕",
			Accent: "#00FFFF", Tool: "#5FA8FF", Warn: "#FFD166", User: "#7CFF6B", Error: "#FF5C8A",
			Muted: "#B8B8B8", Faint: "#777777", Ink: "#FFFFFF", Selected: "#000000",
		},
	}
	themeOrder   = []string{"dark", "paper", "light", "contrast"}
	currentTheme = "dark"

	cAccent lipgloss.Color
	cTool   lipgloss.Color
	cWarn   lipgloss.Color
	cUser   lipgloss.Color
	cError  lipgloss.Color
	cMuted  lipgloss.Color
	cFaint  lipgloss.Color
	cInk    lipgloss.Color

	stAccent lipgloss.Style
	stBullet lipgloss.Style
	stConn   lipgloss.Style
	stTool   lipgloss.Style
	stWarn   lipgloss.Style
	stError  lipgloss.Style
	stUser   lipgloss.Style
	stMuted  lipgloss.Style
	stFaint  lipgloss.Style
	stInk    lipgloss.Style
	stSelCmd lipgloss.Style
	stCmd    lipgloss.Style
)

func init() {
	if name := strings.TrimSpace(os.Getenv("SCISCOPE_TUI_THEME")); name != "" {
		applyTheme(name)
		return
	}
	applyTheme(currentTheme)
}

func applyTheme(name string) bool {
	name = strings.ToLower(strings.TrimSpace(name))
	theme, ok := themes[name]
	if !ok {
		return false
	}
	currentTheme = name
	cAccent = theme.Accent
	cTool = theme.Tool
	cWarn = theme.Warn
	cUser = theme.User
	cError = theme.Error
	cMuted = theme.Muted
	cFaint = theme.Faint
	cInk = theme.Ink
	stAccent = lipgloss.NewStyle().Foreground(cAccent).Bold(true)
	stBullet = lipgloss.NewStyle().Foreground(cAccent).Bold(true) // ⏺
	stConn = lipgloss.NewStyle().Foreground(cFaint)               // ⎿
	stTool = lipgloss.NewStyle().Foreground(cTool)
	stWarn = lipgloss.NewStyle().Foreground(cWarn)
	stError = lipgloss.NewStyle().Foreground(cError)
	stUser = lipgloss.NewStyle().Foreground(cUser).Bold(true)
	stMuted = lipgloss.NewStyle().Foreground(cMuted)
	stFaint = lipgloss.NewStyle().Foreground(cFaint)
	stInk = lipgloss.NewStyle().Foreground(cInk)
	stSelCmd = lipgloss.NewStyle().Background(cAccent).Foreground(theme.Selected).Bold(true)
	stCmd = lipgloss.NewStyle().Foreground(cMuted)
	return true
}

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

type slashCommandKind string

const (
	commandLocal  slashCommandKind = "local"
	commandPrompt slashCommandKind = "prompt"
	commandUI     slashCommandKind = "ui"
)

type slashExecutor func(model, []string) (model, tea.Cmd)

type slashCmd struct {
	cmd       string
	title     string
	desc      string
	category  string
	key       string
	kind      slashCommandKind
	submenu   string
	suggested bool
	run       slashExecutor
}

var slashCmds = []slashCmd{
	{cmd: "/demo", title: "黄金演示", desc: "播放可验证证据流", category: "常用", key: "demo", kind: commandLocal, suggested: true},
	{cmd: "/verify", title: "论断核查", desc: "把论断展开为证据核查任务", category: "常用", key: "verify <claim>", kind: commandPrompt, suggested: true},
	{cmd: "/review", title: "文献综述", desc: "把主题展开为综述/研究现状任务", category: "常用", key: "review <topic>", kind: commandPrompt, suggested: true},
	{cmd: "/trend", title: "趋势分析", desc: "把主题展开为趋势预测任务", category: "常用", key: "trend <topic>", kind: commandPrompt, suggested: true},
	{cmd: "/recommend", title: "论文推荐", desc: "把主题或种子论文展开为推荐任务", category: "常用", key: "recommend <topic|paper_id>", kind: commandPrompt, suggested: true},
	{cmd: "/doctor", title: "状态体检", desc: "检查后端、LLM、会话与图谱", category: "常用", key: "doctor", kind: commandUI, submenu: "doctor", suggested: true},
	{cmd: "/retry", title: "重试上一问", desc: "同一 LangGraph 会话线程恢复上一问", category: "常用", key: "retry", kind: commandLocal, suggested: true},
	{cmd: "/export", title: "导出报告", desc: "导出 Markdown 会话与证据", category: "常用", key: "export", kind: commandLocal, suggested: true},
	{cmd: "/sessions", title: "最近会话", desc: "列出最近研究会话", category: "会话", key: "sessions", kind: commandUI, submenu: "resume"},
	{cmd: "/resume", title: "恢复会话", desc: "恢复会话: /resume 1", category: "会话", key: "resume N", kind: commandUI, submenu: "resume"},
	{cmd: "/timeline", title: "执行时间线", desc: "查看本轮 LangGraph 与工具轨迹", category: "证据", key: "timeline", kind: commandLocal},
	{cmd: "/tools", title: "智能体工具", desc: "列出 LLM 可自主调用的科研工具", category: "证据", key: "tools", kind: commandUI, submenu: "tools"},
	{cmd: "/theme", title: "视觉主题", desc: "查看或切换 TUI 主题: /theme paper", category: "系统", key: "theme", kind: commandUI, submenu: "theme"},
	{cmd: "/help", title: "帮助", desc: "显示命令与快捷键", category: "系统", key: "?", kind: commandLocal},
	{cmd: "/clear", title: "清空视图", desc: "清空当前对话视图", category: "系统", key: "clear", kind: commandUI, submenu: "clear"},
	{cmd: "/quit", title: "退出", desc: "退出 SciScope TUI", category: "系统", key: "ctrl+c", kind: commandUI, submenu: "quit"},
}

var slashExecutors = map[string]slashExecutor{
	"/clear":     runClearCommand,
	"/demo":      runDemoCommand,
	"/doctor":    runDoctorCommand,
	"/export":    runExportCommand,
	"/help":      runHelpCommand,
	"/quit":      runQuitCommand,
	"/recommend": runRecommendCommand,
	"/resume":    runResumeCommand,
	"/review":    runReviewCommand,
	"/retry":     runRetryCommand,
	"/sessions":  runSessionsCommand,
	"/theme":     runThemeCommand,
	"/timeline":  runTimelineCommand,
	"/tools":     runToolsCommand,
	"/trend":     runTrendCommand,
	"/verify":    runVerifyCommand,
}
var slashRegistry = buildSlashRegistry(slashCmds)

func buildSlashRegistry(commands []slashCmd) map[string]slashCmd {
	registry := map[string]slashCmd{}
	for _, command := range commands {
		command.run = slashExecutors[command.cmd]
		registry[command.cmd] = command
	}
	return registry
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
	Phase     string `json:"phase"`
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
	Severity  string
	Inspect   string
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
	Phase    string
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
	return strings.TrimRight(backendURL(), "/") + "/api/ingest/status"
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
func sanitizeHistory(history []turn) []turn {
	clean := make([]turn, 0, len(history))
	for _, item := range history {
		role := strings.TrimSpace(item.Role)
		content := strings.TrimSpace(item.Content)
		if content == "" {
			continue
		}
		if role != "user" && role != "assistant" {
			continue
		}
		clean = append(clean, turn{Role: role, Content: content})
	}
	return clean
}

func agentRequestBody(q string, history []turn, sessionID string, retry bool) ([]byte, error) {
	return json.Marshal(map[string]any{
		"question":   strings.TrimSpace(q),
		"history":    sanitizeHistory(history),
		"session_id": strings.TrimSpace(sessionID),
		"retry":      retry,
	})
}

func stream(ctx context.Context, backend, q string, history []turn, sessionID string, retry bool, sub chan tea.Msg) {
	body, _ := agentRequestBody(q, history, sessionID, retry)
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
	livePlan       []string
	liveReflect    string
	sub            chan tea.Msg
	cancel         context.CancelFunc
	menuIdx        int
	submenu        string
	submenuIdx     int
	ready          bool
	demo           bool
}

func initialModel() model {
	ti := textinput.New()
	ti.Placeholder = "输入研究问题 / 待核查论断,或输入 / 调用命令"
	ti.Prompt = stAccent.Render("❯ ")
	ti.Focus()
	ti.CharLimit = 2000

	sp := spinner.New()
	sp.Spinner = spinner.Spinner{
		Frames: []string{"✻", "✢", "✳", "∗", "✦", "✶"},
		FPS:    time.Second / 8,
	}
	sp.Style = stAccent
	m := model{ti: ti, spin: sp, sub: make(chan tea.Msg, 64), demo: demoMode(), sessionID: newSessionID()}
	m.syncThemeStyles()
	return m
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

func (m *model) syncThemeStyles() {
	m.ti.Prompt = stAccent.Render("❯ ")
	m.spin.Style = stAccent
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
	if meta.Phase != "" {
		parts = append(parts, "阶段 "+meta.Phase)
	} else if meta.Node != "" {
		parts = append(parts, "阶段 "+nodeLabel(meta.Node))
	}
	if meta.ElapsedMS > 0 {
		parts = append(parts, fmt.Sprintf("%dms", meta.ElapsedMS))
	}
	if meta.Retry {
		parts = append(parts, "重试")
	}
	return strings.Join(parts, " · ")
}

func metaEmpty(meta eventMeta) bool {
	return meta.Runtime == "" && meta.Node == "" && meta.Phase == "" && meta.SessionID == "" && meta.ElapsedMS == 0 && !meta.Retry
}

func nodeLabel(node string) string {
	switch node {
	case "prepare":
		return "理解问题"
	case "plan":
		return "制定研究计划"
	case "llm_step":
		return "推理与检索决策"
	case "execute_tools":
		return "证据检索"
	case "reflect":
		return "自检修正"
	case "force_synthesis":
		return "综合回答"
	default:
		if node == "" {
			return "等待事件"
		}
		return node
	}
}

func eventPhase(ev timelineEvent) string {
	if strings.TrimSpace(ev.Phase) != "" {
		return strings.TrimSpace(ev.Phase)
	}
	switch ev.Kind {
	case "plan":
		return "制定研究计划"
	case "tool_call", "tool_result", "permission":
		return "证据检索"
	case "reflect":
		return "自检修正"
	case "final":
		return "综合回答"
	case "error":
		return "错误恢复"
	default:
		return "执行过程"
	}
}

func metaPhase(meta eventMeta) string {
	if strings.TrimSpace(meta.Phase) != "" {
		return strings.TrimSpace(meta.Phase)
	}
	return nodeLabel(meta.Node)
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

func renderWorkflowStatus(meta eventMeta, nodes []string, kind string, elapsed time.Duration, width int) string {
	if width < 56 {
		width = 56
	}
	current := metaPhase(meta)
	if current == "等待事件" && len(nodes) > 0 {
		current = nodeLabel(nodes[len(nodes)-1])
	}
	phases := []string{"理解问题", "制定研究计划", "推理与检索决策", "证据检索", "自检修正", "综合回答"}
	active := -1
	for i, phase := range phases {
		if phase == current {
			active = i
			break
		}
	}
	steps := []string{}
	for i, phase := range phases {
		mark := "○"
		style := stFaint
		if active >= 0 && i < active {
			mark = "●"
		}
		if i == active {
			mark = "◆"
			style = stAccent
		}
		steps = append(steps, style.Render(mark+" "+phase))
	}
	phaseLines := []string{strings.Join(steps, stFaint.Render("  →  "))}
	if width < 96 {
		phaseLines = []string{
			strings.Join(steps[:3], stFaint.Render("  →  ")),
			strings.Join(steps[3:], stFaint.Render("  →  ")),
		}
	}
	session := meta.SessionID
	if session == "" {
		session = "local session"
	}
	status := []string{
		stAccent.Render("当前阶段"),
		stInk.Render(current),
		stFaint.Render(streamKindLabel(kind)),
		stFaint.Render(fmt.Sprintf("%.0fs", elapsed.Seconds())),
	}
	if meta.Retry {
		status = append(status, stWarn.Render("重试"))
	}
	if meta.ElapsedMS > 0 {
		status = append(status, stFaint.Render(fmt.Sprintf("%dms", meta.ElapsedMS)))
	}
	body := []string{
		strings.Join(status, stFaint.Render(" · ")),
	}
	body = append(body, phaseLines...)
	body = append(body, stFaint.Render("线程 "+clip(session, 42)))
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(body, "\n"))
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
	// Follow new content only when already pinned to the bottom; if the user has
	// scrolled up to read, keep their position instead of yanking them down.
	atBottom := m.vp.AtBottom()
	m.vp.SetContent(content)
	if atBottom {
		m.vp.GotoBottom()
	}
}

func renderStreamRail(events []timelineEvent, meta eventMeta, nodes []string, kind string, elapsed time.Duration, width int) string {
	if width < 48 {
		width = 48
	}
	runtime := meta.Runtime
	if runtime == "" {
		runtime = "langgraph"
	}
	node := meta.Phase
	if node == "" {
		node = nodeLabel(meta.Node)
	}
	if meta.Node == "" && meta.Phase == "" && len(nodes) > 0 {
		node = nodeLabel(nodes[len(nodes)-1])
	}
	session := meta.SessionID
	if session == "" {
		session = "local session"
	}
	status := []string{
		stAccent.Render(runtime),
		stFaint.Render("阶段 ") + stInk.Render(node),
		stFaint.Render(streamKindLabel(kind)),
		stFaint.Render(fmt.Sprintf("%.0fs", elapsed.Seconds())),
	}
	if meta.Retry {
		status = append(status, stWarn.Render("重试"))
	}
	if meta.ElapsedMS > 0 {
		status = append(status, stFaint.Render(fmt.Sprintf("%dms", meta.ElapsedMS)))
	}

	body := []string{
		strings.Join(status, stFaint.Render(" · ")),
		stFaint.Render("线程 " + clip(session, 38)),
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
		body = append(body, stFaint.Render("图谱  ")+stInk.Render(strings.Join(labels, stFaint.Render(" → "))))
	}
	if len(events) > 0 {
		body = append(body, stFaint.Render("最新"))
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

func renderThinkingShelf(plan []string, reflect string, width int) string {
	if len(plan) == 0 && strings.TrimSpace(reflect) == "" {
		return ""
	}
	if width < 48 {
		width = 48
	}
	body := []string{}
	if len(plan) > 0 {
		body = append(body, stFaint.Render("研究计划"))
		for i, step := range plan {
			if i >= 4 {
				break
			}
			body = append(body, fmt.Sprintf("  [%d] %s", i+1, clip(step, 86)))
		}
	}
	if strings.TrimSpace(reflect) != "" {
		if len(body) > 0 {
			body = append(body, "")
		}
		body = append(body, stFaint.Render("自检修正"))
		body = append(body, "  "+clip(reflect, 110))
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
	// Render the real textinput widget so the cursor is drawn inside the
	// composer box (rendering Value() as static text left the hardware cursor
	// stranded at the bottom of the screen).
	inputLine := m.ti.View()
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cAccent).
		Padding(0, 1).
		Width(width - 2).
		Render(inputLine)
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

// clipWidth truncates by terminal display width (CJK runes count as 2), so
// columns stay aligned regardless of Chinese/ASCII mix. lipgloss.Width measures
// display cells.
func clipWidth(s string, w int) string {
	s = strings.TrimSpace(strings.ReplaceAll(s, "\n", " "))
	if lipgloss.Width(s) <= w {
		return s
	}
	r := []rune(s)
	for len(r) > 0 && lipgloss.Width(string(r))+1 > w {
		r = r[:len(r)-1]
	}
	return string(r) + "…"
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
	cursorW, cmdW, titleW, keyW := 3, 12, 14, 12
	descW := inner - cursorW - cmdW - titleW - keyW
	if descW < 10 {
		descW = 10
	}
	rows := []string{
		stAccent.Render("命令启动器") + stFaint.Render("  · ↑/↓ 选择 · Enter 执行 · Tab 补全 · Esc 关闭"),
	}
	for i, c := range matches {
		marker := "  "
		if i == idx {
			marker = "▶ "
		}
		cols := lipgloss.JoinHorizontal(
			lipgloss.Top,
			lipgloss.NewStyle().Width(cursorW).Render(marker),
			lipgloss.NewStyle().Width(cmdW).Render(c.cmd),
			lipgloss.NewStyle().Width(titleW).Render(clipWidth(c.title, titleW-1)),
			lipgloss.NewStyle().Width(descW).Render(clipWidth(c.desc, descW-1)),
			lipgloss.NewStyle().Width(keyW).Render(clipWidth(c.key, keyW-1)),
		)
		if i == idx {
			rows = append(rows, stSelCmd.Width(inner).Render(cols))
		} else {
			rows = append(rows, stCmd.Width(inner).Render(cols))
		}
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
		m.livePlan = nil
		m.liveReflect = ""
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

	case tea.MouseMsg:
		// Mouse wheel scrolls the transcript viewport.
		m.vp, cmd = m.vp.Update(msg)
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
						m.ti.SetValue(ms[m.menuIdx%len(ms)].cmd)
					}
					return m, nil
				}
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
				return m, nil
			}
			if strings.HasPrefix(v, "/") {
				if ms := filterCmds(m.ti.Value()); len(ms) > 0 && m.menuIdx < len(ms) && !strings.Contains(v, " ") {
					v = ms[m.menuIdx].cmd
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
		m.appendBlock(strings.Join(planLines, "\n"))
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
		m.appendBlock(callLine)
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
		// Render the rich evidence/verify/trend card by default (not just in /demo
		// or /timeline) so the evidence chain is always visible inline.
		m.appendBlock(renderToolResult(msg.name, msg.result, m.vp.Width, elapsed))
		return m, listen(m.sub)

	case reflectMsg:
		m.answer = ""
		m.record("reflect", "", string(msg))
		m.liveReflect = string(msg)
		m.addTimeline(timelineEvent{Kind: "reflect", Phase: "自检修正", Label: "自检修正", Detail: string(msg)})
		m.appendBlock(stBullet.Render("⏺ ") + stWarn.Render("自检修正") + "\n" + stConn.Render("  ⎿ ") + stFaint.Render(string(msg)))
		return m, listen(m.sub)

	case textMsg:
		m.answer += string(msg)
		m.refresh()
		return m, listen(m.sub)

	case finalMsg:
		if m.answer == "" {
			m.answer = string(msg)
		}
		m.refresh()
		return m, listen(m.sub)

	case errMsg:
		errText := friendlyError(string(msg))
		m.record("error", "", errText)
		action := recoveryAction(string(msg))
		m.addTimeline(timelineEvent{Kind: "error", Phase: "错误恢复", Label: action.Title, Detail: action.Message})
		m.appendBlock(stError.Render("⏺ ✗ ") + renderRecoveryPanel(string(msg)))
		return m, listen(m.sub)

	case doneMsg:
		if m.answer != "" {
			ans := m.answer
			m.answering = false
			m.addTimeline(timelineEvent{Kind: "final", Phase: "综合回答", Label: "回答完成"})
			if body := timelineMarkdownBody(m.timeline); body != "" {
				m.record("timeline", "", body)
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
		m.livePlan = nil
		m.liveReflect = ""
		m.cancel = nil
		m.refresh()
		return m, nil
	}

	m.ti, cmd = m.ti.Update(msg)
	return m, cmd
}

// renderAnswer renders the finished answer as a chat message. Tool traces are
// kept in /timeline so the main conversation stays readable.
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
	body = styleAnswerBody(body)
	header := stBullet.Render("⏺ ") + stAccent.Render("研究结论")
	out := header + "\n" + body
	if len(m.used) > 0 {
		seen := map[string]bool{}
		labels := []string{}
		for _, n := range m.used {
			if !seen[n] {
				seen[n] = true
				labels = append(labels, toolLabel(n))
			}
		}
		out += "\n" + stFaint.Render("  证据工具: "+strings.Join(labels, "  ")+" · /timeline 查看过程")
	}
	return out
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
		return indent + stAccent.Render(label) + stInk.Render("  "+text)
	}
	if strings.Contains(raw, "[") && strings.Contains(raw, "]") {
		return indent + stTool.Render(raw)
	}
	if hasMetricToken(raw) {
		return indent + stAccent.Render(raw)
	}
	if hasCautionToken(raw) {
		return indent + stWarn.Render(raw)
	}
	return line
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

type submenuItem struct {
	label   string
	desc    string
	command string
}

func commandSubmenu(cmd string) string {
	fields := strings.Fields(cmd)
	if len(fields) == 0 {
		return ""
	}
	if command, ok := slashRegistry[fields[0]]; ok {
		return command.submenu
	}
	return ""
}

type toolInfo struct {
	name string
	desc string
	when string
}

func toolCatalog() []toolInfo {
	return []toolInfo{
		{"search_literature", "混合检索论文证据", "文献问答、查新、证据补充"},
		{"get_trends", "查看关键词趋势与生命周期", "趋势预测、热点监测"},
		{"recommend_papers", "按种子论文推荐相似研究", "延伸阅读、相关工作"},
		{"get_paper", "读取单篇论文详情", "已知 paper_id 后深读"},
		{"summarize_field", "生成领域综述证据", "主题综述、背景整理"},
		{"compare_papers", "对比两篇论文", "方法差异、贡献比较"},
		{"export_bibliography", "导出引用文本", "写报告、整理参考文献"},
		{"query_knowledge_graph", "查询作者/关键词/主题图谱", "合作网络、主题关系"},
		{"verify_claim", "核查论断并返回证据", "事实核查、降低幻觉"},
	}
}

func toolInfoByName(name string) (toolInfo, bool) {
	for _, tool := range toolCatalog() {
		if tool.name == name || toolPlainLabel(tool.name) == name {
			return tool, true
		}
	}
	return toolInfo{}, false
}

func submenuTitle(name string) string {
	switch name {
	case "theme":
		return "选择主题"
	case "resume":
		return "恢复会话"
	case "tools":
		return "选择工具"
	case "doctor":
		return "查看检查项"
	case "clear":
		return "确认清空"
	case "quit":
		return "确认退出"
	default:
		return "二级选择"
	}
}

func (m model) submenuItems() []submenuItem {
	switch m.submenu {
	case "theme":
		items := []submenuItem{}
		for _, name := range themeOrder {
			theme := themes[name]
			items = append(items, submenuItem{label: theme.Name, desc: theme.Title + " · " + theme.Desc, command: "/theme " + theme.Name})
		}
		return items
	case "resume":
		items := []submenuItem{}
		for _, session := range m.recentSessions {
			question := session.LastQuestion
			if question == "" {
				question = strings.TrimSuffix(session.Name, filepath.Ext(session.Name))
			}
			items = append(items, submenuItem{
				label:   fmt.Sprintf("%d", session.Index),
				desc:    clip(question, 58) + " · " + session.ModTime.Format("01-02 15:04"),
				command: fmt.Sprintf("/resume %d", session.Index),
			})
		}
		return items
	case "tools":
		items := []submenuItem{}
		for _, tool := range toolCatalog() {
			items = append(items, submenuItem{label: toolPlainLabel(tool.name), desc: tool.desc + " · " + tool.when, command: "/tools " + tool.name})
		}
		return items
	case "doctor":
		items := []submenuItem{}
		for _, check := range collectDoctorChecks() {
			items = append(items, submenuItem{label: check.Name, desc: check.Status + " · " + check.Detail, command: "/doctor " + check.Name})
		}
		return items
	case "clear":
		return []submenuItem{{label: "取消", desc: "保留当前对话", command: "/clear no"}, {label: "清空", desc: "清空当前视图、历史和时间线", command: "/clear yes"}}
	case "quit":
		return []submenuItem{{label: "取消", desc: "继续当前会话", command: "/quit no"}, {label: "退出", desc: "关闭 SciScope TUI", command: "/quit yes"}}
	default:
		return nil
	}
}

func (m model) renderSubmenuPalette(width int) string {
	if width < 48 {
		width = 48
	}
	items := m.submenuItems()
	if len(items) == 0 {
		return panelRow("launcher", submenuTitle(m.submenu), "empty", []string{"暂无可选项。Esc 返回。"})
	}
	inner := width - 6
	if inner < 38 {
		inner = 38
	}
	idx := m.submenuIdx % len(items)
	labelW := 14
	descW := inner - 3 - labelW - 16
	if descW < 16 {
		descW = 16
	}
	title := submenuTitle(m.submenu)
	rows := []string{stAccent.Render(title) + stFaint.Render("  · ↑/↓ 选择 · Enter 执行 · Esc 返回")}
	for i, item := range items {
		marker := "  "
		if i == idx {
			marker = "▶ "
		}
		cols := lipgloss.JoinHorizontal(
			lipgloss.Top,
			lipgloss.NewStyle().Width(3).Render(marker),
			lipgloss.NewStyle().Width(labelW).Render(item.label),
			lipgloss.NewStyle().Width(descW).Render(clipWidth(item.desc, descW-1)),
			lipgloss.NewStyle().Width(16).Render(clipWidth(item.command, 15)),
		)
		if i == idx {
			rows = append(rows, stSelCmd.Width(inner).Render(cols))
		} else {
			rows = append(rows, stCmd.Width(inner).Render(cols))
		}
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(rows, "\n"))
}

func (m *model) openSubmenu(name string) {
	m.submenu = name
	m.submenuIdx = 0
	switch name {
	case "theme":
		m.ti.SetValue("/theme ")
	case "resume":
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err == nil {
			m.recentSessions = sessions
		}
		m.ti.SetValue("/resume ")
	case "tools":
		m.ti.SetValue("/tools ")
	case "doctor":
		m.ti.SetValue("/doctor ")
	case "clear":
		m.ti.SetValue("/clear ")
	case "quit":
		m.ti.SetValue("/quit ")
	}
}

func renderSlashHelpBlock() string {
	groups := map[string][]slashCmd{}
	for _, cmd := range slashCmds {
		groups[cmd.category] = append(groups[cmd.category], cmd)
	}
	order := []string{"常用", "会话", "证据", "系统"}
	body := []string{"使用 / 打开命令启动器; ↑/↓ 选择, Enter 执行, Tab 补全。"}
	for _, group := range order {
		cmds := groups[group]
		if len(cmds) == 0 {
			continue
		}
		body = append(body, "")
		body = append(body, stAccent.Render(group))
		for _, cmd := range cmds {
			body = append(body, fmt.Sprintf("  %-10s %s", cmd.cmd, cmd.desc))
		}
	}
	return panelRow("launcher", "命令启动器", "slash", body)
}

func renderToolsBlock() string {
	type toolInfo struct {
		name string
		desc string
	}
	tools := []toolInfo{
		{"search_literature", "混合检索论文证据"},
		{"get_trends", "查看关键词趋势与生命周期"},
		{"recommend_papers", "按种子论文推荐相似研究"},
		{"get_paper", "读取单篇论文详情"},
		{"summarize_field", "生成领域综述证据"},
		{"compare_papers", "对比两篇论文"},
		{"export_bibliography", "导出引用文本"},
		{"query_knowledge_graph", "查询作者/关键词/主题图谱"},
		{"verify_claim", "核查论断并返回证据"},
	}
	body := []string{"这些工具由 LLM 按问题自主调用; /timeline 查看每次调用过程。"}
	for _, tool := range tools {
		body = append(body, fmt.Sprintf("  %-18s %s", toolPlainLabel(tool.name), tool.desc))
	}
	return panelRow("tools", "智能体工具", "read-only", body)
}

func renderInlineDoctorBlock() string {
	body := []string{}
	for _, check := range collectDoctorChecks() {
		line := fmt.Sprintf("%s  %s", check.Status, check.Name)
		if check.Detail != "" {
			line += " · " + check.Detail
		}
		body = append(body, line)
	}
	return panelRow("doctor", "系统状态", "live", body)
}

func runQuitCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) >= 1 && args[0] == "yes" {
		return m, tea.Quit
	}
	m.appendBlock(stFaint.Render("  已取消退出。"))
	return m, nil
}

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
	next, cmd := command.run(m, fields[1:])
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
		parts = append(parts, m.spin.View()+" "+stAccent.Render(m.verb+"…")+stFaint.Render(fmt.Sprintf("  (%ds · esc 中断)", elapsed)))
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
	p := tea.NewProgram(m, tea.WithAltScreen(), tea.WithMouseCellMotion())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
