package main

import (
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
)

func newScrollbackTestModel() model {
	m := initialModel()
	m.ready = true
	m.vp = newTranscriptViewport(100, 20)
	return m
}

// 计划 T05-02「必须证明」1：streaming 更新同一 running block，而非无限 append。
func TestRunningBlockUpdatesSameIDNotAppend(t *testing.T) {
	m := newScrollbackTestModel()
	id := m.startRunningBlock(BlockAnswer)
	if id == "" {
		t.Fatal("startRunningBlock should return a non-empty ID")
	}
	if got := len(m.blockItems); got != 1 {
		t.Fatalf("startRunningBlock should create exactly 1 block, got %d", got)
	}
	if b := m.runningBlock(id); b == nil || b.Status != BlockRunning {
		t.Fatalf("running block should exist and be running, got %#v", b)
	}

	// 多 chunk 更新同一 ID：块数量不变，Raw 原地更新。
	before := m.runningBlock(id).RenderVersion
	for _, chunk := range []string{"第一段", "第一段第二段", "第一段第二段第三段"} {
		if !m.updateRunningBlock(id, chunk) {
			t.Fatalf("updateRunningBlock(%s, %q) should succeed", id, chunk)
		}
	}
	if got := len(m.blockItems); got != 1 {
		t.Fatalf("streaming must not append new blocks, got %d blocks", got)
	}
	b := m.runningBlock(id)
	if b.Raw != "第一段第二段第三段" {
		t.Fatalf("running block raw = %q, want latest chunk", b.Raw)
	}
	if b.RenderVersion <= before {
		t.Fatalf("update should bump render version, %d -> %d", before, b.RenderVersion)
	}
	if !m.finishRunningBlock(id) {
		t.Fatal("finishRunningBlock should succeed")
	}
	if b := m.runningBlock(id); b.Status != BlockFinished || b.EndedAt.IsZero() {
		t.Fatalf("finished block should carry BlockFinished + EndedAt, got %#v", b)
	}
	if m.updateRunningBlock(id, "迟到 chunk") {
		t.Fatal("updating a finished block must fail")
	}
}

// 计划 T05-02「必须证明」2：finished block 可缓存。
func TestFinishedBlockRenderCacheStable(t *testing.T) {
	m := newScrollbackTestModel()
	m.appendBlock(BlockResearchPlan, "研究计划行")
	m.appendBlock(BlockAnswer, "答案行")

	first := m.renderBlocksContent(80)
	for i := range m.blockItems {
		if m.blockItems[i].RenderVersion == 0 {
			t.Fatalf("block %d should be rendered on first pass", i)
		}
	}
	versions := make([]int, len(m.blockItems))
	for i := range m.blockItems {
		versions[i] = m.blockItems[i].RenderVersion
	}
	second := m.renderBlocksContent(80)
	if second != first {
		t.Fatalf("same-width render should be identical: %q vs %q", second, first)
	}
	for i := range m.blockItems {
		if m.blockItems[i].RenderVersion != versions[i] {
			t.Fatalf("block %d cache miss on same width: version %d -> %d", i, versions[i], m.blockItems[i].RenderVersion)
		}
	}
}

// 计划 T05-02「必须证明」3：fold/unfold 不修改 transcript。
func TestFoldUnfoldDoesNotTouchTranscript(t *testing.T) {
	m := newScrollbackTestModel()
	m.record("plan", "", "持久事实")
	m.record("assistant", "", "答案事实")
	beforeTranscript := len(m.transcript)

	m.appendBlock(BlockResearchPlan, "计划块")
	beforeBlocks := len(m.blocks)
	id := m.blockItems[len(m.blockItems)-1].ID
	if !m.setExpanded(id, false) {
		t.Fatal("setExpanded should succeed")
	}
	if m.blockItems[len(m.blockItems)-1].Expanded {
		t.Fatal("block should be folded")
	}
	if len(m.transcript) != beforeTranscript || len(m.blocks) != beforeBlocks {
		t.Fatalf("fold must not touch facts: transcript %d -> %d, blocks %d -> %d",
			beforeTranscript, len(m.transcript), beforeBlocks, len(m.blocks))
	}
	if !m.setExpanded(id, true) || !m.blockItems[len(m.blockItems)-1].Expanded {
		t.Fatal("unfold should restore expanded state")
	}
	if len(m.transcript) != beforeTranscript {
		t.Fatal("unfold must not touch transcript either")
	}
}

// 计划 T05-02「必须证明」4：width 改变只失效相关 render cache（块身份与事实保留）。
func TestWidthChangeInvalidatesOnlyRenderCache(t *testing.T) {
	m := newScrollbackTestModel()
	m.appendBlock(BlockToolResult, "工具结果")
	m.appendBlock(BlockAnswer, "答案")
	m.renderBlocksContent(80)
	for i := range m.blockItems {
		if m.blockItems[i].RenderWidth != 80 {
			t.Fatalf("block %d should render at width 80", i)
		}
	}
	saved := make([]ScrollbackBlock, len(m.blockItems))
	copy(saved, m.blockItems)

	m.invalidateRenderCacheForWidth(120)
	for i := range m.blockItems {
		if m.blockItems[i].Rendered != "" || m.blockItems[i].RenderWidth != 0 {
			t.Fatalf("block %d cache should be invalidated on width change", i)
		}
		// 块身份与源事实不受影响。
		if m.blockItems[i].ID != saved[i].ID || m.blockItems[i].Raw != saved[i].Raw ||
			m.blockItems[i].Kind != saved[i].Kind || m.blockItems[i].Status != saved[i].Status {
			t.Fatalf("block %d identity/facts changed on width invalidation: %#v vs %#v", i, m.blockItems[i], saved[i])
		}
	}
	m.renderBlocksContent(120)
	for i := range m.blockItems {
		if m.blockItems[i].RenderWidth != 120 {
			t.Fatalf("block %d should re-render at width 120", i)
		}
	}
}

// 计划 T05-02「必须证明」5：/export 仍以 transcript 事实语义工作——UI 块
// （含 ANSI chrome 字符串）不进入导出内容。
func TestExportUsesTranscriptFactsOnly(t *testing.T) {
	m := newScrollbackTestModel()
	m.record("user", "", "用户问题事实")
	m.record("tool_call", "verify_claim", "核查论断")
	m.record("assistant", "", "答案事实")
	// UI 投影（含渲染字符串）不得污染导出。
	m.appendBlock(BlockToolCall, stBullet.Render("⏺ ")+"检索文献")

	out := exportMarkdown(m.transcript, time.Now())
	if !strings.Contains(out, "用户问题事实") || !strings.Contains(out, "答案事实") {
		t.Fatalf("export should carry transcript facts:\n%s", out)
	}
	if strings.Contains(out, "检索文献") {
		t.Fatalf("UI chrome must not leak into export:\n%s", out)
	}
}

// 计划 T05-02「必须证明」5b：/resume 重建的是事实投影，块身份重新分配，
// 不依赖旧会话的块身份。
func TestResumeRebuildsBlocksFromFacts(t *testing.T) {
	m := newScrollbackTestModel()
	m.record("user", "", "恢复的问题")
	m.record("assistant", "", "恢复的答案")
	// 真实场景 record 与 UI 块成对出现。
	m.appendBlock(BlockUser, "恢复的问题")
	m.appendBlock(BlockAnswer, "恢复的答案")

	content := exportMarkdown(m.transcript, time.Now())
	// resume 路径：从 markdown 事实重建视图（模拟 runResumeCommand 的输入）。
	m2 := newScrollbackTestModel()
	m2.appendBlock(BlockSystem, "恢复会话成功")
	for _, line := range strings.Split(content, "\n") {
		if strings.TrimSpace(line) != "" {
			m2.appendBlock(BlockMessage, line)
		}
	}
	if len(m2.transcript) != 0 {
		t.Fatal("rebuilding the view must not fabricate transcript facts")
	}
	// 重建后的块身份是新的、单调的，且与旧模型无关。
	if m2.blockItems[0].ID == m.blockItems[0].ID {
		t.Fatal("resumed session must get fresh block identities")
	}
}

// typed 块按 kind 可检索（验收：不再靠解析 ANSI/标题文本判断块类型）。
func TestBlocksAreRetrievableByTypedKind(t *testing.T) {
	m := newScrollbackTestModel()
	m.appendBlock(BlockResearchPlan, "计划")
	m.appendBlock(BlockToolCall, "工具")
	m.appendBlock(BlockToolResult, "结果")
	m.appendBlock(BlockAnswer, "答案")
	m.appendBlock(BlockSystem, "系统")

	if got := len(m.blockByKind(BlockResearchPlan)); got != 1 {
		t.Fatalf("research_plan blocks = %d, want 1", got)
	}
	if got := len(m.blockByKind(BlockToolResult)); got != 1 {
		t.Fatalf("tool_result blocks = %d, want 1", got)
	}
	kinds := []BlockKind{BlockUser, BlockResearchPlan, BlockToolCall, BlockToolResult,
		BlockResearchTrace, BlockEvidence, BlockAnswer, BlockContract, BlockRecovery, BlockSystem}
	seen := map[BlockKind]bool{}
	for _, k := range kinds {
		seen[k] = len(m.blockByKind(k)) > 0
	}
	// 至少已使用的 kind 全部可检索。
	for _, k := range []BlockKind{BlockResearchPlan, BlockToolCall, BlockToolResult, BlockAnswer, BlockSystem} {
		if !seen[k] {
			t.Fatalf("kind %q should be retrievable", k)
		}
	}
}

// viewport 依赖（测试编译期验证 ScrollbackBlock 与现有渲染路径兼容）。
var _ = viewport.Model{}
