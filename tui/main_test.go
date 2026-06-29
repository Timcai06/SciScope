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

func TestTranscriptViewportUsesFasterWheelDelta(t *testing.T) {
	vp := newTranscriptViewport(100, 20)

	if vp.MouseWheelDelta != 8 {
		t.Fatalf("MouseWheelDelta = %d, want 8", vp.MouseWheelDelta)
	}
}

func TestAnimationCadenceIsScrollFriendly(t *testing.T) {
	if streamRefreshInterval < 80*time.Millisecond {
		t.Fatalf("stream refresh interval %s is too aggressive for smooth terminal scrolling", streamRefreshInterval)
	}
	m := initialModel()
	if m.spin.Spinner.FPS < 250*time.Millisecond {
		t.Fatalf("spinner FPS interval %s is too aggressive for smooth terminal scrolling", m.spin.Spinner.FPS)
	}
	if terminalRenderFPS > 30 {
		t.Fatalf("terminal render FPS %d should be capped for smoother scrolling", terminalRenderFPS)
	}
}

func TestVerticalWheelFilterIgnoresNonScrollMouseEvents(t *testing.T) {
	cases := []struct {
		name string
		msg  tea.MouseMsg
		want bool
	}{
		{
			name: "wheel up",
			msg:  tea.MouseMsg{Action: tea.MouseActionPress, Button: tea.MouseButtonWheelUp},
			want: true,
		},
		{
			name: "wheel down",
			msg:  tea.MouseMsg{Action: tea.MouseActionPress, Button: tea.MouseButtonWheelDown},
			want: true,
		},
		{
			name: "motion",
			msg:  tea.MouseMsg{Action: tea.MouseActionMotion},
		},
		{
			name: "click",
			msg:  tea.MouseMsg{Action: tea.MouseActionPress, Button: tea.MouseButtonLeft},
		},
		{
			name: "horizontal wheel",
			msg:  tea.MouseMsg{Action: tea.MouseActionPress, Button: tea.MouseButtonWheelLeft},
		},
	}
	for _, c := range cases {
		if got := isVerticalWheel(c.msg); got != c.want {
			t.Fatalf("%s: isVerticalWheel = %v, want %v", c.name, got, c.want)
		}
	}
}

func TestSemanticHighlightStylesResearchTokens(t *testing.T) {
	raw := "强支持: verify_claim 命中 W4411065983, 2025, 相似度 0.846; /timeline 查看, 但仍需谨慎"

	spans := resolveHighlightSpans(semanticHighlightSpans(raw))
	if len(spans) < 6 {
		t.Fatalf("expected semantic spans for verdict/tool/paper/metric/command/caution, got %#v", spans)
	}
	styled := styleSemanticText(raw)
	plain := plainANSI(styled)
	for _, want := range []string{"强支持", "verify_claim", "W4411065983", "0.846", "/timeline", "谨慎"} {
		if !strings.Contains(plain, want) {
			t.Fatalf("highlighted text missing %q:\n%s", want, plain)
		}
	}
}

func TestKaomojiTracksAgentState(t *testing.T) {
	cases := []struct {
		name string
		kind string
		meta eventMeta
		want string
	}{
		{name: "plan", kind: "plan", want: "(。-`ω´-)"},
		{name: "tool", kind: "tool_call", meta: eventMeta{Node: "execute_tools"}, want: "(つ•̀ω•́)つ"},
		{name: "reflect", kind: "reflect", want: "( ･᷄ὢ･᷅ )"},
		{name: "final", kind: "final", want: "(๑•̀ㅂ•́)و✧"},
		{name: "retry", kind: "text", meta: eventMeta{Retry: true}, want: "(ง •̀_•́)ง"},
		{name: "idle", kind: "", want: "(´▽`)"},
	}
	for _, c := range cases {
		answering := c.name != "idle"
		if got := kaomojiForState(c.kind, c.meta, answering); got != c.want {
			t.Fatalf("%s: kaomoji = %q, want %q", c.name, got, c.want)
		}
	}
}

func TestToolResultMentionsTimelineForCollapsedEvidence(t *testing.T) {
	result := `[
		{"paper_id":"W1","标题":"A","年份":2025},
		{"paper_id":"W2","标题":"B","年份":2025},
		{"paper_id":"W3","标题":"C","年份":2025},
		{"paper_id":"W4","标题":"D","年份":2025},
		{"paper_id":"W5","标题":"E","年份":2025}
	]`

	rendered := renderToolResult("search_literature", result, 120, 0)

	if !strings.Contains(rendered, "+1 篇更多证据 · /timeline 查看完整证据链") {
		t.Fatalf("collapsed evidence should point to /timeline:\n%s", rendered)
	}
}

func TestAppendBlockMaintainsStructuredBlockCache(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	m.appendBlock("第一条")

	if len(m.blockItems) != 1 {
		t.Fatalf("appendBlock should add one structured block, got %#v", m.blockItems)
	}
	if m.blockItems[0].Raw != "第一条" || m.blockItems[0].Kind != "message" {
		t.Fatalf("unexpected structured block: %#v", m.blockItems[0])
	}
}

func TestRenderBlocksContentReusesWidthCache(t *testing.T) {
	m := initialModel()
	m.blocks = []string{"alpha", "beta"}

	first := m.renderBlocksContent(80)
	if first != "alpha\nbeta" {
		t.Fatalf("unexpected rendered content: %q", first)
	}
	if len(m.blockItems) != 2 {
		t.Fatalf("expected fallback blocks to populate structured cache, got %#v", m.blockItems)
	}
	version := m.blockItems[0].RenderVersion

	second := m.renderBlocksContent(80)
	if second != first {
		t.Fatalf("same width should render same content: %q vs %q", second, first)
	}
	if m.blockItems[0].RenderVersion != version {
		t.Fatalf("same-width render should reuse cache, version %d -> %d", version, m.blockItems[0].RenderVersion)
	}

	_ = m.renderBlocksContent(72)
	if m.blockItems[0].RenderVersion == version {
		t.Fatalf("width change should invalidate per-block render cache")
	}
}

func TestRenderTranscriptContentReusesWholeTranscriptCache(t *testing.T) {
	m := initialModel()
	m.blocks = []string{"alpha", "beta"}

	first := m.renderTranscriptContent(80)
	if first != "alpha\nbeta" {
		t.Fatalf("unexpected transcript content: %q", first)
	}
	cacheVersion := m.transcriptCacheVersion

	second := m.renderTranscriptContent(80)
	if second != first {
		t.Fatalf("same width should reuse transcript text: %q vs %q", second, first)
	}
	if m.transcriptCacheVersion != cacheVersion {
		t.Fatalf("same-width transcript render should reuse cache, version %d -> %d", cacheVersion, m.transcriptCacheVersion)
	}

	m.appendBlock("gamma")
	third := m.renderTranscriptContent(80)
	if third != "alpha\nbeta\ngamma" {
		t.Fatalf("append should invalidate transcript cache, got %q", third)
	}
	if m.transcriptCacheVersion == cacheVersion {
		t.Fatalf("append should rebuild transcript cache")
	}
}

func TestStreamingTextKeepsViewportStableUntilFinal(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = newTranscriptViewport(100, 20)
	m.appendBlock("历史 transcript")
	m.refresh()
	beforeViewport := m.vp.View()
	m.lastRefresh = time.Now().Add(-streamRefreshInterval)

	next, _ := m.Update(textMsg("流式增量"))
	got := next.(model)

	if got.vp.View() != beforeViewport {
		t.Fatalf("streaming text should not rewrite viewport content before final:\nbefore:\n%s\nafter:\n%s", beforeViewport, got.vp.View())
	}
	if !strings.Contains(got.View(), "流式增量") {
		t.Fatalf("streaming preview should still show the live answer:\n%s", got.View())
	}
}

func TestMetaDetailFormatsLangGraphNodeTiming(t *testing.T) {
	got := metaDetail(eventMeta{Runtime: "langgraph", Node: "execute_tools", Phase: "证据检索", ElapsedMS: 42, Retry: true})

	if got != "阶段 证据检索 · 42ms · 重试" {
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
		"重试",
		"42ms",
		"线程 tui-20260625T120000",
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
		"重试",
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
		"证据接地的科研文献智能体",
		"从一个论断",
		"输入 / 查看命令",
	} {
		if !strings.Contains(splash, want) {
			t.Fatalf("splash missing %q:\n%s", want, splash)
		}
	}
	for _, removed := range []string{
		"Quick actions",
		"黄金演示",
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
		"输入 /",
		"查看命令",
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
		"/",
	} {
		if !strings.Contains(composer, want) {
			t.Fatalf("composer missing %q:\n%s", want, composer)
		}
	}
	for _, removed := range []string{"session tui-test-session", "langgraph", "/retry", "Tab", "Ctrl"} {
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
		"命令启动器",
		"Enter 执行",
		"Esc 关闭",
		"/ 命令",
		"▶",
		"/demo",
		"/timeline",
		"/sessions",
		"黄金演示",
	} {
		if !strings.Contains(palette, want) {
			t.Fatalf("palette missing %q:\n%s", want, palette)
		}
	}
	for _, removed := range []string{"↑/↓", "Tab"} {
		if strings.Contains(palette, removed) {
			t.Fatalf("palette should keep shortcut hints minimal, found %q:\n%s", removed, palette)
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
		"最近会话",
		"/sessions",
	} {
		if !strings.Contains(palette, want) {
			t.Fatalf("filtered palette missing %q:\n%s", want, palette)
		}
	}
	if strings.Contains(palette, "黄金演示") {
		t.Fatalf("filtered palette should not include demo:\n%s", palette)
	}
}

func TestSlashCommandRegistryClassifiesCommandsByExecutionKind(t *testing.T) {
	for _, cmd := range slashCmds {
		registered, ok := slashRegistry[cmd.cmd]
		if !ok {
			t.Fatalf("command %s missing from registry", cmd.cmd)
		}
		if registered.kind == "" || registered.run == nil {
			t.Fatalf("command %s has incomplete registry metadata: %#v", cmd.cmd, registered)
		}
	}
	if slashRegistry["/theme"].kind != commandUI || slashRegistry["/theme"].submenu != "theme" {
		t.Fatalf("/theme should be a UI command with theme submenu: %#v", slashRegistry["/theme"])
	}
	if slashRegistry["/verify"].kind != commandPrompt || slashRegistry["/review"].kind != commandPrompt || slashRegistry["/trend"].kind != commandPrompt || slashRegistry["/recommend"].kind != commandPrompt {
		t.Fatalf("/verify, /review, /trend, and /recommend should be prompt commands")
	}
	if slashRegistry["/export"].kind != commandLocal {
		t.Fatalf("/export should be local command")
	}
}

func TestPromptSlashCommandExpandsIntoAgentQuestion(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	next, cmd := m.runSlash("/verify RAG 能降低幻觉")
	got := next.(model)

	if cmd == nil {
		t.Fatalf("expected /verify to start an agent stream")
	}
	if !got.answering {
		t.Fatalf("expected prompt command to enter answering state")
	}
	if got.lastQuestion == "RAG 能降低幻觉" || !strings.Contains(got.lastQuestion, "SciScope 技能: 论断核查") {
		t.Fatalf("expected /verify to expand the task, got %q", got.lastQuestion)
	}
	if len(got.history) == 0 || !strings.Contains(got.history[len(got.history)-1].Content, "RAG 能降低幻觉") {
		t.Fatalf("expected expanded question in history, got %#v", got.history)
	}
}

func TestSkillTemplateLoadsFromSciscopeDirectory(t *testing.T) {
	template, err := loadSkillTemplate("claim-check")
	if err != nil {
		t.Fatalf("expected claim-check skill template to load: %v", err)
	}
	if !strings.Contains(template, "{{input}}") {
		t.Fatalf("expected raw template placeholder, got %q", template)
	}

	rendered := renderSkillPrompt("claim-check", "RAG 能降低幻觉", "fallback")
	if !strings.Contains(rendered, "RAG 能降低幻觉") || strings.Contains(rendered, "{{input}}") {
		t.Fatalf("expected rendered skill prompt to inject input, got %q", rendered)
	}
}

func TestTrendSlashCommandUsesSkillTemplate(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	next, cmd := m.runSlash("/trend graph rag")
	got := next.(model)

	if cmd == nil {
		t.Fatalf("expected /trend to start an agent stream")
	}
	if !got.answering {
		t.Fatalf("expected /trend to enter answering state")
	}
	if !strings.Contains(got.lastQuestion, "SciScope 技能: 趋势分析") || !strings.Contains(got.lastQuestion, "graph rag") {
		t.Fatalf("expected /trend to render trend skill, got %q", got.lastQuestion)
	}
}

func TestRecommendSlashCommandUsesSkillTemplate(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	next, cmd := m.runSlash("/recommend graph rag")
	got := next.(model)

	if cmd == nil {
		t.Fatalf("expected /recommend to start an agent stream")
	}
	if !got.answering {
		t.Fatalf("expected /recommend to enter answering state")
	}
	if !strings.Contains(got.lastQuestion, "SciScope 技能: 论文推荐") || !strings.Contains(got.lastQuestion, "graph rag") {
		t.Fatalf("expected /recommend to render recommendation skill, got %q", got.lastQuestion)
	}
}

func TestSlashCommandOpensToolsDoctorAndConfirmSubmenus(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	next, _ := m.runSlash("/tools")
	got := next.(model)
	if got.submenu != "tools" {
		t.Fatalf("expected tools submenu, got %q", got.submenu)
	}
	if !strings.Contains(got.View(), "选择工具") {
		t.Fatalf("expected tools submenu in view:\n%s", got.View())
	}

	next, _ = got.Update(tea.KeyMsg{Type: tea.KeyEnter})
	got = next.(model)
	if !strings.Contains(got.vp.View(), "工具名:") {
		t.Fatalf("expected selected tool detail:\n%s", got.vp.View())
	}

	next, _ = got.runSlash("/doctor")
	got = next.(model)
	if got.submenu != "doctor" {
		t.Fatalf("expected doctor submenu, got %q", got.submenu)
	}
	if !strings.Contains(got.View(), "查看检查项") {
		t.Fatalf("expected doctor submenu in view:\n%s", got.View())
	}

	got.blocks = []string{"keep"}
	next, _ = got.runSlash("/clear")
	got = next.(model)
	if got.submenu != "clear" {
		t.Fatalf("expected clear submenu, got %q", got.submenu)
	}
	next, _ = got.Update(tea.KeyMsg{Type: tea.KeyEnter})
	got = next.(model)
	if len(got.blocks) == 0 || !strings.Contains(got.blocks[len(got.blocks)-1], "已取消清空") {
		t.Fatalf("clear cancel should preserve blocks and append notice: %#v", got.blocks)
	}
}

func TestSlashCommandOpensResumeSubmenuAndExecutesSelection(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("SCISCOPE_SESSION_DIR", dir)
	path, err := writeSessionMarkdown(dir, []transcriptEvent{{Kind: "user", Content: "核查 RAG 是否降低幻觉"}}, time.Now())
	if err != nil {
		t.Fatalf("write session: %v", err)
	}
	_ = path

	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.ti.SetValue("/")
	for i, cmd := range filterCmds("/") {
		if cmd.cmd == "/resume" {
			m.menuIdx = i
			break
		}
	}

	next, _ := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	got := next.(model)
	if got.submenu != "resume" {
		t.Fatalf("expected resume submenu, got %q", got.submenu)
	}
	if !strings.Contains(got.View(), "恢复会话") {
		t.Fatalf("expected resume submenu in view:\n%s", got.View())
	}
	next, _ = got.Update(tea.KeyMsg{Type: tea.KeyEnter})
	got = next.(model)
	if got.submenu != "" {
		t.Fatalf("submenu should close after resume")
	}
	if !strings.Contains(got.vp.View(), "已恢复会话") {
		t.Fatalf("expected restored session output:\n%s", got.vp.View())
	}
}

func TestSlashCommandOpensThemeSubmenuAndExecutesSelection(t *testing.T) {
	applyTheme("dark")
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.ti.SetValue("/")
	for i, cmd := range filterCmds("/") {
		if cmd.cmd == "/theme" {
			m.menuIdx = i
			break
		}
	}

	next, _ := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	got := next.(model)
	if got.submenu != "theme" {
		t.Fatalf("expected theme submenu, got %q", got.submenu)
	}
	if !strings.Contains(got.View(), "选择主题") {
		t.Fatalf("expected submenu palette in view:\n%s", got.View())
	}
	got.submenuIdx = 1 // paper
	next, _ = got.Update(tea.KeyMsg{Type: tea.KeyEnter})
	got = next.(model)
	if currentTheme != "paper" {
		t.Fatalf("expected paper theme after submenu enter, got %q", currentTheme)
	}
	if got.submenu != "" {
		t.Fatalf("submenu should close after execution")
	}
}

func TestThemeCommandListsAndSwitchesThemes(t *testing.T) {
	applyTheme("dark")
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)

	next, _ := m.runSlash("/theme")
	got := next.(model)
	if !strings.Contains(got.vp.View(), "paper") {
		t.Fatalf("/theme should list available themes:\n%s", got.vp.View())
	}

	next, _ = got.runSlash("/theme paper")
	got = next.(model)
	if currentTheme != "paper" {
		t.Fatalf("expected current theme paper, got %q", currentTheme)
	}
	if !strings.Contains(got.vp.View(), "已切换主题: paper") {
		t.Fatalf("/theme paper should confirm switch:\n%s", got.vp.View())
	}
}

func TestThemeCommandRerendersQuestionAndAnswerBlocks(t *testing.T) {
	applyTheme("dark")
	m := initialModel()
	m.ready = true
	m.vp = viewport.New(100, 20)
	m.appendUserMessage("核查 RAG", false)
	m.appendAnswerMessage("结论: RAG 能降低无依据回答风险。", []string{"verify_claim"})
	beforeUserVersion := m.blockItems[0].RenderVersion
	beforeAnswerVersion := m.blockItems[1].RenderVersion

	next, _ := m.runSlash("/theme paper")
	got := next.(model)

	if currentTheme != "paper" {
		t.Fatalf("expected current theme paper, got %q", currentTheme)
	}
	if got.blockItems[0].RenderVersion <= beforeUserVersion {
		t.Fatalf("theme switch should rerender existing user block, version %d -> %d", beforeUserVersion, got.blockItems[0].RenderVersion)
	}
	if got.blockItems[1].RenderVersion <= beforeAnswerVersion {
		t.Fatalf("theme switch should rerender existing answer block, version %d -> %d", beforeAnswerVersion, got.blockItems[1].RenderVersion)
	}
	plain := plainANSI(got.vp.View())
	for _, want := range []string{"用户问题", "研究结论", "核查 RAG", "RAG 能降低"} {
		if !strings.Contains(plain, want) {
			t.Fatalf("rerendered themed view missing %q:\n%s", want, got.vp.View())
		}
	}
}

func TestApplyThemeRejectsUnknownTheme(t *testing.T) {
	applyTheme("dark")
	if applyTheme("not-a-theme") {
		t.Fatalf("unknown theme should be rejected")
	}
	if currentTheme != "dark" {
		t.Fatalf("rejected theme should not change current theme, got %q", currentTheme)
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

func TestPlanAndReflectStreamInlineAndUpdateLiveState(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = viewport.New(100, 20)

	next, _ := m.Update(planMsg{"检索证据", "综合回答"})
	got := next.(model)
	if len(got.blocks) != 1 {
		t.Fatalf("plan should stream inline as one block: %#v", got.blocks)
	}
	if len(got.livePlan) != 2 {
		t.Fatalf("expected live plan to update, got %#v", got.livePlan)
	}

	next, _ = got.Update(reflectMsg("需要补充证据"))
	got = next.(model)
	if len(got.blocks) != 2 {
		t.Fatalf("reflect should stream inline as another block: %#v", got.blocks)
	}
	if got.liveReflect != "需要补充证据" {
		t.Fatalf("expected live reflect to update, got %q", got.liveReflect)
	}
	if !strings.Contains(got.View(), "需要补充证据") {
		t.Fatalf("view should show reflect:\n%s", got.View())
	}
}

func TestToolEventsStreamInlineAndAppearInTimeline(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.answering = true
	m.vp = viewport.New(100, 20)

	next, _ := m.Update(toolCallMsg{name: "search_literature", args: map[string]any{"query": "RAG"}})
	got := next.(model)
	if len(got.blocks) != 1 {
		t.Fatalf("tool call should stream inline as one block: %#v", got.blocks)
	}

	next, _ = got.Update(toolResultMsg{name: "search_literature", result: `[{"paper_id":"W1","标题":"RAG","年份":2025}]`})
	got = next.(model)
	if len(got.blocks) != 2 {
		t.Fatalf("tool result should stream inline as another block: %#v", got.blocks)
	}
	if len(got.timeline) < 2 {
		t.Fatalf("tool events should also be available in timeline: %#v", got.timeline)
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
		"研究结论",
		"结论",
		"RAG 能降低",
		"/timeline 查看过程",
		"论断核查",
		"证据工具",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("answer message missing %q:\n%s", want, rendered)
		}
	}
	if strings.Contains(plain, "╭─ answer") {
		t.Fatalf("answer should not render as isolated card:\n%s", rendered)
	}
}

func TestUserAndAssistantMessagesHaveDistinctLabels(t *testing.T) {
	applyTheme("dark")
	user := renderUserMessage("核查 RAG 是否降低幻觉", false)
	assistant := renderAnswerMessage("结论: 可以降低无依据回答风险。", []string{"verify_claim"}, 100)
	userPlain := plainANSI(user)
	assistantPlain := plainANSI(assistant)

	if !strings.Contains(userPlain, "用户问题") || !strings.Contains(userPlain, "核查 RAG") {
		t.Fatalf("user message should be clearly labelled:\n%s", user)
	}
	if strings.Contains(userPlain, "研究结论") {
		t.Fatalf("user message should not look like assistant answer:\n%s", user)
	}
	for _, want := range []string{"研究结论", "可以降低", "证据工具", "论断核查"} {
		if !strings.Contains(assistantPlain, want) {
			t.Fatalf("assistant message missing %q:\n%s", want, assistant)
		}
	}
	if strings.Contains(assistantPlain, "用户问题") {
		t.Fatalf("assistant message should not look like user prompt:\n%s", assistant)
	}
}

func TestStyleAnswerBodyHighlightsSemanticLines(t *testing.T) {
	applyTheme("paper")
	body := styleAnswerBody("结论: RAG 有帮助\n证据: [1] 2025 年论文\n风险: 但取决于检索质量\n推荐相似度 0.8918")
	plain := plainANSI(body)
	for _, want := range []string{"结论", "证据", "[1]", "风险", "0.8918"} {
		if !strings.Contains(plain, want) {
			t.Fatalf("styled answer missing %q:\n%s", want, body)
		}
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

func TestBackendURLDefaultsToHostedEndpoint(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "")
	t.Setenv("SCISCOPE_HOSTED_BACKEND", "https://api.example.test/")

	got := backendURL()

	if got != "https://api.example.test" {
		t.Fatalf("backendURL() = %q, want hosted endpoint", got)
	}
}

func TestBackendURLLocalOverrideWins(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "http://127.0.0.1:8000/")
	t.Setenv("SCISCOPE_HOSTED_BACKEND", "https://api.example.test")

	got := backendURL()

	if got != "http://127.0.0.1:8000/" {
		t.Fatalf("backendURL() = %q, want explicit local override", got)
	}
}

func TestBackendURLDefaultHostedLdflagFallback(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "")
	t.Setenv("SCISCOPE_HOSTED_BACKEND", "")
	old := defaultHostedBackendURL
	t.Cleanup(func() {
		defaultHostedBackendURL = old
	})
	defaultHostedBackendURL = " https://release.example.test/ "

	got := backendURL()

	if got != "https://release.example.test" {
		t.Fatalf("backendURL() = %q, want trimmed ldflag hosted endpoint", got)
	}
}

func TestBackendModeLabelsHostedAndLocal(t *testing.T) {
	if got := backendMode("https://api.example.test"); got != "hosted" {
		t.Fatalf("backendMode(hosted) = %q", got)
	}
	if got := backendMode("http://127.0.0.1:8000"); got != "local" {
		t.Fatalf("backendMode(local) = %q", got)
	}
	if got := backendMode("http://[::1]:8000"); got != "local" {
		t.Fatalf("backendMode(ipv6 local) = %q", got)
	}
	if got := backendMode("https://api.example.test/proxy/localhost"); got != "hosted" {
		t.Fatalf("backendMode(path mentions localhost) = %q", got)
	}
	if got := backendMode("https://127.0.0.1.example.com"); got != "hosted" {
		t.Fatalf("backendMode(hostname contains local IP) = %q", got)
	}
	if got := backendMode("not localhost"); got != "hosted" {
		t.Fatalf("backendMode(malformed hosted) = %q", got)
	}
	if got := backendMode("localhost"); got != "local" {
		t.Fatalf("backendMode(raw localhost) = %q", got)
	}
}

func TestHelpStringDocumentsHostedBackendDefault(t *testing.T) {
	help := helpString()

	if strings.Contains(help, "default http://127.0.0.1:8000") {
		t.Fatalf("help should not document localhost as default:\n%s", help)
	}
	if !strings.Contains(help, "SCISCOPE_HOSTED_BACKEND") && !strings.Contains(strings.ToLower(help), "hosted") {
		t.Fatalf("help should document hosted backend default:\n%s", help)
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
		"Enter",
		"Esc",
		"/",
	} {
		if !strings.Contains(composer, want) {
			t.Fatalf("composer missing %q:\n%s", want, composer)
		}
	}
	for _, removed := range []string{"agent", "langgraph", "/retry", "Tab", "Ctrl"} {
		if strings.Contains(composer, removed) {
			t.Fatalf("composer should stay minimal, found %q:\n%s", removed, composer)
		}
	}
}

func TestPaletteStagesArgCommandTemplate(t *testing.T) {
	rec := slashCmd{cmd: "/recommend", key: "recommend <topic|paper_id>"}
	demo := slashCmd{cmd: "/demo", key: "demo"}
	if !commandNeedsArg(rec) {
		t.Fatal("/recommend (usage has <...>) should need an argument")
	}
	if commandNeedsArg(demo) {
		t.Fatal("/demo should not need an argument")
	}

	// An arg command is staged as "/recommend <>" with the cursor between < and >.
	m := stageCommand(initialModel(), rec)
	if got := m.ti.Value(); got != "/recommend <>" {
		t.Fatalf("staged value = %q, want %q", got, "/recommend <>")
	}
	if pos, want := m.ti.Position(), len("/recommend <>")-1; pos != want {
		t.Fatalf("cursor at %d, want %d (between < and >)", pos, want)
	}

	// An argument-less command just completes to the bare command.
	if got := stageCommand(initialModel(), demo).ti.Value(); got != "/demo" {
		t.Fatalf("staged value = %q, want %q", got, "/demo")
	}
}

func TestStripPlaceholderArgument(t *testing.T) {
	cases := []struct {
		in   []string
		want string
	}{
		{[]string{"<graph", "nn>"}, "graph|nn"}, // typed inside the staged <>
		{[]string{"<>"}, ""},                    // untouched placeholder -> empty arg
		{[]string{"graph", "nn"}, "graph|nn"},   // typed without brackets
		{nil, ""},
	}
	for _, c := range cases {
		if got := strings.Join(stripPlaceholder(c.in), "|"); got != c.want {
			t.Fatalf("stripPlaceholder(%v) = %q, want %q", c.in, got, c.want)
		}
	}
}
