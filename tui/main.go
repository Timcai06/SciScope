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
	"flag"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
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
	toolNamePattern = regexp.MustCompile(`\b(?:verify_claim|search_literature|get_trends|recommend_papers|get_paper|summarize_field|compare_papers|query_knowledge_graph|export_bibliography|list_disputes)\b`)
	verdictPattern  = regexp.MustCompile(`强支持|弱支持|不支持|支持等级|论断核查|证据卡|趋势卡|相似度|最高接地相似度`)
	cautionPattern  = regexp.MustCompile(`风险|限制|边界|注意|谨慎|可能|取决于|不应|不能|然而|但是|仍需|不足`)
)

// ---- tool icons/labels ----
//
// T05-01 icon policy（计划 3.2 节）：普通 Unicode 为 canonical 默认，不再依赖
// Nerd Font PUA 图形；Nerd Font 作为 opt-in 增强模式（SCISCOPE_TUI_ICONS=nerd），
// SCISCOPE_TUI_ICONS=off 则为纯中文标签（无任何图标依赖）。
//
// Unicode 图标全部选 BMP 单列宽符号，避免 emoji 双列宽导致列对齐错乱。
var toolIconsUnicode = map[string]string{
	"search_literature":     "⌕", // 检索
	"get_trends":            "↗", // 趋势
	"recommend_papers":      "✦", // 推荐
	"get_paper":             "▤", // 详情
	"summarize_field":       "≡", // 综述
	"compare_papers":        "⇄", // 对比
	"export_bibliography":   "⤓", // 导出
	"query_knowledge_graph": "◈", // 图谱
	"verify_claim":          "✓", // 核查
	"list_disputes":         "△", // 争议
}

// Nerd Font / Font Awesome glyphs (U+F0xx PUA) — opt-in enhancement only.
var toolIconsNerd = map[string]string{
	"search_literature":     "\uf002", // search
	"get_trends":            "\uf201", // line-chart
	"recommend_papers":      "\uf02d", // book
	"get_paper":             "\uf15c", // file-text
	"summarize_field":       "\uf0ca", // list-ul
	"compare_papers":        "\uf24e", // balance-scale
	"export_bibliography":   "\uf02e", // bookmark
	"query_knowledge_graph": "\uf0e8", // sitemap
	"verify_claim":          "\uf058", // check-circle
	"list_disputes":         "\uf071", // warning
}

var toolLabels = map[string]string{
	"search_literature":     "检索文献",
	"get_trends":            "研究趋势",
	"recommend_papers":      "论文推荐",
	"get_paper":             "论文详情",
	"summarize_field":       "领域综述",
	"compare_papers":        "论文对比",
	"export_bibliography":   "引文导出",
	"query_knowledge_graph": "知识图谱",
	"verify_claim":          "论断核查",
	"list_disputes":         "争议前线",
}

// iconMode 解析 SCISCOPE_TUI_ICONS：默认 "" → unicode；"nerd" → Nerd Font；
// "off" → 无图标（纯标签）。
func iconMode() string {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("SCISCOPE_TUI_ICONS"))) {
	case "nerd", "on", "1", "true", "yes":
		return "nerd"
	case "off", "0", "false", "no":
		return "off"
	default:
		return "unicode"
	}
}

var useIcons = iconMode()

func toolLabel(name string) string {
	v, ok := toolLabels[name]
	if !ok {
		v = name
	}
	if ic := toolIcon(name); ic != "" {
		return ic + "  " + v
	}
	return v
}

func toolIcon(name string) string {
	mode := useIcons
	if mode == "nerd" {
		if g, ok := toolIconsNerd[name]; ok {
			return g
		}
		return "\uf013"
	}
	if mode == "unicode" {
		if g, ok := toolIconsUnicode[name]; ok {
			return g
		}
		return "◆"
	}
	return "" // off：无图标
}

func toolPlainLabel(name string) string {
	if v, ok := toolLabels[name]; ok {
		return v
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
		"",
		"Judge-ready tasks:",
		"  /verify <claim>              verify one scientific claim with evidence or abstention",
		"  /review <topic>              map a topic into review-style research leads",
		"  /trend <topic>               descriptive trend only; not a prediction guarantee",
		"  /recommend <topic|paper_id>  needs paper embeddings; unavailable is shown explicitly",
	}, "\n")
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

// appendBlock 追加一个 typed 块。kind 为块类型身份（不再靠字符串猜测）；
// raw 为源文本（现含 ANSI 渲染字符串，T05-04 再迁无框语法）。
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

func runQuitCommand(m model, args []string) (model, tea.Cmd) {
	if len(args) >= 1 && args[0] == "yes" {
		return m, tea.Quit
	}
	m.appendBlock(BlockSystem, stFaint.Render("  已取消退出。"))
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
	// 关闭终端自动换行（DECAWM）：满宽行（外框 + 内容 = 终端全宽）在行尾写字符
	// 会触发自动换行导致后续行错位；退出时恢复。
	fmt.Print("\x1b[?7l")
	defer fmt.Print("\x1b[?7h")
	p := tea.NewProgram(m, tea.WithAltScreen(), tea.WithMouseCellMotion(), tea.WithFPS(terminalRenderFPS))
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
