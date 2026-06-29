// SciScope terminal client — a Bubble Tea (Charm) TUI that consumes the agent's
// SSE event stream (/api/agent/stream). The Python agent core is untouched: this
// is purely a presentation client, styled after Claude Code's visual grammar
// (⏺ action bullets, ⎿ tool-result connectors, an animated verb spinner).
//
// Run:  sciscope-tui    (release binary connects to the hosted backend by default)
// Dev:  SCISCOPE_BACKEND=http://127.0.0.1:8000 make tui
package main

import (
	"bytes"
	"context"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
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
var defaultHostedBackendURL string

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

const (
	streamRefreshInterval = 90 * time.Millisecond
	spinnerFrameInterval  = 250 * time.Millisecond
	terminalRenderFPS     = 30
)

var (
	paperIDPattern  = regexp.MustCompile(`\b(?:W\d{6,}|[a-zA-Z]+:\S+|\d{4}\.\d{4,5})\b`)
	yearPattern     = regexp.MustCompile(`\b20(?:1[9]|2[0-9])\b`)
	metricPattern   = regexp.MustCompile(`(?:\b\d+(?:\.\d+)?%|\b0\.\d{2,4}\b|\b\d+(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d+\b)`)
	commandPattern  = regexp.MustCompile(`/(?:timeline|retry|doctor|export|demo|tools|theme|sessions|resume|verify|trend|recommend|review)\b`)
	toolNamePattern = regexp.MustCompile(`\b(?:verify_claim|search_literature|get_trends|recommend_papers|get_paper|summarize_field|compare_papers|query_knowledge_graph|export_bibliography)\b`)
	verdictPattern  = regexp.MustCompile(`强支持|弱支持|不支持|支持等级|论断核查|证据卡|趋势卡|相似度|最高接地相似度`)
	cautionPattern  = regexp.MustCompile(`风险|限制|边界|注意|谨慎|可能|取决于|不应|不能|然而|但是|仍需|不足`)
)

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

func backendURL() string {
	if v := os.Getenv("SCISCOPE_BACKEND"); v != "" {
		return v
	}
	return hostedBackendURL()
}

func hostedBackendURL() string {
	// Runtime override for installed clients. Release CI uses
	// SCISCOPE_HOSTED_BACKEND_URL only to inject defaultHostedBackendURL at build
	// time; the running binary reads SCISCOPE_HOSTED_BACKEND when a user needs to
	// test a different hosted service without rebuilding.
	if v := strings.TrimSpace(os.Getenv("SCISCOPE_HOSTED_BACKEND")); v != "" {
		return strings.TrimRight(v, "/")
	}
	if v := strings.TrimSpace(defaultHostedBackendURL); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "http://127.0.0.1:8000"
}

func backendMode(rawURL string) string {
	normalized := strings.ToLower(strings.TrimSpace(rawURL))
	if u, err := url.Parse(normalized); err == nil {
		switch u.Hostname() {
		case "localhost", "127.0.0.1", "::1":
			return "local"
		case "":
		default:
			return "hosted"
		}
	}
	switch {
	case normalized == "localhost", strings.HasPrefix(normalized, "localhost:"):
		return "local"
	case normalized == "127.0.0.1", strings.HasPrefix(normalized, "127.0.0.1:"):
		return "local"
	case normalized == "::1", strings.HasPrefix(normalized, "[::1]:"):
		return "local"
	}
	return "hosted"
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
		"  SCISCOPE_HOSTED_BACKEND       hosted backend URL for release defaults",
		"  SCISCOPE_BACKEND              developer override for local/custom backend",
		"  SCISCOPE_TUI_DEMO_DELAY_MS    demo playback delay",
	}, "\n")
}

type model struct {
	ti                          textinput.Model
	vp                          viewport.Model
	spin                        spinner.Model
	blocks                      []string // finalized conversation lines
	blockItems                  []conversationBlock
	blocksVersion               int
	transcriptCache             string
	transcriptCacheWidth        int
	transcriptCacheBlockVersion int
	transcriptCacheVersion      int
	viewportContent             string
	viewportContentVersion      int
	answer                      string // current streaming answer
	answering                   bool
	verb                        string
	tick                        int
	start                       time.Time // when the current turn began (for the elapsed timer)
	used                        []string  // tools called this turn (for the answer footer)
	toolStart                   map[string]time.Time
	history                     []turn
	transcript                  []transcriptEvent
	timeline                    []timelineEvent
	recentSessions              []sessionFile
	lastExport                  string
	lastQuestion                string
	sessionID                   string
	lastMeta                    eventMeta
	lastStreamKind              string
	nodeSeen                    []string
	livePlan                    []string
	liveReflect                 string
	lastRefresh                 time.Time
	refreshPending              bool
	sub                         chan tea.Msg
	cancel                      context.CancelFunc
	menuIdx                     int
	submenu                     string
	submenuIdx                  int
	ready                       bool
	demo                        bool
}

type conversationBlock struct {
	Kind          string
	Raw           string
	Tools         []string
	Retry         bool
	Rendered      string
	RenderWidth   int
	RenderVersion int
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
		FPS:    spinnerFrameInterval,
	}
	sp.Style = stAccent
	m := model{ti: ti, spin: sp, sub: make(chan tea.Msg, 64), demo: demoMode(), sessionID: newSessionID()}
	m.syncThemeStyles()
	return m
}

func newTranscriptViewport(width, height int) viewport.Model {
	vp := viewport.New(width, height)
	// macOS trackpads emit many small wheel events; a larger delta keeps the
	// transcript responsive while streamed ANSI content is being redrawn.
	vp.MouseWheelDelta = 8
	return vp
}

func isVerticalWheel(msg tea.MouseMsg) bool {
	if msg.Action != tea.MouseActionPress {
		return false
	}
	return msg.Button == tea.MouseButtonWheelUp || msg.Button == tea.MouseButtonWheelDown
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
	m.blockItems = append(m.blockItems, conversationBlock{Kind: "message", Raw: s})
	m.blocksVersion++
	m.refresh()
}

func (m *model) appendUserMessage(text string, retry bool) {
	m.blocks = append(m.blocks, text)
	m.blockItems = append(m.blockItems, conversationBlock{Kind: "user", Raw: text, Retry: retry})
	m.blocksVersion++
	m.refresh()
}

func (m *model) appendAnswerMessage(text string, tools []string) {
	copiedTools := append([]string(nil), tools...)
	m.blocks = append(m.blocks, text)
	m.blockItems = append(m.blockItems, conversationBlock{Kind: "assistant", Raw: text, Tools: copiedTools})
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
	m.blockItems = make([]conversationBlock, len(m.blocks))
	for i, raw := range m.blocks {
		m.blockItems[i] = conversationBlock{Kind: "message", Raw: raw}
	}
	m.blocksVersion++
}

func (m *model) invalidateRenderCache() {
	for i := range m.blockItems {
		m.blockItems[i].Rendered = ""
		m.blockItems[i].RenderWidth = 0
	}
	m.transcriptCache = ""
	m.transcriptCacheWidth = 0
	m.transcriptCacheBlockVersion = -1
	m.blocksVersion++
}

func (m *model) renderBlocksContent(width int) string {
	m.syncBlockItems()
	if len(m.blockItems) == 0 {
		return ""
	}
	parts := make([]string, 0, len(m.blockItems))
	for i := range m.blockItems {
		block := &m.blockItems[i]
		if block.Rendered == "" || block.RenderWidth != width {
			block.Rendered = renderConversationBlock(*block, width)
			block.RenderWidth = width
			block.RenderVersion++
		}
		parts = append(parts, block.Rendered)
	}
	return strings.Join(parts, "\n")
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

func kaomojiForState(kind string, meta eventMeta, answering bool) string {
	if !answering {
		return "(´▽`)"
	}
	if kind == "error" {
		return "(；￣Д￣)"
	}
	if meta.Retry {
		return "(ง •̀_•́)ง"
	}
	switch kind {
	case "tool_call", "tool_result":
		switch meta.Node {
		case "execute_tools":
			return "(つ•̀ω•́)つ"
		default:
			return "(｀・ω・´)"
		}
	case "reflect":
		return "( ･᷄ὢ･᷅ )"
	case "final":
		return "(๑•̀ㅂ•́)و✧"
	case "plan":
		return "(。-`ω´-)"
	case "text":
		return "( ..)φ"
	default:
		return "(。-`ω´-)"
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
		stAccent.Render(kaomojiForState(kind, meta, true)),
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
	m.refreshTranscript(false)
}

func (m *model) refreshWithLiveAnswer() {
	m.refreshTranscript(true)
}

func (m *model) refreshTranscript(includeLiveAnswer bool) {
	content := m.renderTranscriptContent(m.vp.Width)
	if includeLiveAnswer && m.answering && m.answer != "" {
		// Live answer with a streaming cursor block, for a "being written" feel.
		content += "\n" + stBullet.Render("⏺ ") + stInk.Render(m.answer) + stAccent.Render("▌")
	}
	if strings.TrimSpace(content) == "" && m.vp.Width > 0 {
		m.loadRecentSessions()
		content = renderSplash(m.vp.Width, m.recentSessions)
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
	hints := stFaint.Render("Enter 发送 · Esc 中断/关闭 · / 命令")
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cAccent).
		Padding(0, 1).
		Width(width - 2).
		Render(inputLine + "\n" + hints)
}

func renderLiveAnswerPreview(answer string, width int) string {
	answer = strings.Trim(answer, "\n")
	if answer == "" {
		return ""
	}
	if width < 48 {
		width = 48
	}
	inner := width - 4
	if inner < 24 {
		inner = 24
	}
	lines := strings.Split(answer, "\n")
	start := len(lines) - 4
	if start < 0 {
		start = 0
	}
	body := []string{stBullet.Render("⏺ ") + stAccent.Render("正在回答") + stAccent.Render(" ▌")}
	for _, line := range lines[start:] {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		body = append(body, stInk.Render("  "+clipWidth(line, inner-2)))
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(body, "\n"))
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
			m.vp = newTranscriptViewport(msg.Width, vh)
			m.loadRecentSessions()
			m.setViewportContent(renderSplash(msg.Width, m.recentSessions), true)
			m.ready = true
		} else {
			m.vp.Width, m.vp.Height = msg.Width, vh
			if len(m.blocks) == 0 && m.answer == "" {
				m.loadRecentSessions()
				m.setViewportContent(renderSplash(msg.Width, m.recentSessions), true)
			}
		}
		m.ti.Width = msg.Width - 4

	case demoStartMsg:
		v := string(msg)
		m.ti.SetValue("")
		m.appendUserMessage(v, false)
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
		return m, tea.Batch(m.requestStreamRefresh(), listen(m.sub))

	case finalMsg:
		if m.answer == "" {
			m.answer = string(msg)
		}
		m.refreshPending = false
		m.refreshWithLiveAnswer()
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
			m.appendAnswerMessage(ans, m.used)
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

func renderConversationBlock(block conversationBlock, width int) string {
	switch block.Kind {
	case "user":
		return renderUserMessage(block.Raw, block.Retry)
	case "assistant":
		return renderAnswerMessage(block.Raw, block.Tools, width)
	default:
		return block.Raw
	}
}

func renderUserMessage(text string, retry bool) string {
	text = strings.TrimSpace(text)
	prefix := "❯"
	title := "用户问题"
	if retry {
		prefix = "↻"
		title = "重试问题"
	}
	lines := []string{
		stUser.Render(prefix + " " + title),
		stInk.Render("  " + text),
	}
	return strings.Join(lines, "\n")
}

func glamourStyleName() string {
	switch currentTheme {
	case "paper", "light":
		return "light"
	default:
		return "dark"
	}
}

func renderAnswerMessage(answer string, tools []string, width int) string {
	w := width - 4
	if w < 20 {
		w = 20
	}
	body := strings.Trim(answer, "\n")
	// Use a fixed named style — NOT WithAutoStyle(), which queries the terminal background
	// (OSC 11) on every render and leaks the response (]11;rgb:…) into the UI.
	if r, err := glamour.NewTermRenderer(glamour.WithStandardStyle(glamourStyleName()), glamour.WithWordWrap(w)); err == nil {
		if out, e := r.Render(answer); e == nil {
			body = strings.Trim(out, "\n")
		}
	}
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
	rows := []string{stAccent.Render(title) + stFaint.Render("  · Enter 执行 · Esc 返回 · / 命令")}
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
	body := []string{"使用 / 打开命令启动器; Enter 执行, Esc 返回。"}
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
	p := tea.NewProgram(m, tea.WithAltScreen(), tea.WithMouseCellMotion(), tea.WithFPS(terminalRenderFPS))
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
