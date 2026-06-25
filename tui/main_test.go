package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRenderToolResultSearchLiteratureAsEvidenceCards(t *testing.T) {
	result := `[
		{"paper_id":"W1","标题":"Retrieval-Augmented Generation","年份":2025,"作者":["Ada","Bo"],"摘要片段":"RAG grounds answers in retrieved evidence."},
		{"paper_id":"W2","标题":"Knowledge Graph Retrieval","年份":2024,"作者":["Chen"],"摘要片段":"Graph evidence improves retrieval."}
	]`

	rendered := renderToolResult("search_literature", result, 120, 0)

	for _, want := range []string{
		"证据卡 2 篇",
		"Retrieval-Augmented Generation",
		"W1 · 2025 · Ada, Bo",
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
		"论断核查 · 强支持 · 0.846",
		"检索增强生成能够降低幻觉",
		"Retrieval-Augmented Generation and Hallucination",
		"W4411065983 · 2025 · 相似度 0.846",
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
