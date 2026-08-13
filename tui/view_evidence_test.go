package main

import (
	"os"
	"regexp"
	"strings"
	"testing"
	"time"
)

// view_evidence_test.go — T05-06 Evidence / Claim / Answer Contract 纯函数
// 渲染层测试。全部测试只调用 view_evidence.go 导出的纯函数，输入显式
// fixture、输出字符串断言；不读取或修改渲染全局状态（主题、model 等）。
// 断言同时覆盖「语义文本」（plainANSI 去色）与「颜色纪律」（原始 ANSI
// 输出中 Warning/Accent/Error 样式 token 的出现与否）。

func evidenceClaimFixture() claimResult {
	return claimResult{
		Claim:            "检索增强生成能够降低幻觉",
		Verdict:          "部分支持",
		TopSimilarity:    0.846,
		Reason:           "仍需限定研究对象。",
		Qualification:    []string{"样本主要来自单一队列。"},
		StructuredAnswer: structuredAnswerCard{},
		Evidence: []claimEvidence{
			{
				PaperID:          "W1",
				Title:            "Retrieval-Augmented Generation and Hallucination",
				Year:             2025,
				Similarity:       0.827,
				Stance:           "SUPPORT",
				Confidence:       0.83,
				EvidenceSentence: "RAG reduced hallucination rates in grounded answers.",
				ChunkUID:         "cccccccccccccccccccccccccccccccccccccccc",
				SourceField:      "full_text",
				DisplayPolicy:    displayPolicy{Authorized: true, Reason: "usage_rights_allows_display"},
			},
		},
	}
}

func TestEvidencePapersCardRendersTitleYearAuthorSnippet(t *testing.T) {
	papers := []evidencePaper{
		{PaperID: "W1", Title: "Retrieval-Augmented Generation", Year: 2025, Authors: []string{"Ada", "Bo"}, Snippet: "RAG grounds answers in retrieved evidence."},
		{PaperID: "W2", Title: "Knowledge Graph Retrieval", Year: 2024, Authors: []string{"Chen"}, Snippet: "Graph evidence improves retrieval."},
	}
	out := RenderEvidencePapersCard(papers, 4, 1200*time.Millisecond)
	plain := plainANSI(out)
	for _, want := range []string{
		"╭─ evidence · 证据卡 2 篇 · 1.2s",
		"[1] Retrieval-Augmented Generation",
		"W1 · 2025 · Ada, Bo",
		"RAG grounds answers in retrieved evidence.",
		"[2] Knowledge Graph Retrieval",
		"W2 · 2024 · Chen",
		"╰─",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("papers card missing %q:\n%s", want, plain)
		}
	}
	// 空输入不渲染。
	if got := RenderEvidencePapersCard(nil, 4, 0); got != "" {
		t.Fatalf("empty papers should render nothing, got:\n%s", got)
	}
}

func TestEvidenceClaimCardSeparatesSimilarityFromConfidence(t *testing.T) {
	cr := evidenceClaimFixture()
	out := RenderClaimEvidenceCard(cr, 4, 0)
	plain := plainANSI(out)
	for _, want := range []string{
		"╭─ evidence · 论断核查 · 部分支持 · 最高相似度 0.846",
		"检索增强生成能够降低幻觉",
		"[1] Retrieval-Augmented Generation and Hallucination",
		"支持",
		"相似度 0.827",
		"中置信 0.83",
		"审计链 · chunk cccccccccccc",
		"来源链 · full_text",
		"RAG reduced hallucination rates in grounded answers.",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("claim card missing %q:\n%s", want, plain)
		}
	}
	// Similarity 与 Confidence 必须分开标注、数字不串位。
	if strings.Contains(plain, "相似度 0.83") || strings.Contains(plain, "置信 0.827") {
		t.Fatalf("similarity and confidence values crossed labels:\n%s", plain)
	}
	simAt := strings.Index(plain, "相似度 0.827")
	confAt := strings.Index(plain, "中置信 0.83")
	if simAt < 0 || confAt < 0 || simAt == confAt {
		t.Fatalf("similarity and confidence should both appear as separate tokens:\n%s", plain)
	}
}

func TestEvidenceClaimCardKeepsContradictingWeightEqualToSupporting(t *testing.T) {
	cr := evidenceClaimFixture()
	cr.Evidence = append(cr.Evidence,
		claimEvidence{PaperID: "W2", Title: "Contradicting Study", Year: 2024, Similarity: 0.81, Stance: "REFUTE", Confidence: 0.79, ChunkUID: "dddddddddddddddddddddddddddddddddddddddd"},
		claimEvidence{PaperID: "W3", Title: "Neutral Study", Year: 2023, Similarity: 0.75, Stance: "NEUTRAL", Confidence: 0.55, ChunkUID: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},
	)
	out := RenderClaimEvidenceCard(cr, 4, 0)
	plain := plainANSI(out)
	// Stance 语义真实：SUPPORT/REFUTE/NEUTRAL 分别呈现，不吞掉矛盾证据。
	for _, want := range []string{"支持", "反驳", "中立"} {
		if !strings.Contains(plain, want) {
			t.Fatalf("stance label %q missing:\n%s", want, plain)
		}
	}
	// 视觉权重相当：SUPPORT 与 REFUTE 共用同一 Accent 样式（计划 5.6，
	// 不把 refute 画成错误红）。
	if !strings.Contains(out, AccentText().Render("反驳")) || !strings.Contains(out, AccentText().Render("支持")) {
		t.Fatalf("SUPPORT and REFUTE must share the same accent style:\n%s", out)
	}
	if strings.Contains(out, ErrorText().Render("反驳")) || strings.Contains(out, ErrorText().Render("支持")) {
		t.Fatalf("contradicting evidence must not be painted as error red:\n%s", out)
	}
}

func TestEvidenceClaimCardHidesBlockedEvidenceText(t *testing.T) {
	cr := evidenceClaimFixture()
	cr.Evidence = append(cr.Evidence,
		claimEvidence{PaperID: "W2", Title: "Blocked Study", Year: 2024, Similarity: 0.8, Stance: "NEUTRAL", Confidence: 0.41, ChunkUID: "dddddddddddddddddddddddddddddddddddddddd", SourceField: "abstract", EvidenceSentence: "92% accuracy in a retrieval benchmark.", DisplayPolicy: displayPolicy{Authorized: false, Reason: "usage_rights_unknown_conservative"}},
		claimEvidence{PaperID: "W3", Title: "Unknown Policy Study", Year: 2025, Similarity: 0.7, Stance: "NEUTRAL", Confidence: 0.4, ChunkUID: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", SourceField: "full_text", EvidenceSentence: "This must stay hidden without explicit auth."},
	)
	out := RenderClaimEvidenceCard(cr, 4, 0)
	plain := plainANSI(out)
	for _, forbidden := range []string{
		"92% accuracy in a retrieval benchmark.",
		"This must stay hidden without explicit auth.",
		"abstract", // source field 同样受 display policy 保护
	} {
		if strings.Contains(plain, forbidden) {
			t.Fatalf("blocked evidence leaked %q:\n%s", forbidden, plain)
		}
	}
	// hidden reason 呈现；审计链即使正文被隐藏也保留。
	for _, want := range []string{
		"正文隐藏 · usage_rights_unknown_conservative",
		"审计链 · chunk dddddddddddd",
		"审计链 · chunk eeeeeeeeeeee",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("blocked evidence card missing %q:\n%s", want, plain)
		}
	}
	// 无 reason 的 fail-closed（零值 policy）不渲染「正文隐藏」伪条目。
	if strings.Count(plain, "正文隐藏") != 1 {
		t.Fatalf("expected exactly one hidden-reason line, got %d:\n%s", strings.Count(plain, "正文隐藏"), plain)
	}
}

func TestEvidenceInsufficientCardWarnsWithoutFakeConfidence(t *testing.T) {
	cr := claimResult{
		Claim:         "某论断",
		Verdict:       "证据不足",
		TopSimilarity: 0.9,
		Reason:        "未检索到相关文献。",
		Qualification: []string{"研究对象范围未覆盖。"},
		Evidence:      []claimEvidence{},
	}
	out := RenderClaimEvidenceCard(cr, 4, 0)
	plain := plainANSI(out)
	for _, want := range []string{
		"╭─ evidence · 论断核查 · 证据不足",
		"某论断",
		"系统拒绝无证据结论",
		"未检索到相关文献。",
		"限定条件 · 研究对象范围未覆盖。",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("insufficient card missing %q:\n%s", want, plain)
		}
	}
	// Warning 而不是 Error。
	if !strings.Contains(out, WarningText().Render("证据不足: 系统拒绝无证据结论")) {
		t.Fatalf("insufficient must render in Warning style:\n%s", out)
	}
	if strings.Contains(out, ErrorText().Render("证据不足: 系统拒绝无证据结论")) {
		t.Fatalf("insufficient must not be painted as error:\n%s", out)
	}
	// 不显示假 confidence / similarity（包括 TopSimilarity 0.9）。
	for _, forbidden := range []string{"相似度", "置信", "0.9"} {
		if strings.Contains(plain, forbidden) {
			t.Fatalf("insufficient card must not fabricate metrics, leaked %q:\n%s", forbidden, plain)
		}
	}
}

func TestEvidenceAnswerContractCompressedSingleLine(t *testing.T) {
	card := structuredAnswerCard{
		SchemaVersion:      "answer-contract/v1",
		Capability:         "claim_verification",
		Status:             "supported",
		VerdictLabel:       "强支持",
		AnswerMode:         "evidence_based",
		CitationCompliance: "ok",
		Citations:          make([]answerCitation, 4),
		ToolBasis:          []string{"verify_claim"},
		Claim:              "咖啡能降低心脏病风险",
	}
	out := RenderAnswerContractCompressed(card)
	plain := plainANSI(out)
	if strings.Count(out, "\n") != 0 {
		t.Fatalf("compressed contract must be a single line, got:\n%q", out)
	}
	for _, want := range []string{"强支持", "4 条证据", "引文已验证"} {
		if !strings.Contains(plain, want) {
			t.Fatalf("compressed contract missing %q:\n%s", want, plain)
		}
	}
	if !strings.Contains(out, AccentText().Render("强支持")) {
		t.Fatalf("compressed contract verdict should be accent-emphasized:\n%s", out)
	}
	// 非 ok 合规状态如实翻译，不伪装 verified。
	card.CitationCompliance = "missing_required_citations"
	if plain := plainANSI(RenderAnswerContractCompressed(card)); !strings.Contains(plain, "引文 missing_required_citations") {
		t.Fatalf("compressed contract should keep non-ok compliance visible:\n%s", plain)
	}
}

func TestEvidenceAnswerContractFullKeepsAllFields(t *testing.T) {
	card := structuredAnswerCard{
		SchemaVersion:      "answer-contract/v1",
		Capability:         "claim_verification",
		Status:             "partially_supported",
		VerdictLabel:       "部分支持",
		AnswerMode:         "generative_non_evidentiary",
		CitationCompliance: "missing_required_citations",
		ToolBasis:          []string{"verify_claim"},
		Claim:              "咖啡能降低心脏病风险",
		Uncertainty: answerUncertainty{
			Category:            "evidence_insufficient",
			Message:             "研究对象仍有限定。",
			CalibratedRejection: true,
			QualificationHints:  []string{"样本主要来自单一队列。"},
		},
		Citations: []answerCitation{
			{PaperID: "W1", Title: "Coffee study", Year: 2023, ChunkUID: "cccccccccccccccccccccccccccccccccccccccc", SourceField: "full_text", EvidenceSentence: "Coffee intake was associated with lower cardiovascular risk.", Stance: "SUPPORT", Confidence: 0.81, DisplayPolicy: displayPolicy{Authorized: true, Reason: "usage_rights_allows_display"}},
			{PaperID: "W2", Title: "Blocked study", Year: 2024, ChunkUID: "dddddddddddddddddddddddddddddddddddddddd", SourceField: "abstract", EvidenceSentence: "Hidden sentence that must not leak.", DisplayPolicy: displayPolicy{Authorized: false, Reason: "indexable_only_metadata_not_display"}},
		},
	}
	out := RenderAnswerContractFull(card)
	plain := plainANSI(out)
	for _, want := range []string{
		"╭─ contract · 答案合同",
		"部分支持 · non-evidentiary · citations missing_required_citations",
		"claim   咖啡能降低心脏病风险",
		"uncert  evidence_insufficient · calibrated rejection",
		"reason  研究对象仍有限定。",
		"limit   样本主要来自单一队列。",
		"[1] Coffee study",
		"W1 · 2023 · 支持 · 中置信 0.81",
		"审计链 chunk cccccccccccc",
		"来源链 full_text",
		"Coffee intake was associated with lower cardiovascular risk.",
		"正文隐藏 · indexable_only_metadata_not_display",
		"basis   verify_claim",
	} {
		if !strings.Contains(plain, want) {
			t.Fatalf("full contract missing %q:\n%s", want, plain)
		}
	}
	// display policy fail-closed 在完整版同样不可绕过。
	for _, forbidden := range []string{"Hidden sentence that must not leak.", "abstract"} {
		if strings.Contains(plain, forbidden) {
			t.Fatalf("full contract leaked %q:\n%s", forbidden, plain)
		}
	}
	// uncertainty（degraded）用 Warning 语义。
	if !strings.Contains(out, WarningText().Render("uncert  evidence_insufficient · calibrated rejection")) {
		t.Fatalf("full contract uncertainty should be Warning-styled:\n%s", out)
	}
}

func TestEvidenceAnswerContractEmptyRendersNothing(t *testing.T) {
	for name, card := range map[string]structuredAnswerCard{
		"zero":           {},
		"not-applicable": {Status: "not_applicable", CitationCompliance: "not_applicable"},
	} {
		if got := RenderAnswerContractCompressed(card); got != "" {
			t.Fatalf("%s: compressed should render nothing, got:\n%s", name, got)
		}
		if got := RenderAnswerContractFull(card); got != "" {
			t.Fatalf("%s: full should render nothing, got:\n%s", name, got)
		}
	}
}

func TestEvidenceRenderFunctionsAreDeterministic(t *testing.T) {
	cr := evidenceClaimFixture()
	a := RenderClaimEvidenceCard(cr, 4, 1500*time.Millisecond)
	b := RenderClaimEvidenceCard(cr, 4, 1500*time.Millisecond)
	if a != b {
		t.Fatalf("claim evidence card is not deterministic:\n%s\n---\n%s", a, b)
	}
	papers := []evidencePaper{{PaperID: "W1", Title: "T", Year: 2025}}
	if x, y := RenderEvidencePapersCard(papers, 4, 0), RenderEvidencePapersCard(papers, 4, 0); x != y {
		t.Fatalf("papers card is not deterministic")
	}
	card := structuredAnswerCard{Status: "supported", VerdictLabel: "强支持", CitationCompliance: "ok", Citations: make([]answerCitation, 2)}
	if x, y := RenderAnswerContractCompressed(card), RenderAnswerContractCompressed(card); x != y {
		t.Fatalf("compressed contract is not deterministic")
	}
	if x, y := RenderAnswerContractFull(card), RenderAnswerContractFull(card); x != y {
		t.Fatalf("full contract is not deterministic")
	}
}

func TestEvidenceViewSourceHasNoRawHexAndUsesPrimitives(t *testing.T) {
	src, err := os.ReadFile("view_evidence.go")
	if err != nil {
		t.Fatalf("read view_evidence.go: %v", err)
	}
	text := string(src)
	if hexRE.MatchString(text) {
		t.Fatalf("view_evidence.go must not contain raw hex colors")
	}
	// 必须基于 style_primitives 的 domainCard（Evidence 卡）与
	// inlineBlock（压缩行）基元。
	for _, want := range []string{"domainCard(", "inlineBlock("} {
		if !strings.Contains(text, want) {
			t.Fatalf("view_evidence.go missing primitive %q", want)
		}
	}
	// 颜色一律经 theme.go 语义样式函数，且本层不使用 Error 语义
	// （证据层没有真实执行失败）。
	for _, want := range []string{"PrimaryText()", "MutedText()", "FaintText()", "AccentText()", "WarningText()"} {
		if !strings.Contains(text, want) {
			t.Fatalf("view_evidence.go missing semantic style %q", want)
		}
	}
	if strings.Contains(text, "ErrorText()") {
		t.Fatalf("evidence layer must not use Error semantics")
	}
}

var hexRE = regexp.MustCompile(`#[0-9A-Fa-f]{6}`)
