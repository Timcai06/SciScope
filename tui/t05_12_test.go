package main

import (
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func setTrueColor(t *testing.T) {
	t.Helper()
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	t.Cleanup(func() { lipgloss.SetColorProfile(prev) })
	applyTheme("dark")
}

// ---- 提示词核心目标 1：对话历史由语义化 Block 驱动，不保存 ANSI ----

func TestSemanticBlocksStoreNoANSI(t *testing.T) {
	m := initialModel()
	m.ready = true
	m.vp.Width, m.vp.Height = 100, 20

	// plan：PlanSteps 结构化，Raw 纯文本，无 ANSI。
	next, _ := m.Update(planMsg{"解析问题", "检索证据"})
	m = next.(model)
	if len(m.blockItems) == 0 {
		t.Fatal("plan should create a block")
	}
	if got := m.blockItems[0].Raw; strings.Contains(got, "\x1b[") || !strings.Contains(got, "解析问题") {
		t.Fatalf("plan Raw should be pure text, got %q", got)
	}
	if len(m.blockItems[0].PlanSteps) != 2 {
		t.Fatalf("plan should store PlanSteps, got %v", m.blockItems[0].PlanSteps)
	}

	// tool call：ToolName/ToolArgs 结构化，Raw 空（渲染层负责）。
	next, _ = m.Update(toolCallMsg{name: "search_literature", args: map[string]any{"query": "RAG"}})
	m = next.(model)
	call := m.blockItems[len(m.blockItems)-1]
	if call.Kind != BlockToolCall || call.Status != BlockRunning {
		t.Fatalf("tool call should create running block, got %+v", call)
	}
	if call.ToolName != "search_literature" {
		t.Fatalf("tool name not stored: %q", call.ToolName)
	}
	if strings.Contains(call.Raw, "\x1b[") {
		t.Fatalf("tool call Raw must not contain ANSI, got %q", call.Raw)
	}

	// tool result：转正 succeeded，摘要并入 tool 行，无日志式结果块。
	papers := `[{"paper_id":"W123456","标题":"RAG 综述","年份":2020,"作者":["A"]}]`
	next, _ = m.Update(toolResultMsg{name: "search_literature", result: papers})
	m = next.(model)
	done := m.blockItems[len(m.blockItems)-2]
	if done.Status != BlockSucceeded {
		t.Fatalf("tool should transition to succeeded, got %s", done.Status)
	}
	if !strings.Contains(done.ToolSummary, "1 篇论文") {
		t.Fatalf("summary missing, got %q", done.ToolSummary)
	}
	rendered := renderConversationBlock(done, 100)
	if !strings.Contains(stripANSI(rendered), "✓") {
		t.Fatalf("succeeded tool should render ✓:\n%s", rendered)
	}
}

func TestToolCallFailedLifecycle(t *testing.T) {
	m := initialModel()
	m.ready = true
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	next, _ = m.Update(toolCallMsg{name: "verify_claim", args: map[string]any{"claim": "x"}})
	m = next.(model)
	next, _ = m.Update(toolResultMsg{name: "verify_claim", result: "[未执行]伪造 paper_id"})
	m = next.(model)
	var call *ScrollbackBlock
	for i := range m.blockItems {
		if m.blockItems[i].Kind == BlockToolCall {
			call = &m.blockItems[i]
		}
	}
	if call == nil {
		t.Fatal("no tool block")
	}
	if call.Status != BlockFailed {
		t.Fatalf("validation gate should mark failed, got %s", call.Status)
	}
	if !strings.Contains(call.ToolSummary, "伪造 paper_id") {
		t.Fatalf("failed summary missing, got %q", call.ToolSummary)
	}
	rendered := renderConversationBlock(*call, 100)
	if !strings.Contains(stripANSI(rendered), "✗") {
		t.Fatalf("failed tool should render ✗:\n%s", rendered)
	}
}

// ---- 提示词交互优化：搜索（ctrl+f）与 block 选择（ctrl+g）----

func TestSearchModeFindAndJump(t *testing.T) {
	setTrueColor(t)
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 12})
	m = next.(model)
	// 填充足够行使 viewport 可滚动，目标行落在视口外。
	m = fillBlocks(t, m)
	m.appendBlock(BlockUser, "RAG 问题")
	m.appendBlock(BlockSystem, "证据链")
	m.appendBlock(BlockAnswer, "结论")
	m.refresh()
	m.vp.GotoTop()

	// ctrl+f 进入搜索模式
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlF})
	m = next.(model)
	if !m.searchMode {
		t.Fatal("ctrl+f should enter search mode")
	}
	// 输入关键词（rune 消息）
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("证据")})
	m = next.(model)
	if m.searchQuery != "证据" {
		t.Fatalf("query = %q", m.searchQuery)
	}
	m.computeSearchMatches()
	if len(m.searchMatches) == 0 {
		t.Fatal("should match 证据 chain line")
	}
	// Enter 跳转下一个匹配（viewport clamp 到最大可滚动位置）。
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = next.(model)
	want := m.searchMatches[0]
	if max := len(strings.Split(m.viewportContent, "\n")) - m.vp.Height; want > max {
		want = max
	}
	if m.vp.YOffset != want {
		t.Fatalf("Enter should jump to match line %d (clamped), got %d", want, m.vp.YOffset)
	}
	// 搜索框渲染
	box := m.renderSearchBox(100)
	if !strings.Contains(box, "证据") {
		t.Fatalf("search box missing query:\n%s", box)
	}
	// Esc 退出
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = next.(model)
	if m.searchMode || m.searchQuery != "" {
		t.Fatal("esc should exit search mode")
	}
}

func TestSelectModeNavigateAndFold(t *testing.T) {
	setTrueColor(t)
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	m.appendBlock(BlockUser, "问题一")
	m.appendBlock(BlockResearchPlan, strings.Join([]string{"步骤一", "步骤二"}, "\n"))
	m.appendBlock(BlockAnswer, "答案一")
	m.refresh()

	// ctrl+g 进入选择模式，默认定位最近块
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlG})
	m = next.(model)
	if !m.selectMode {
		t.Fatal("ctrl+g should enter select mode")
	}
	if m.selectIdx != len(m.blockItems)-1 {
		t.Fatalf("selectIdx = %d, want %d", m.selectIdx, len(m.blockItems)-1)
	}
	// up 移动到上一个块（plan）
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	m = next.(model)
	if m.selectIdx != len(m.blockItems)-2 {
		t.Fatalf("up should move to previous block, got %d", m.selectIdx)
	}
	// Enter 折叠 plan 块
	planBlock := m.blockItems[m.selectIdx]
	if planBlock.Expanded != true {
		t.Fatal("plan should start expanded")
	}
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = next.(model)
	if m.blockItems[m.selectIdx].Expanded {
		t.Fatal("enter should collapse selected block")
	}
	// Esc 退出
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = next.(model)
	if m.selectMode {
		t.Fatal("esc should exit select mode")
	}
}

// ---- 提示词 Composer：multiline（Shift+Enter）与历史（↑/↓）----

func TestComposerShiftEnterInsertsNewline(t *testing.T) {
	m := initialModel()
	m.ti.SetValue("第一行")
	next, _ := m.Update(tea.KeyMsg{Type: tea.KeyCtrlJ})
	m = next.(model)
	if !strings.Contains(m.ti.Value(), "\n") {
		t.Fatalf("ctrl+j should insert newline, got %q", m.ti.Value())
	}
	// Enter 仍是发送（不插入换行）
	before := m.ti.Value()
	m.ti.SetValue("问题")
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = next.(model)
	if m.ti.Value() != "" {
		t.Fatalf("enter should send (clear composer), got %q", m.ti.Value())
	}
	if before == m.ti.Value() {
		t.Fatal("sanity")
	}
}

func TestComposerHistoryBrowse(t *testing.T) {
	m := initialModel()
	m.pushHistory("核查 RAG 综述")
	m.pushHistory("对比两篇论文")
	// 有内容时 up 进入历史
	m.ti.SetValue("新输入")
	next, _ := m.Update(tea.KeyMsg{Type: tea.KeyUp})
	m = next.(model)
	if m.ti.Value() != "对比两篇论文" {
		t.Fatalf("up should browse newest history, got %q", m.ti.Value())
	}
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	m = next.(model)
	if m.ti.Value() != "核查 RAG 综述" {
		t.Fatalf("second up should go older, got %q", m.ti.Value())
	}
	// down 回到草稿
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = next.(model)
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = next.(model)
	if m.ti.Value() != "新输入" {
		t.Fatalf("down back should restore draft, got %q", m.ti.Value())
	}
	// 去重
	m.pushHistory("对比两篇论文")
	if n := len(m.inputHistory); n != 2 {
		t.Fatalf("duplicate should be deduped, got %d entries", n)
	}
}

// ---- 提示词布局：三档响应式 ----

func TestLayoutTiers(t *testing.T) {
	cases := []struct {
		width int
		want  layoutTier
	}{
		{40, tierCompact},
		{60, tierCompact},
		{64, tierNormal},
		{80, tierNormal},
		{110, tierNormal},
		{120, tierWide},
		{160, tierWide},
	}
	for _, c := range cases {
		if got := layoutTierFor(c.width); got != c.want {
			t.Fatalf("layoutTierFor(%d) = %v, want %v", c.width, got, c.want)
		}
	}
}

// ---- 语义化：evidence 块 Raw 存 JSON 原文，渲染层解析 ----

func TestEvidenceBlockStoresRawJSON(t *testing.T) {
	setTrueColor(t)
	m := initialModel()
	m.ready = true
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	next, _ = m.Update(toolCallMsg{name: "search_literature", args: map[string]any{"query": "RAG"}})
	m = next.(model)
	papers := `[{"paper_id":"W123456","标题":"RAG 综述","年份":2020,"作者":["A"],"摘要片段":"..."}]`
	next, _ = m.Update(toolResultMsg{name: "search_literature", result: papers})
	m = next.(model)
	var ev *ScrollbackBlock
	for i := range m.blockItems {
		if m.blockItems[i].Kind == BlockEvidence {
			ev = &m.blockItems[i]
		}
	}
	if ev == nil {
		t.Fatal("evidence tool should produce BlockEvidence")
	}
	if strings.Contains(ev.Raw, "\x1b[") {
		t.Fatalf("evidence Raw must be JSON not ANSI, got %q", ev.Raw)
	}
	rendered := renderConversationBlock(*ev, 100)
	if !strings.Contains(stripANSI(rendered), "RAG 综述") {
		t.Fatalf("evidence card should render from JSON:\n%s", rendered)
	}
}

// ---- 状态栏：一行合并，嵌入输入框边框内底部（grok prompt_widget）----

func TestStatusLineSingleLineWhileAnswering(t *testing.T) {
	setTrueColor(t)
	m := initialModel()
	m.answering = true
	m.verb = "正在核查证据"
	m.start = time.Now().Add(-8 * time.Second)
	composer := m.renderComposer(96)
	if strings.Count(composer, "\n") != 4 {
		t.Fatalf("composer should be 4 lines (border+2+input+hint), got %d:\n%q", strings.Count(composer, "\n"), composer)
	}
	hint := m.renderComposerHint(96)
	if strings.Count(hint, "\n") != 0 {
		t.Fatalf("hint must be one line:\n%q", hint)
	}
	if !strings.Contains(hint, "8s") {
		t.Fatalf("hint should show elapsed, got %q", hint)
	}
	if !strings.Contains(hint, "Esc 取消") {
		t.Fatalf("hint should show cancel, got %q", hint)
	}
}
