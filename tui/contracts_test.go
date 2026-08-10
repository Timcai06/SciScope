package main

import (
	"strings"
	"testing"
)

func TestGoldenJudgeTasksProvideTwoFixedReviewerFlows(t *testing.T) {
	tasks := goldenJudgeTasks()
	if len(tasks) != 2 {
		t.Fatalf("expected 2 golden tasks, got %#v", tasks)
	}
	if !strings.HasPrefix(tasks[0].Command, "/verify ") {
		t.Fatalf("first golden task should be verify, got %#v", tasks[0])
	}
	if !strings.HasPrefix(tasks[1].Command, "/review ") {
		t.Fatalf("second golden task should be review, got %#v", tasks[1])
	}
}

func TestRenderStructuredAnswerCardShowsFailClosedSourceChain(t *testing.T) {
	rendered := plainANSI(renderStructuredAnswerCard(map[string]any{
		"schema_version":      "answer-contract/v1",
		"capability":          "claim_verification",
		"status":              "evidence_insufficient",
		"verdict_label":       "证据不足",
		"answer_mode":         "generative_non_evidentiary",
		"citation_compliance": "missing_required_citations",
		"claim":               "咖啡能降低心脏病风险",
		"tool_basis":          []string{"verify_claim"},
		"uncertainty": map[string]any{
			"category":             "evidence_insufficient",
			"message":              "当前只检索到主题相关论文，不能直接判为支持。",
			"calibrated_rejection": true,
			"qualification_hints":  []string{"研究对象与原论断人群不完全一致。"},
		},
		"citations": []map[string]any{
			{
				"paper_id":          "W1",
				"title":             "Coffee study",
				"year":              2023,
				"chunk_uid":         "cccccccccccccccccccccccccccccccccccccccc",
				"source_field":      "full_text",
				"evidence_sentence": "Coffee intake was associated with lower cardiovascular risk.",
				"stance":            "SUPPORT",
				"confidence":        0.61,
				"display_policy": map[string]any{
					"authorized": true,
					"reason":     "usage_rights_allows_display",
				},
			},
		},
	}, 120))

	for _, want := range []string{
		"答案合同",
		"证据不足",
		"calibrated rejection",
		"审计链 chunk cccccccccccc",
		"来源链 full_text",
		"Coffee intake was associated with lower cardiovascular risk.",
		"研究对象与原论断人群不完全一致。",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("structured answer card missing %q:\n%s", want, rendered)
		}
	}
}

func TestRenderStructuredAnswerCardHidesEvidenceWhenUnauthorizedOrUnknown(t *testing.T) {
	unauthorized := plainANSI(renderStructuredAnswerCard(map[string]any{
		"schema_version":      "answer-contract/v1",
		"capability":          "claim_verification",
		"status":              "supported",
		"verdict_label":       "强支持",
		"answer_mode":         "evidence_based",
		"citation_compliance": "ok",
		"claim":               "咖啡能降低心脏病风险",
		"tool_basis":          []string{"verify_claim"},
		"uncertainty":         map[string]any{"category": "none", "message": "", "calibrated_rejection": false, "qualification_hints": []string{}},
		"citations": []map[string]any{
			{
				"paper_id":          "W1",
				"title":             "Coffee study",
				"year":              2023,
				"chunk_uid":         "cccccccccccccccccccccccccccccccccccccccc",
				"source_field":      "full_text",
				"evidence_sentence": "Coffee intake was associated with lower cardiovascular risk.",
				"display_policy": map[string]any{
					"authorized": false,
					"reason":     "indexable_only_metadata_not_display",
				},
			},
			{
				"paper_id":          "W2",
				"title":             "Second study",
				"year":              2024,
				"chunk_uid":         "dddddddddddddddddddddddddddddddddddddddd",
				"source_field":      "abstract",
				"evidence_sentence": "Numeric result 92% accuracy.",
			},
		},
	}, 120))

	if strings.Contains(unauthorized, "Coffee intake was associated") || strings.Contains(unauthorized, "Numeric result 92% accuracy.") {
		t.Fatalf("unauthorized or unknown display policy should hide evidence text:\n%s", unauthorized)
	}
	if strings.Contains(unauthorized, "full_text") || strings.Contains(unauthorized, "abstract") {
		t.Fatalf("unauthorized or unknown display policy should hide source field:\n%s", unauthorized)
	}
	for _, want := range []string{"审计链 chunk cccccccccccc", "审计链 chunk dddddddddddd", "正文隐藏 · indexable_only_metadata_not_display"} {
		if !strings.Contains(unauthorized, want) {
			t.Fatalf("expected retained audit chain %q:\n%s", want, unauthorized)
		}
	}
}

func TestRenderRecommendToolResultFailsClosedWhenUnavailable(t *testing.T) {
	result := `{"status":"unavailable","query":{"kind":"recommend","paper_id":"W1"},"data_source":null,"results":[],"unavailable_reason":"paper_embeddings_unavailable","note":"paper_embeddings 缺失时不提供伪造推荐。"}`
	rendered := plainANSI(renderToolResult("recommend_papers", result, 120, 0))
	for _, want := range []string{
		"论文推荐",
		"unavailable",
		"paper_embeddings_unavailable",
		"当前无可展示推荐；不伪造语义近邻。",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("recommend unavailable card missing %q:\n%s", want, rendered)
		}
	}
}

func TestRenderKnowledgeGraphToolResultShowsRelationsAndProvenance(t *testing.T) {
	result := `{
		"status":"ok",
		"query":{"type":"paper","center":"W1"},
		"data_source":"kg_asset_v1",
		"asset":{"schema_version":"knowledge-graph-asset/v1"},
		"results":{
			"paper":{"title":"Evidence-grounded Scientific QA"},
			"relations":{"about":{"target_label":"retrieval augmented generation"}},
			"neighbours":[
				{"relation":"about","target_label":"retrieval augmented generation","provenance":{"paper_id":"W1","record_sha256_status":"computed_at_query_time"}}
			]
		},
		"note":"本图谱关系仅表达论文已有字段关系，不构成因果。"
	}`
	rendered := plainANSI(renderToolResult("query_knowledge_graph", result, 120, 0))
	for _, want := range []string{
		"知识图谱",
		"关系   about",
		"about → retrieval augmented generation",
		"来源链 · W1 · hash computed_at_query_time",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("graph card missing %q:\n%s", want, rendered)
		}
	}
}

func TestRenderDisputesToolResultShowsCanonicalClaimFrontier(t *testing.T) {
	result := `{
		"争议数量":1,
		"争议":[
			{"claim":"咖啡能降低心脏病风险","support_count":1,"contradict_count":1,"paper_count":2,"paper_ids":["E03-SUPPORT","E03-CONTRADICT"]}
		],
		"边界":"仅计入有可核验证据句、置信度达阈值且无适用条件冲突的 SUPPORT/CONTRADICT 证据。"
	}`
	rendered := plainANSI(renderToolResult("list_disputes", result, 120, 0))
	for _, want := range []string{
		"争议前线",
		"咖啡能降低心脏病风险",
		"support 1 · contradict 1 · papers 2",
		"paper_ids · E03-SUPPORT, E03-CONTRADICT",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("dispute card missing %q:\n%s", want, rendered)
		}
	}
}

func TestRenderVerifyClaimToolResultRequiresExplicitAuthorizationForEvidenceText(t *testing.T) {
	result := `{
		"论断":"咖啡能降低心脏病风险",
		"支持等级":"部分支持",
		"拒答原因":"仍需限定研究对象。",
		"证据":[
			{"paper_id":"W1","标题":"Coffee study","年份":2023,"立场":"SUPPORT","置信度":0.83,"chunk_uid":"cccccccccccccccccccccccccccccccccccccccc","source_field":"full_text","证据句":"Coffee lowered cardiovascular risk.","display_policy":{"authorized":true,"reason":"usage_rights_allows_display"}},
			{"paper_id":"W2","标题":"Second study","年份":2024,"立场":"NEUTRAL","置信度":0.41,"chunk_uid":"dddddddddddddddddddddddddddddddddddddddd","source_field":"abstract","证据句":"92% accuracy in a retrieval benchmark.","display_policy":{"authorized":false,"reason":"usage_rights_unknown_conservative"}},
			{"paper_id":"W3","标题":"Third study","年份":2025,"立场":"CONTRADICT","置信度":0.77,"chunk_uid":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","source_field":"full_text","证据句":"This should stay hidden without explicit auth."}
		]
	}`
	rendered := plainANSI(renderToolResult("verify_claim", result, 120, 0))
	if !strings.Contains(rendered, "Coffee lowered cardiovascular risk.") {
		t.Fatalf("authorized verify_claim evidence should render:\n%s", rendered)
	}
	for _, forbidden := range []string{"92% accuracy in a retrieval benchmark.", "This should stay hidden without explicit auth.", "abstract"} {
		if strings.Contains(rendered, forbidden) {
			t.Fatalf("unauthorized or unknown verify_claim evidence leaked %q:\n%s", forbidden, rendered)
		}
	}
	for _, want := range []string{"来源链 · full_text", "正文隐藏 · usage_rights_unknown_conservative", "审计链 · chunk dddddddddddd", "审计链 · chunk eeeeeeeeeeee"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("verify_claim card missing %q:\n%s", want, rendered)
		}
	}
}

func TestReviewGoldenMessagesProvideResearchClueFixture(t *testing.T) {
	msgs := reviewGoldenMessages()
	if len(msgs) < 8 {
		t.Fatalf("expected rich review fixture, got %#v", msgs)
	}
	seen := map[string]bool{}
	for _, msg := range msgs {
		switch typed := msg.(type) {
		case toolCallMsg:
			seen[typed.name] = true
		}
	}
	for _, want := range []string{"query_knowledge_graph", "recommend_papers", "get_trends"} {
		if !seen[want] {
			t.Fatalf("review golden fixture missing %s: %#v", want, msgs)
		}
	}
}
