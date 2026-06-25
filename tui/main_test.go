package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

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
		{Kind: "plan", Label: "执行计划", Detail: "检索相关论文"},
		{Kind: "tool_call", Tool: "search_literature", Label: "检索文献", Detail: "RAG hallucination"},
		{Kind: "tool_result", Tool: "search_literature", Label: "证据卡 2 篇", Duration: 1200 * time.Millisecond},
		{Kind: "final", Label: "回答完成"},
	}

	md := renderTimelineMarkdown(events)

	for _, want := range []string{
		"## 工具调用时间线",
		"1. 执行计划: 检索相关论文",
		"2. 检索文献: RAG hallucination",
		"3. 证据卡 2 篇 (1.2s)",
		"4. 回答完成",
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
		{Kind: "tool_call", Label: "检索文献", Detail: "RAG"},
		{Kind: "final", Label: "回答完成"},
	})
	if !strings.Contains(timeline, "╭─ timeline · 工具调用时间线") {
		t.Fatalf("timeline should use panel row grammar:\n%s", timeline)
	}
	if !strings.Contains(timeline, "│  [1] 检索文献 · RAG") {
		t.Fatalf("timeline missing dense row:\n%s", timeline)
	}

	errPanel := renderRecoveryPanel("无法连接后端: connection refused")
	if !strings.Contains(errPanel, "╭─ recovery · 后端未连接") {
		t.Fatalf("recovery should use panel row grammar:\n%s", errPanel)
	}
	if !strings.Contains(errPanel, "make backend") {
		t.Fatalf("recovery panel missing command:\n%s", errPanel)
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
		"Quick actions",
		"Golden demo",
		"Recent work",
		"verify_claim",
		"/sessions",
		"/demo",
		"可验证证据",
	} {
		if !strings.Contains(splash, want) {
			t.Fatalf("splash missing %q:\n%s", want, splash)
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
		"/demo",
		"/sessions",
		"verify_claim",
	} {
		if !strings.Contains(splash, want) {
			t.Fatalf("compact splash missing %q:\n%s", want, splash)
		}
	}
}

func TestComposerRendersPolishedInputBox(t *testing.T) {
	m := initialModel()
	m.ti.SetValue("核查 RAG")
	composer := m.renderComposer(96)

	for _, want := range []string{
		"╭─ ask · SciScope",
		"│",
		"核查 RAG",
		"/help",
		"/sessions",
		"Enter 发送",
	} {
		if !strings.Contains(composer, want) {
			t.Fatalf("composer missing %q:\n%s", want, composer)
		}
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

	for _, want := range []string{
		"Recent work",
		"/resume 1",
		"核查 RAG",
		"是否降低幻觉",
		"06-25 13:00",
	} {
		if !strings.Contains(splash, want) {
			t.Fatalf("splash missing recent session %q:\n%s", want, splash)
		}
	}
}
