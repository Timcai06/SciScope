package main

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

var ansiRE = regexp.MustCompile(`\x1b\[[0-9;]*m`)

func plainANSI(s string) string {
	return ansiRE.ReplaceAllString(s, "")
}

func TestRenderToolResultSearchLiteratureAsEvidenceCards(t *testing.T) {
	result := `[
		{"paper_id":"W1","标题":"Retrieval-Augmented Generation","年份":2025,"作者":["Ada","Bo"],"摘要片段":"RAG grounds answers in retrieved evidence."},
		{"paper_id":"W2","标题":"Knowledge Graph Retrieval","年份":2024,"作者":["Chen"],"摘要片段":"Graph evidence improves retrieval."}
	]`

	rendered := renderToolResult("search_literature", result, 120, 0)

	for _, want := range []string{
		"╭─ evidence · 证据卡 2 篇",
		"Retrieval-Augmented Generation",
		"│  W1 · 2025 · Ada, Bo",
		"Graph evidence improves retrieval.",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered result missing %q:\n%s", want, rendered)
		}
	}
}

func TestFormatHTTPErrorIncludesValidationDetails(t *testing.T) {
	resp := &http.Response{
		Status: "422 Unprocessable Entity",
		Body:   io.NopCloser(strings.NewReader(`{"detail":[{"loc":["body","question"],"msg":"question must not be empty"}]}`)),
	}

	got := formatHTTPError(resp)

	if !strings.Contains(got, "422") || !strings.Contains(got, "question must not be empty") {
		t.Fatalf("expected validation detail in HTTP error, got %q", got)
	}
}

func TestAgentRequestBodySanitizesHistoryForBackendSchema(t *testing.T) {
	body, err := agentRequestBody("  核查 RAG  ", []turn{
		{Role: "system", Content: "drop"},
		{Role: "user", Content: "上一问"},
		{Role: "assistant", Content: "上一答"},
		{Role: "assistant", Content: "   "},
	}, " tui-test ", true)
	if err != nil {
		t.Fatalf("agentRequestBody returned error: %v", err)
	}
	raw := string(body)
	for _, want := range []string{
		`"question":"核查 RAG"`,
		`"session_id":"tui-test"`,
		`"retry":true`,
		`"role":"user"`,
		`"role":"assistant"`,
	} {
		if !strings.Contains(raw, want) {
			t.Fatalf("request body missing %q:\n%s", want, raw)
		}
	}
	if strings.Contains(raw, `"system"`) || strings.Contains(raw, `"drop"`) {
		t.Fatalf("request body should drop invalid history turns:\n%s", raw)
	}
}

func TestMetaDetailFormatsLangGraphNodeTiming(t *testing.T) {
	got := metaDetail(eventMeta{Runtime: "langgraph", Node: "execute_tools", Phase: "证据检索", ElapsedMS: 42, Retry: true})

	if got != "阶段 证据检索 · 42ms · retry" {
		t.Fatalf("unexpected meta detail: %q", got)
	}
}

func TestRenderStreamRailShowsLangGraphObservability(t *testing.T) {
	rail := renderStreamRail(
		[]timelineEvent{{Kind: "tool_call", Label: "检索文献", Detail: "RAG hallucination"}},
		eventMeta{Runtime: "langgraph", Node: "execute_tools", Phase: "证据检索", SessionID: "tui-20260625T120000", ElapsedMS: 42, Retry: true},
		[]string{"prepare", "plan", "execute_tools"},
		"tool_call",
		3*time.Second,
		100,
	)

	for _, want := range []string{
		"langgraph",
		"阶段",
		"证据检索",
		"tool call",
		"retry",
		"42ms",
		"thread tui-20260625T120000",
		"理解问题",
		"制定研究计划",
		"检索文献",
	} {
		if !strings.Contains(rail, want) {
			t.Fatalf("stream rail missing %q:\n%s", want, rail)
		}
	}
}

func TestRenderWorkflowStatusShowsCurrentResearchPhase(t *testing.T) {
	rail := renderWorkflowStatus(
		eventMeta{Runtime: "langgraph", Node: "execute_tools", Phase: "证据检索", SessionID: "tui-20260625T120000", ElapsedMS: 42, Retry: true},
		[]string{"prepare", "plan", "execute_tools"},
		"tool_call",
		3*time.Second,
		100,
	)
	plain := plainANSI(rail)

	for _, want := range []string{
		"当前阶段",
		"证据检索",
		"理解问题",
		"制定研究计划",
		"推理与检索决策",
		"自检修正",
		"综合回答",
		"tui-20260625T120000",
		"retry",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("workflow status missing %q:\n%s", want, plain)
		}
	}
	if strings.Contains(plain, "execute_tools") {
		t.Fatalf("workflow status should not expose raw graph node:\n%s", plain)
	}
}

func TestNodePulseUpdatesLiveStreamState(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.answering = true
	m.start = time.Now()

	next, cmd := m.Update(nodePulseMsg{
		kind: "tool_result",
		meta: eventMeta{Runtime: "langgraph", Node: "execute_tools", SessionID: "tui-test"},
	})
	got := next.(model)

	if cmd == nil {
		t.Fatalf("expected node pulse to keep stream listener active")
	}
	if got.lastMeta.Node != "execute_tools" || got.lastStreamKind != "tool_result" {
		t.Fatalf("unexpected stream state: %#v kind=%s", got.lastMeta, got.lastStreamKind)
	}
	if len(got.nodeSeen) != 1 || got.nodeSeen[0] != "execute_tools" {
		t.Fatalf("expected node path to record execute_tools, got %#v", got.nodeSeen)
	}
}

func TestRenderToolResultVerifyClaimAsGroundingCards(t *testing.T) {
	result := `{
		"论断":"检索增强生成能够降低幻觉",
		"支持等级":"强支持",
		"最高接地相似度":0.846,
		"证据":[
			{"paper_id":"W4411065983","标题":"Retrieval-Augmented Generation and Hallucination","年份":2025,"接地相似度":0.846},
			{"paper_id":"2309.01431","标题":"Benchmarking Large Language Models in Retrieval-Augmented Generation","年份":2023,"接地相似度":0.827}
		]
	}`

	rendered := renderToolResult("verify_claim", result, 120, 0)

	for _, want := range []string{
		"╭─ verify · 论断核查",
		"强支持 · 0.846",
		"检索增强生成能够降低幻觉",
		"Retrieval-Augmented Generation and Hallucination",
		"│  W4411065983 · 2025 · 相似度 0.846",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered result missing %q:\n%s", want, rendered)
		}
	}
}

func TestRenderTrendResultAvoidsInternalMetricJargon(t *testing.T) {
	result := `[
		{
			"关键词":"retrieval augmented generation",
			"累计论文数":120,
			"增长方向":"rising",
			"生命周期阶段":"growth",
			"统计依据":{"近期活跃度分":0.88,"短期加速分":0.44}
		}
	]`

	rendered := renderToolResult("get_trends", result, 120, 0)
	summary := summarizeToolResultMarkdown("get_trends", result)
	visible := plainANSI(rendered + "\n" + summary)

	for _, want := range []string{
		"趋势卡",
		"retrieval augmented generation",
		"方向 rising",
		"阶段 growth",
		"依据",
	} {
		if !strings.Contains(visible, want) {
			t.Fatalf("trend rendering missing %q:\n%s", want, visible)
		}
	}
	for _, removed := range []string{"动量", "Mann-Kendall", "Sen", "burst"} {
		if strings.Contains(visible, removed) {
			t.Fatalf("trend rendering should translate internal jargon %q:\n%s", removed, visible)
		}
	}
}

func TestFriendlyErrorSuggestsRecoveryCommand(t *testing.T) {
	msg := friendlyError("无法连接后端 http://127.0.0.1:8000:dial tcp 127.0.0.1:8000: connect: connection refused")

	if !strings.Contains(msg, "make backend") {
		t.Fatalf("expected backend recovery hint, got %q", msg)
	}
}

func TestExportMarkdownIncludesConversationAndEvidence(t *testing.T) {
	events := []transcriptEvent{
		{Kind: "user", Content: "帮我核查 RAG 是否能降低幻觉"},
		{Kind: "plan", Content: "1. 检索相关论文\n2. 核查论断"},
		{Kind: "tool_call", Tool: "verify_claim", Content: "检索增强生成能够降低幻觉"},
		{Kind: "tool_result", Tool: "verify_claim", Content: "- [1] Retrieval-Augmented Generation and Hallucination\n  W1 · 2025 · 相似度 0.846"},
		{Kind: "assistant", Content: "结论: 该论断获得强支持。"},
	}

	md := exportMarkdown(events, time.Date(2026, 6, 25, 12, 30, 0, 0, time.UTC))

	for _, want := range []string{
		"# SciScope 会话导出",
		"导出时间: 2026-06-25 12:30:00 UTC",
		"## 用户问题",
		"帮我核查 RAG 是否能降低幻觉",
		"## 工具调用: verify_claim",
		"## 证据结果: verify_claim",
		"Retrieval-Augmented Generation and Hallucination",
		"## 智能体回答",
		"该论断获得强支持",
	} {
		if !strings.Contains(md, want) {
			t.Fatalf("export markdown missing %q:\n%s", want, md)
		}
	}
}

func TestWriteSessionMarkdownCreatesFile(t *testing.T) {
	dir := t.TempDir()
	events := []transcriptEvent{{Kind: "user", Content: "检索 2025 年 RAG 论文"}}
	now := time.Date(2026, 6, 25, 12, 30, 0, 0, time.UTC)

	path, err := writeSessionMarkdown(dir, events, now)
	if err != nil {
		t.Fatalf("writeSessionMarkdown returned error: %v", err)
	}
	if filepath.Dir(path) != dir {
		t.Fatalf("expected session in %s, got %s", dir, path)
	}
	if filepath.Ext(path) != ".md" {
		t.Fatalf("expected markdown file, got %s", path)
	}

	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read exported markdown: %v", err)
	}
	if !strings.Contains(string(b), "检索 2025 年 RAG 论文") {
		t.Fatalf("exported file missing conversation:\n%s", string(b))
	}
}

func TestRenderTimelineMarkdownShowsToolLifecycle(t *testing.T) {
	events := []timelineEvent{
		{Kind: "plan", Phase: "制定研究计划", Label: "执行计划", Detail: "检索相关论文"},
		{Kind: "tool_call", Phase: "证据检索", Tool: "search_literature", Label: "检索文献", Detail: "RAG hallucination"},
		{Kind: "tool_result", Phase: "证据检索", Tool: "search_literature", Label: "证据卡 2 篇", Duration: 1200 * time.Millisecond},
		{Kind: "final", Phase: "综合回答", Label: "回答完成"},
	}

	md := renderTimelineMarkdown(events)

	for _, want := range []string{
		"## 科研工作流时间线",
		"### 制定研究计划",
		"- 执行计划: 检索相关论文",
		"### 证据检索",
		"- 检索文献: RAG hallucination",
		"- 证据卡 2 篇 (1.2s)",
		"### 综合回答",
		"- 回答完成",
	} {
		if !strings.Contains(md, want) {
			t.Fatalf("timeline markdown missing %q:\n%s", want, md)
		}
	}
}

func TestPermissionNoticeHighlightsExportTool(t *testing.T) {
	notice, ok := permissionNotice("export_bibliography")
	if !ok {
		t.Fatalf("expected export_bibliography to require a permission notice")
	}
	for _, want := range []string{"权限提示", "导出", "会话记录"} {
		if !strings.Contains(notice, want) {
			t.Fatalf("permission notice missing %q: %s", want, notice)
		}
	}

	if notice, ok := permissionNotice("search_literature"); ok || notice != "" {
		t.Fatalf("search_literature should not require a permission notice, got %q", notice)
	}
}

func TestExportMarkdownIncludesTimelineSection(t *testing.T) {
	events := []transcriptEvent{
		{Kind: "user", Content: "导出 RAG 引文"},
		{Kind: "timeline", Content: "1. 引文导出: RAG\n2. 回答完成"},
		{Kind: "assistant", Content: "已整理引用。"},
	}

	md := exportMarkdown(events, time.Date(2026, 6, 25, 12, 30, 0, 0, time.UTC))

	if !strings.Contains(md, "## 工具调用时间线") {
		t.Fatalf("expected timeline section in export:\n%s", md)
	}
	if !strings.Contains(md, "1. 引文导出: RAG") {
		t.Fatalf("expected timeline content in export:\n%s", md)
	}
}

func TestRecoveryActionClassifiesBackendError(t *testing.T) {
	action := recoveryAction("无法连接后端 http://127.0.0.1:8000: connect: connection refused")

	if action.Command != "make backend" {
		t.Fatalf("expected make backend recovery command, got %#v", action)
	}
	if !action.Retryable {
		t.Fatalf("expected backend error to be retryable")
	}
	if !strings.Contains(action.Message, "/retry") {
		t.Fatalf("expected retry hint in recovery message: %s", action.Message)
	}
}

func TestRetrySlashReplaysLastQuestion(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(80, 20)
	m.lastQuestion = "核查 RAG 是否降低幻觉"

	next, cmd := m.runSlash("/retry")
	got := next.(model)

	if cmd == nil {
		t.Fatalf("expected retry to start a stream command")
	}
	if !got.answering {
		t.Fatalf("expected model to be answering after retry")
	}
	if got.history[len(got.history)-1] != (turn{"user", "核查 RAG 是否降低幻觉"}) {
		t.Fatalf("expected retry to append last question to history, got %#v", got.history)
	}
	if len(got.transcript) == 0 || got.transcript[len(got.transcript)-1].Content != "核查 RAG 是否降低幻觉" {
		t.Fatalf("expected retry question in transcript, got %#v", got.transcript)
	}
}

func TestListSessionFilesReturnsNewestFirst(t *testing.T) {
	dir := t.TempDir()
	oldPath := filepath.Join(dir, "sciscope-session-20260625-120000.md")
	newPath := filepath.Join(dir, "sciscope-session-20260625-130000.md")
	if err := os.WriteFile(oldPath, []byte("# old"), 0o644); err != nil {
		t.Fatalf("write old session: %v", err)
	}
	time.Sleep(10 * time.Millisecond)
	if err := os.WriteFile(newPath, []byte("# new"), 0o644); err != nil {
		t.Fatalf("write new session: %v", err)
	}

	sessions, err := listSessionFiles(dir, 5)
	if err != nil {
		t.Fatalf("listSessionFiles returned error: %v", err)
	}
	if len(sessions) != 2 {
		t.Fatalf("expected 2 sessions, got %#v", sessions)
	}
	if sessions[0].Path != newPath {
		t.Fatalf("expected newest session first, got %#v", sessions)
	}
}

func TestLoadSessionMarkdownRestoresLastQuestion(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sciscope-session-20260625-130000.md")
	md := "# SciScope 会话导出\n\n## 用户问题\n\n核查 RAG 是否降低幻觉\n\n## 智能体回答\n\n可以。"
	if err := os.WriteFile(path, []byte(md), 0o644); err != nil {
		t.Fatalf("write session: %v", err)
	}

	s, err := loadSessionMarkdown(path)
	if err != nil {
		t.Fatalf("loadSessionMarkdown returned error: %v", err)
	}
	if s.LastQuestion != "核查 RAG 是否降低幻觉" {
		t.Fatalf("expected last question restored, got %#v", s)
	}
	if !strings.Contains(s.Content, "可以。") {
		t.Fatalf("expected full content restored, got %#v", s)
	}
}

func TestSessionsSlashRendersRecentSessions(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("SCISCOPE_SESSION_DIR", dir)
	path := filepath.Join(dir, "sciscope-session-20260625-130000.md")
	if err := os.WriteFile(path, []byte("# SciScope 会话导出\n\n## 用户问题\n\n核查 RAG"), 0o644); err != nil {
		t.Fatalf("write session: %v", err)
	}
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	next, _ := m.runSlash("/sessions")
	got := next.(model)
	content := got.vp.View()

	if !strings.Contains(content, "/resume 1") {
		t.Fatalf("expected resume command in sessions view:\n%s", content)
	}
	if !strings.Contains(content, "sciscope-session-20260625-130000.md") {
		t.Fatalf("expected session filename in sessions view:\n%s", content)
	}
}

func TestPanelRowUsesConsistentDenseGrammar(t *testing.T) {
	row := panelRow("evidence", "证据卡 2 篇", "1.2s", []string{"[1] Paper", "W1 · 2025"})

	for _, want := range []string{
		"╭─ evidence · 证据卡 2 篇 · 1.2s",
		"│  [1] Paper",
		"│  W1 · 2025",
		"╰─",
	} {
		if !strings.Contains(row, want) {
			t.Fatalf("panel row missing %q:\n%s", want, row)
		}
	}
}

func TestTimelineAndErrorUsePanelRows(t *testing.T) {
	timeline := renderTimelineBlock([]timelineEvent{
		{Kind: "tool_call", Phase: "证据检索", Label: "检索文献", Detail: "RAG"},
		{Kind: "final", Phase: "综合回答", Label: "回答完成"},
	})
	if !strings.Contains(timeline, "╭─ timeline · 本轮执行时间线") {
		t.Fatalf("timeline should use panel row grammar:\n%s", timeline)
	}
	for _, want := range []string{
		"证据检索",
		"  - 检索文献 · RAG",
		"综合回答",
		"  - 回答完成",
	} {
		if !strings.Contains(timeline, want) {
			t.Fatalf("timeline missing grouped row %q:\n%s", want, timeline)
		}
	}

	errPanel := renderRecoveryPanel("无法连接后端: connection refused")
	if !strings.Contains(errPanel, "╭─ recovery · 后端未连接") {
		t.Fatalf("recovery should use panel row grammar:\n%s", errPanel)
	}
	for _, want := range []string{
		"blocked",
		"error",
		"reason",
		"primary make backend",
		"next    /retry",
		"inspect /doctor",
	} {
		if !strings.Contains(errPanel, want) {
			t.Fatalf("recovery panel missing %q:\n%s", want, errPanel)
		}
	}
}

func TestTimelineBlockShowsEmptyState(t *testing.T) {
	timeline := renderTimelineBlock(nil)

	for _, want := range []string{
		"╭─ timeline · 本轮执行时间线 · empty",
		"暂无本轮执行轨迹",
		"/demo",
	} {
		if !strings.Contains(timeline, want) {
			t.Fatalf("empty timeline missing %q:\n%s", want, timeline)
		}
	}
}

func TestTimelineSlashRendersCurrentTurnTrace(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.timeline = []timelineEvent{
		{Kind: "plan", Phase: "制定研究计划", Label: "执行计划", Detail: "检索证据"},
		{Kind: "tool_result", Phase: "证据检索", Tool: "verify_claim", Label: "论断核查 · 强支持", Duration: 1500 * time.Millisecond},
	}

	next, _ := m.runSlash("/timeline")
	got := next.(model)
	content := got.vp.View()

	for _, want := range []string{
		"本轮执行时间线",
		"制定研究计划",
		"执行计划",
		"检索证据",
		"证据检索",
		"论断核查",
		"1.5s",
	} {
		if !strings.Contains(content, want) {
			t.Fatalf("/timeline output missing %q:\n%s", want, content)
		}
	}
}

func TestDemoScriptCoversGoldenFlow(t *testing.T) {
	msgs := demoScriptMessages()
	if len(msgs) < 7 {
		t.Fatalf("expected rich demo script, got %#v", msgs)
	}

	var hasStart, hasPlan, hasVerifyCall, hasVerifyResult, hasSearchResult, hasFinal, hasDone bool
	for _, msg := range msgs {
		switch msg := msg.(type) {
		case demoStartMsg:
			hasStart = strings.Contains(string(msg), "RAG")
		case planMsg:
			hasPlan = len(msg) >= 3
		case toolCallMsg:
			if msg.name == "verify_claim" {
				hasVerifyCall = true
			}
		case toolResultMsg:
			if msg.name == "verify_claim" && strings.Contains(msg.result, "强支持") {
				hasVerifyResult = true
			}
			if msg.name == "search_literature" && strings.Contains(msg.result, "Retrieval-Augmented") {
				hasSearchResult = true
			}
		case finalMsg:
			hasFinal = strings.Contains(string(msg), "可验证")
		case doneMsg:
			hasDone = true
		}
	}
	for name, ok := range map[string]bool{
		"start":         hasStart,
		"plan":          hasPlan,
		"verify_call":   hasVerifyCall,
		"verify_result": hasVerifyResult,
		"search_result": hasSearchResult,
		"final":         hasFinal,
		"done":          hasDone,
	} {
		if !ok {
			t.Fatalf("demo script missing %s: %#v", name, msgs)
		}
	}
}

func TestDemoModeReadsEnvironment(t *testing.T) {
	t.Setenv("SCISCOPE_TUI_DEMO", "1")
	if !demoMode() {
		t.Fatalf("expected demo mode from SCISCOPE_TUI_DEMO=1")
	}
}

func TestSplashScreenShowsProductCurtain(t *testing.T) {
	splash := renderSplash(96, nil)

	for _, want := range []string{
		"███████╗ ██████╗██╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗",
		"科研智能体终端",
		"Evidence-grounded research agent",
		"Start with a claim",
		"Type / for commands",
	} {
		if !strings.Contains(splash, want) {
			t.Fatalf("splash missing %q:\n%s", want, splash)
		}
	}
	for _, removed := range []string{
		"Quick actions",
		"Golden demo",
		"System status",
		"Recent work",
		"/demo",
		"/sessions",
		"/resume 1",
	} {
		if strings.Contains(splash, removed) {
			t.Fatalf("splash should not render old dashboard content %q:\n%s", removed, splash)
		}
	}
}

func TestBrandMarkScalesForCompactWidth(t *testing.T) {
	wide := asciiBrand(100)
	compact := asciiBrand(42)

	if !strings.Contains(wide, "███████") {
		t.Fatalf("expected wide brand to use large ASCII art:\n%s", wide)
	}
	if !strings.Contains(compact, "SciScope") {
		t.Fatalf("expected compact brand fallback:\n%s", compact)
	}
}

func TestSplashScalesDownWithoutLosingActions(t *testing.T) {
	splash := renderSplash(42, nil)

	for _, want := range []string{
		"SciScope",
		"科研智能体终端",
		"Type /",
		"commands",
	} {
		if !strings.Contains(splash, want) {
			t.Fatalf("compact splash missing %q:\n%s", want, splash)
		}
	}
}

func TestComposerRendersPolishedInputBox(t *testing.T) {
	m := initialModel()
	m.ti.SetValue("核查 RAG")
	m.sessionID = "tui-test-session"
	composer := m.renderComposer(96)

	for _, want := range []string{
		"核查 RAG",
		"Enter",
		"Esc",
		"commands",
	} {
		if !strings.Contains(composer, want) {
			t.Fatalf("composer missing %q:\n%s", want, composer)
		}
	}
	for _, removed := range []string{"session tui-test-session", "langgraph", "/retry"} {
		if strings.Contains(composer, removed) {
			t.Fatalf("composer should not expose noisy status %q:\n%s", removed, composer)
		}
	}
}

func TestSlashCommandPaletteUsesFullWidth(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.ti.SetValue("/")
	palette := m.renderCommandPalette(100)

	for _, want := range []string{
		"Commands",
		"Suggested",
		"Session",
		"Evidence",
		"System",
		"/demo",
		"/timeline",
		"/sessions",
		"Golden demo",
		"Enter run",
	} {
		if !strings.Contains(palette, want) {
			t.Fatalf("palette missing %q:\n%s", want, palette)
		}
	}
	if lipgloss.Width(palette) < 96 {
		t.Fatalf("expected full-width command palette, width=%d:\n%s", lipgloss.Width(palette), palette)
	}
}

func TestSlashCommandPaletteFiltersByCategoryAndDescription(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.ti.SetValue("/session")
	palette := m.renderCommandPalette(100)

	for _, want := range []string{
		"Recent sessions",
		"Resume session",
	} {
		if !strings.Contains(palette, want) {
			t.Fatalf("filtered palette missing %q:\n%s", want, palette)
		}
	}
	if strings.Contains(palette, "Golden demo") {
		t.Fatalf("filtered palette should not include demo:\n%s", palette)
	}
}

func TestThinkingPanelsUseTraceGrammar(t *testing.T) {
	plan := renderPlanBlock(planMsg{"解析问题", "检索证据"})
	if !strings.Contains(plan, "╭─ thinking · 思考过程") {
		t.Fatalf("plan should render as thinking panel:\n%s", plan)
	}
	if !strings.Contains(plan, "│  [1] 解析问题") {
		t.Fatalf("plan missing numbered step:\n%s", plan)
	}

	call := renderToolCallBlock("verify_claim", "RAG 降低幻觉")
	if !strings.Contains(call, "╭─ action · 论断核查") {
		t.Fatalf("tool call should render as action panel:\n%s", call)
	}
	if !strings.Contains(call, "RAG 降低幻觉") {
		t.Fatalf("tool call missing args:\n%s", call)
	}

	reflection := renderReflectBlock("限定为降低风险")
	if !strings.Contains(reflection, "╭─ thinking · 自我纠错") {
		t.Fatalf("reflect should render as thinking panel:\n%s", reflection)
	}
}

func TestThinkingShelfRendersAboveComposerState(t *testing.T) {
	shelf := renderThinkingShelf([]string{"检索相关论文", "综合证据"}, "证据不足时重试", 100)

	for _, want := range []string{
		"研究计划",
		"[1] 检索相关论文",
		"自检修正",
		"证据不足时重试",
	} {
		if !strings.Contains(shelf, want) {
			t.Fatalf("thinking shelf missing %q:\n%s", want, shelf)
		}
	}
}

func TestPlanAndReflectStayOutOfConversationBlocks(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = viewport.New(100, 20)

	next, _ := m.Update(planMsg{"检索证据", "综合回答"})
	got := next.(model)
	if len(got.blocks) != 0 {
		t.Fatalf("plan should not append to conversation blocks: %#v", got.blocks)
	}
	if len(got.livePlan) != 2 {
		t.Fatalf("expected live plan to update, got %#v", got.livePlan)
	}

	next, _ = got.Update(reflectMsg("需要补充证据"))
	got = next.(model)
	if len(got.blocks) != 0 {
		t.Fatalf("reflect should not append to conversation blocks: %#v", got.blocks)
	}
	if got.liveReflect != "需要补充证据" {
		t.Fatalf("expected live reflect to update, got %q", got.liveReflect)
	}
	if !strings.Contains(got.View(), "需要补充证据") {
		t.Fatalf("view should show live reflect above composer:\n%s", got.View())
	}
}

func TestToolEventsStayOutOfConversationBlocks(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = viewport.New(100, 20)

	next, _ := m.Update(toolCallMsg{name: "search_literature", args: map[string]any{"query": "RAG"}})
	got := next.(model)
	if len(got.blocks) != 0 {
		t.Fatalf("tool call should not append to conversation blocks: %#v", got.blocks)
	}

	next, _ = got.Update(toolResultMsg{name: "search_literature", result: `[{"paper_id":"W1","标题":"RAG","年份":2025}]`})
	got = next.(model)
	if len(got.blocks) != 0 {
		t.Fatalf("tool result should not append to conversation blocks: %#v", got.blocks)
	}
	if len(got.timeline) < 2 {
		t.Fatalf("tool events should still be available in timeline: %#v", got.timeline)
	}
}

func TestDoneAppendsOnlyAnswerToConversationBlocks(t *testing.T) {
	t.Setenv("SCISCOPE_SESSION_DIR", t.TempDir())
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = viewport.New(100, 20)
	m.answer = "最终回答"
	m.timeline = []timelineEvent{{Kind: "tool_call", Label: "检索文献"}}

	next, _ := m.Update(doneMsg{})
	got := next.(model)

	if len(got.blocks) != 2 {
		t.Fatalf("expected user-visible answer and save notice only, got %#v", got.blocks)
	}
	if strings.Contains(got.blocks[0], "本轮执行时间线") {
		t.Fatalf("timeline should not be appended to main chat:\n%s", strings.Join(got.blocks, "\n"))
	}
}

func TestFinalMessageRefreshesStreamingAnswerImmediately(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = viewport.New(100, 20)

	next, _ := m.Update(finalMsg("最终结论"))
	got := next.(model)

	if got.answer != "最终结论" {
		t.Fatalf("expected final answer to be stored immediately, got %q", got.answer)
	}
	if !strings.Contains(got.vp.View(), "最终结论") {
		t.Fatalf("expected final answer to render before done:\n%s", got.vp.View())
	}
}

func TestRenderAnswerUsesChatMessageStyle(t *testing.T) {
	m := initialModel()
	m.vp = viewport.New(100, 20)
	m.answer = "## 结论\n\nRAG 能降低无依据回答风险。"
	m.used = []string{"verify_claim"}

	rendered := m.renderAnswer()
	plain := plainANSI(rendered)
	for _, want := range []string{
		"⏺",
		"结论",
		"RAG 能降低",
		"/timeline 查看过程",
		"论断核查",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("answer message missing %q:\n%s", want, rendered)
		}
	}
	if strings.Contains(plain, "╭─ answer") {
		t.Fatalf("answer should not render as isolated card:\n%s", rendered)
	}
}

func TestInitialViewportUsesSplashCurtain(t *testing.T) {
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	got := next.(model)

	if !strings.Contains(got.vp.View(), "科研智能体终端") {
		t.Fatalf("expected initial viewport to show splash:\n%s", got.vp.View())
	}
}

func TestSplashShowsRecentSessionSummaries(t *testing.T) {
	sessions := []sessionFile{
		{
			Index:        1,
			Name:         "sciscope-session-20260625-130000.md",
			LastQuestion: "核查 RAG 是否降低幻觉",
			ModTime:      time.Date(2026, 6, 25, 13, 0, 0, 0, time.Local),
			Size:         2048,
		},
	}

	splash := renderSplash(112, sessions)

	for _, removed := range []string{"Recent work", "/resume 1", "核查 RAG", "06-25 13:00"} {
		if strings.Contains(splash, removed) {
			t.Fatalf("splash should keep recent sessions out of the opening curtain %q:\n%s", removed, splash)
		}
	}
}

func TestParseCLIOptions(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want cliOptions
	}{
		{name: "demo", args: []string{"--demo"}, want: cliOptions{Demo: true}},
		{name: "demo command", args: []string{"demo"}, want: cliOptions{Demo: true, Command: "demo"}},
		{name: "doctor command", args: []string{"doctor"}, want: cliOptions{Doctor: true, Command: "doctor"}},
		{name: "export last command", args: []string{"export", "--last"}, want: cliOptions{ExportLast: true, Command: "export"}},
		{name: "version", args: []string{"--version"}, want: cliOptions{Version: true}},
		{name: "short version", args: []string{"-v"}, want: cliOptions{Version: true}},
		{name: "help", args: []string{"--help"}, want: cliOptions{Help: true}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parseCLIOptions(tt.args)
			if err != nil {
				t.Fatalf("parseCLIOptions returned error: %v", err)
			}
			if got.Demo != tt.want.Demo || got.Doctor != tt.want.Doctor || got.ExportLast != tt.want.ExportLast || got.Version != tt.want.Version || got.Help != tt.want.Help || got.Command != tt.want.Command {
				t.Fatalf("got %#v, want %#v", got, tt.want)
			}
		})
	}
}

func TestVersionStringIncludesAppName(t *testing.T) {
	got := versionString("0.1.0")
	if !strings.Contains(got, "sciscope-tui 0.1.0") {
		t.Fatalf("unexpected version string: %s", got)
	}
}

func TestDoctorReportRendersProductChecks(t *testing.T) {
	report := renderDoctorReport([]doctorCheck{
		{Name: "Backend", Status: "ok", Detail: healthURL()},
		{Name: "LLM", Status: "warn", Detail: "make llm"},
		{Name: "Sessions", Status: "ok", Detail: "/tmp/sessions"},
	})

	for _, want := range []string{
		"SciScope doctor",
		"Backend",
		"ok",
		"LLM",
		"warn",
		"Sessions",
		"make llm",
	} {
		if !strings.Contains(report, want) {
			t.Fatalf("doctor report missing %q:\n%s", want, report)
		}
	}
}

func TestDoctorUsesIngestStatusAsBackendHealthCheck(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "http://127.0.0.1:8000/")

	got := healthURL()

	if got != "http://127.0.0.1:8000/api/ingest/status" {
		t.Fatalf("unexpected health URL: %s", got)
	}
}

func TestExportLastSessionReturnsNewestMarkdown(t *testing.T) {
	dir := t.TempDir()
	oldPath := filepath.Join(dir, "sciscope-session-20260625-120000.md")
	newPath := filepath.Join(dir, "sciscope-session-20260625-130000.md")
	if err := os.WriteFile(oldPath, []byte("# old"), 0o644); err != nil {
		t.Fatalf("write old session: %v", err)
	}
	time.Sleep(10 * time.Millisecond)
	if err := os.WriteFile(newPath, []byte("# new\n\n## 用户问题\n\n最新问题"), 0o644); err != nil {
		t.Fatalf("write new session: %v", err)
	}

	content, path, err := exportLastSession(dir)
	if err != nil {
		t.Fatalf("exportLastSession returned error: %v", err)
	}
	if path != newPath {
		t.Fatalf("expected newest path %s, got %s", newPath, path)
	}
	if !strings.Contains(content, "最新问题") {
		t.Fatalf("expected newest session content, got:\n%s", content)
	}
}

func TestSplashKeepsStatusOutOfOpeningCurtain(t *testing.T) {
	splash := renderSplash(112, nil)

	for _, removed := range []string{
		"System status",
		"Backend",
		"LLM",
		"Sessions",
		"doctor",
	} {
		if strings.Contains(splash, removed) {
			t.Fatalf("splash should not show status dashboard content %q:\n%s", removed, splash)
		}
	}
}

func TestComposerShowsMultilineAndRecoveryHints(t *testing.T) {
	m := initialModel()
	m.ti.SetValue("第一行\n第二行")
	composer := m.renderComposer(96)

	for _, want := range []string{
		"第一行",
		"第二行",
		"Esc",
		"/",
		"commands",
	} {
		if !strings.Contains(composer, want) {
			t.Fatalf("composer missing %q:\n%s", want, composer)
		}
	}
	for _, removed := range []string{"agent", "langgraph", "/retry"} {
		if strings.Contains(composer, removed) {
			t.Fatalf("composer should stay minimal, found %q:\n%s", removed, composer)
		}
	}
}
