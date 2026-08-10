package main

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

func healthURL() string {
	return strings.TrimRight(backendURL(), "/") + "/readyz"
}

func llmURL() string {
	if v := os.Getenv("LOCAL_LLM_BASE_URL"); v != "" {
		return strings.TrimRight(v, "/") + "/models"
	}
	return "http://127.0.0.1:8001/v1/models"
}

func httpReachable(url string, timeout time.Duration) bool {
	client := http.Client{Timeout: timeout}
	resp, err := client.Get(url)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 500
}

func backendDoctorTimeout(baseURL string) time.Duration {
	if backendMode(baseURL) == "local" {
		return 700 * time.Millisecond
	}
	return 8 * time.Second
}

func backendDoctorWarning(baseURL string) doctorCheck {
	if backendMode(baseURL) == "local" {
		return doctorCheck{"Backend", "warn", "not reachable; run make backend"}
	}
	return doctorCheck{"Backend", "warn", "hosted service unavailable; try /demo or retry later"}
}

func collectDoctorChecks() []doctorCheck {
	checks := []doctorCheck{}
	baseURL := backendURL()
	if httpReachable(healthURL(), backendDoctorTimeout(baseURL)) {
		checks = append(checks, doctorCheck{"Backend", "ok", healthURL()})
	} else {
		checks = append(checks, backendDoctorWarning(baseURL))
	}
	if httpReachable(llmURL(), 700*time.Millisecond) {
		checks = append(checks, doctorCheck{"LLM", "ok", llmURL()})
	} else {
		checks = append(checks, doctorCheck{"LLM", "warn", "not reachable; run make llm or use --demo"})
	}
	dir := sessionDir()
	if err := os.MkdirAll(dir, 0o755); err == nil {
		checks = append(checks, doctorCheck{"Sessions", "ok", dir})
	} else {
		checks = append(checks, doctorCheck{"Sessions", "error", err.Error()})
	}
	if _, err := os.Stat(filepath.Join("..", "output", "graphs")); err == nil {
		checks = append(checks, doctorCheck{"Graph assets", "ok", "output/graphs"})
	} else if _, err := os.Stat(filepath.Join("output", "graphs")); err == nil {
		checks = append(checks, doctorCheck{"Graph assets", "ok", "output/graphs"})
	} else {
		checks = append(checks, doctorCheck{"Graph assets", "warn", "missing; run make graph-export"})
	}
	return checks
}

func renderDoctorReport(checks []doctorCheck) string {
	lines := []string{"SciScope doctor", ""}
	for _, check := range checks {
		mark := "unknown"
		switch check.Status {
		case "ok":
			mark = "ok"
		case "warn":
			mark = "warn"
		case "error":
			mark = "error"
		}
		lines = append(lines, fmt.Sprintf("%-12s %-4s %s", check.Name, mark, check.Detail))
	}
	lines = append(lines, "", "Next: sciscope-tui demo | sciscope-tui export --last")
	return strings.Join(lines, "\n")
}

func demoDelay() time.Duration {
	v := strings.TrimSpace(os.Getenv("SCISCOPE_TUI_DEMO_DELAY_MS"))
	if v == "" {
		return 420 * time.Millisecond
	}
	var ms int
	if _, err := fmt.Sscanf(v, "%d", &ms); err != nil || ms < 0 {
		return 420 * time.Millisecond
	}
	return time.Duration(ms) * time.Millisecond
}

func verifyGoldenMessages() []tea.Msg {
	verifyResult := `{
		"论断":"检索增强生成能够降低大语言模型回答中的幻觉风险",
		"支持等级":"强支持",
		"限定条件":["效果取决于检索质量与证据覆盖。"],
		"最高接地相似度":0.846,
		"证据":[
			{"paper_id":"W4411065983","标题":"Retrieval-Augmented Generation and Hallucination Mitigation","年份":2025,"接地相似度":0.846,"立场":"SUPPORT","置信度":0.95,"chunk_uid":"cccccccccccccccccccccccccccccccccccccccc","source_field":"full_text","证据句":"Retrieved evidence improves factual grounding and reduces unsupported generations."},
			{"paper_id":"2309.01431","标题":"Benchmarking Large Language Models in Retrieval-Augmented Generation","年份":2023,"接地相似度":0.827,"立场":"SUPPORT","置信度":0.89,"chunk_uid":"dddddddddddddddddddddddddddddddddddddddd","source_field":"abstract","证据句":"RAG evaluation links answer faithfulness to evidence quality."}
		],
		"structured_answer":{
			"schema_version":"answer-contract/v1",
			"capability":"claim_verification",
			"status":"supported",
			"verdict_label":"强支持",
			"answer_mode":"evidence_based",
			"citation_compliance":"ok",
			"tool_basis":["verify_claim","search_literature"],
			"claim":"检索增强生成能够降低大语言模型回答中的幻觉风险",
			"uncertainty":{"category":"none","message":"","calibrated_rejection":false,"qualification_hints":["效果取决于检索质量与证据覆盖。"]},
			"citations":[
				{"paper_id":"W4411065983","title":"Retrieval-Augmented Generation and Hallucination Mitigation","year":2025,"chunk_uid":"cccccccccccccccccccccccccccccccccccccccc","source_field":"full_text","evidence_sentence":"Retrieved evidence improves factual grounding and reduces unsupported generations.","stance":"SUPPORT","confidence":0.95},
				{"paper_id":"2309.01431","title":"Benchmarking Large Language Models in Retrieval-Augmented Generation","year":2023,"chunk_uid":"dddddddddddddddddddddddddddddddddddddddd","source_field":"abstract","evidence_sentence":"RAG evaluation links answer faithfulness to evidence quality.","stance":"SUPPORT","confidence":0.89}
			]
		}
	}`
	searchResult := `[
		{"paper_id":"W4411065983","标题":"Retrieval-Augmented Generation and Hallucination Mitigation","年份":2025,"作者":["Li","Zhang"],"摘要片段":"Retrieved evidence improves factual grounding and reduces unsupported generations."},
		{"paper_id":"2309.01431","标题":"Benchmarking Large Language Models in Retrieval-Augmented Generation","年份":2023,"作者":["Chen","Wang"],"摘要片段":"RAG evaluation links answer faithfulness to evidence quality."},
		{"paper_id":"W4399001120","标题":"Evidence-grounded Scientific Question Answering","年份":2024,"作者":["Kumar"],"摘要片段":"Scientific QA benefits from citation-aware retrieval and claim verification."}
	]`
	return []tea.Msg{
		demoStartMsg("核查：RAG（检索增强生成）能够降低大语言模型回答中的幻觉风险，并给出可验证证据。"),
		planMsg{"解析中文论断并生成英文检索表达", "调用 verify_claim 做跨语言接地核查", "补充检索高相关论文并输出证据卡", "汇总支持等级、证据出处和可复现结论"},
		toolCallMsg{name: "verify_claim", args: map[string]any{"claim": "检索增强生成能够降低大语言模型回答中的幻觉风险"}},
		toolResultMsg{name: "verify_claim", result: verifyResult},
		toolCallMsg{name: "search_literature", args: map[string]any{"query": "retrieval augmented generation hallucination mitigation", "top_k": 3}},
		toolResultMsg{name: "search_literature", result: searchResult},
		reflectMsg("证据相似度与论文主题一致，结论限定为“降低风险”，不夸大为完全消除。"),
		nodePulseMsg{kind: "final", meta: eventMeta{StructuredAnswer: map[string]any{
			"schema_version":      "answer-contract/v1",
			"capability":          "claim_verification",
			"status":              "supported",
			"verdict_label":       "强支持",
			"answer_mode":         "evidence_based",
			"citation_compliance": "ok",
			"claim":               "检索增强生成能够降低大语言模型回答中的幻觉风险",
			"tool_basis":          []string{"verify_claim", "search_literature"},
			"uncertainty": map[string]any{
				"category":             "none",
				"message":              "",
				"calibrated_rejection": false,
				"qualification_hints":  []string{"效果取决于检索质量与证据覆盖。"},
			},
			"citations": []map[string]any{
				{"paper_id": "W4411065983", "title": "Retrieval-Augmented Generation and Hallucination Mitigation", "year": 2025, "chunk_uid": "cccccccccccccccccccccccccccccccccccccccc", "source_field": "full_text", "evidence_sentence": "Retrieved evidence improves factual grounding and reduces unsupported generations.", "stance": "SUPPORT", "confidence": 0.95},
				{"paper_id": "2309.01431", "title": "Benchmarking Large Language Models in Retrieval-Augmented Generation", "year": 2023, "chunk_uid": "dddddddddddddddddddddddddddddddddddddddd", "source_field": "abstract", "evidence_sentence": "RAG evaluation links answer faithfulness to evidence quality.", "stance": "SUPPORT", "confidence": 0.89},
			},
		}}},
		finalMsg("结论：该论断获得强支持。SciScope 将中文论断映射到英文前沿文献，通过 verify_claim 给出最高接地相似度 0.846，并列出可追溯、可验证的论文证据。更稳妥的表述是：RAG 能显著降低无依据回答的风险，但效果取决于检索质量、证据覆盖和生成模型是否忠实使用证据。"),
		doneMsg{},
	}
}

func reviewGoldenMessages() []tea.Msg {
	graphResult := `{
		"status":"ok",
		"query":{"type":"topic","center":"retrieval augmented generation"},
		"data_source":"kg_asset_v1",
		"asset":{"schema_version":"knowledge-graph-asset/v1","input_fingerprint":"fixture-rag-graph"},
		"results":{"entity":{"label":"retrieval augmented generation"},"paper_count":3,"papers":["W4411065983","2309.01431","W4399001120"],"provenance_sample":{"paper_id":"W4411065983","record_sha256_status":"computed_at_query_time"}},
		"unavailable_reason":null,
		"note":"本图谱关系仅表达论文已有字段（来源/关键词/年份）的关系，不构成因果，也不构成对任何科学结论或 stance 的支持。"
	}`
	recommendResult := `{
		"status":"ok",
		"query":{"kind":"recommend","paper_id":"W4411065983"},
		"data_source":"recommend_service",
		"results":[
			{"paper_id":"W4399001120","title":"Evidence-grounded Scientific Question Answering","year":2024,"field":"computer science","similarity":0.84,"shared_keywords":["citation-aware retrieval","claim verification"],"factors":{"semantic":0.62,"keyword_overlap":0.22}},
			{"paper_id":"W4400000001","title":"Evidence Routing for Scientific QA Agents","year":2025,"field":"computer science","similarity":0.79,"shared_keywords":["evidence routing"],"factors":{"semantic":0.58,"keyword_overlap":0.18}}
		],
		"unavailable_reason":null,
		"note":"推荐基于 paper_embeddings 语义近邻 + 关键词/作者重叠 + MMR 重排；相关性为计算相似度，不代表科学结论支持。"
	}`
	trendResult := `{
		"status":"ok",
		"data_source":"trend_assets",
		"trend_policy":{"descriptive_only":true},
		"asset":{"time_range":{"range":"2022-2026","ytd":true,"source":"keyword_trends.csv"}},
		"results":[{"关键词":"retrieval augmented generation","增长方向":"rising(上升)","生命周期阶段":"加速扩张","统计依据":{"近期活跃度分":"0.82","短期加速分":"0.77"}}],
		"note":"仅提供历史统计描述；当前不提供未来数值预测。"
	}`
	return []tea.Msg{
		demoStartMsg("综述：retrieval augmented generation 在科研问答中的证据链设计与后续研究线索。"),
		planMsg{"先找主题证据与代表论文", "读取图谱关系确认主题关联论文", "补充推荐与趋势，明确哪些只是描述性线索"},
		toolCallMsg{name: "query_knowledge_graph", args: map[string]any{"type": "topic", "center": "retrieval augmented generation"}},
		toolResultMsg{name: "query_knowledge_graph", result: graphResult},
		toolCallMsg{name: "recommend_papers", args: map[string]any{"paper_id": "W4411065983"}},
		toolResultMsg{name: "recommend_papers", result: recommendResult},
		toolCallMsg{name: "get_trends", args: map[string]any{"keyword": "retrieval augmented generation"}},
		toolResultMsg{name: "get_trends", result: trendResult},
		reflectMsg("趋势只作为描述性线索，不把统计外推当预测结论。"),
		finalMsg("研究线索：RAG 在科研问答中的核心机会集中在证据路由、引文合规与争议识别。图谱关系可帮助定位主题相关论文，推荐结果适合延伸阅读，趋势结果只用于描述近年的活跃变化，不应写成确定预测。"),
		doneMsg{},
	}
}

func demoScriptMessages() []tea.Msg {
	return verifyGoldenMessages()
}

// playDemo replays a deterministic offline sequence so "/demo" and the
// environment-gated startup path work without backend/LLM/network.
// The sequence is fixed: user prompt -> plan -> tool calls/results ->
// reflect -> final, ending with doneMsg.
func playDemo(sub chan tea.Msg) {
	delay := demoDelay()
	for _, msg := range demoScriptMessages() {
		if delay > 0 {
			time.Sleep(delay)
		}
		sub <- msg
	}
}

// stream POSTs the question and pushes one tea.Msg per valid SSE payload.
// Supported event types:
//
//	plan      -> []string{"..."}
//	text      -> incremental answer chunk
//	tool_call -> {name,args}
//	tool_result-> {name,result}
//	reflect   -> self-check text
//	final     -> final answer block
//	error     -> recoverable error text
//
// Scanner keeps only lines starting with "data:" and stops at "[DONE]".
