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
	return strings.TrimRight(backendURL(), "/") + "/api/ingest/status"
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

func collectDoctorChecks() []doctorCheck {
	checks := []doctorCheck{}
	if httpReachable(healthURL(), 700*time.Millisecond) {
		checks = append(checks, doctorCheck{"Backend", "ok", healthURL()})
	} else {
		if backendMode(backendURL()) == "local" {
			checks = append(checks, doctorCheck{"Backend", "warn", "not reachable; run make backend"})
		} else {
			checks = append(checks, doctorCheck{"Backend", "warn", "hosted service unavailable; try /demo or retry later"})
		}
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

func demoScriptMessages() []tea.Msg {
	verifyResult := `{
		"论断":"检索增强生成能够降低大语言模型回答中的幻觉风险",
		"支持等级":"强支持",
		"最高接地相似度":0.846,
		"证据":[
			{"paper_id":"W4411065983","标题":"Retrieval-Augmented Generation and Hallucination Mitigation","年份":2025,"接地相似度":0.846},
			{"paper_id":"2309.01431","标题":"Benchmarking Large Language Models in Retrieval-Augmented Generation","年份":2023,"接地相似度":0.827}
		]
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
		finalMsg("结论：该论断获得强支持。SciScope 将中文论断映射到英文前沿文献，通过 verify_claim 给出最高接地相似度 0.846，并列出可追溯、可验证的论文证据。更稳妥的表述是：RAG 能显著降低无依据回答的风险，但效果取决于检索质量、证据覆盖和生成模型是否忠实使用证据。"),
		doneMsg{},
	}
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
