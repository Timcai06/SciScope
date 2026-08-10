package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

type answerCitation struct {
	PaperID          string        `json:"paper_id"`
	Title            string        `json:"title"`
	Year             int           `json:"year"`
	ChunkUID         string        `json:"chunk_uid"`
	SourceField      string        `json:"source_field"`
	EvidenceSentence string        `json:"evidence_sentence"`
	Stance           string        `json:"stance"`
	Confidence       float64       `json:"confidence"`
	DisplayPolicy    displayPolicy `json:"display_policy"`
}

type displayPolicy struct {
	Authorized bool   `json:"authorized"`
	Reason     string `json:"reason"`
}

type answerUncertainty struct {
	Category            string   `json:"category"`
	Message             string   `json:"message"`
	CalibratedRejection bool     `json:"calibrated_rejection"`
	QualificationHints  []string `json:"qualification_hints"`
}

type structuredAnswerCard struct {
	SchemaVersion      string            `json:"schema_version"`
	Capability         string            `json:"capability"`
	Status             string            `json:"status"`
	VerdictLabel       string            `json:"verdict_label"`
	AnswerMode         string            `json:"answer_mode"`
	CitationCompliance string            `json:"citation_compliance"`
	Citations          []answerCitation  `json:"citations"`
	Uncertainty        answerUncertainty `json:"uncertainty"`
	ToolBasis          []string          `json:"tool_basis"`
	Claim              string            `json:"claim"`
}

type resultEnvelope struct {
	Status            string         `json:"status"`
	Query             map[string]any `json:"query"`
	DataSource        string         `json:"data_source"`
	Asset             map[string]any `json:"asset"`
	Results           any            `json:"results"`
	UnavailableReason string         `json:"unavailable_reason"`
	DegradedReason    string         `json:"degraded_reason"`
	Note              string         `json:"note"`
	Reason            string         `json:"reason"`
	TrendPolicy       map[string]any `json:"trend_policy"`
}

type disputeEnvelope struct {
	Count  int              `json:"争议数量"`
	Rows   []map[string]any `json:"争议"`
	Border string           `json:"边界"`
}

type goldenTask struct {
	Title      string
	Command    string
	Goal       string
	Boundary   string
	FixtureTag string
}

func parseStructuredAnswerValue(value any) (structuredAnswerCard, bool) {
	switch typed := value.(type) {
	case nil:
		return structuredAnswerCard{}, false
	case structuredAnswerCard:
		return typed, true
	case map[string]any:
		raw, err := json.Marshal(typed)
		if err != nil {
			return structuredAnswerCard{}, false
		}
		var out structuredAnswerCard
		if json.Unmarshal(raw, &out) != nil {
			return structuredAnswerCard{}, false
		}
		return out, true
	default:
		raw, err := json.Marshal(typed)
		if err != nil {
			return structuredAnswerCard{}, false
		}
		var out structuredAnswerCard
		if json.Unmarshal(raw, &out) != nil {
			return structuredAnswerCard{}, false
		}
		return out, true
	}
}

func parseResultEnvelope(raw string) (resultEnvelope, bool) {
	var out resultEnvelope
	if json.Unmarshal([]byte(raw), &out) != nil {
		return resultEnvelope{}, false
	}
	if strings.TrimSpace(out.Status) == "" {
		return resultEnvelope{}, false
	}
	return out, true
}

func parseDisputeEnvelope(raw string) (disputeEnvelope, bool) {
	var out disputeEnvelope
	if json.Unmarshal([]byte(raw), &out) != nil {
		return disputeEnvelope{}, false
	}
	if out.Rows == nil {
		return disputeEnvelope{}, false
	}
	return out, true
}

func goldenJudgeTasks() []goldenTask {
	return []goldenTask{
		{
			Title:      "黄金任务 1｜论断核查",
			Command:    "/verify 检索增强生成能够降低大语言模型回答中的幻觉风险",
			Goal:       "固定展示 claim → stance → 证据句 → 引文/拒答边界",
			Boundary:   "离线可用 /demo 只回放证据流；实时结论仍以当前后端与语料为准",
			FixtureTag: "demo-verify-golden",
		},
		{
			Title:      "黄金任务 2｜研究线索",
			Command:    "/review retrieval augmented generation 在科研问答中的证据链设计",
			Goal:       "固定展示现状、图谱关系、推荐线索与描述性趋势边界",
			Boundary:   "若图谱/推荐/趋势资产缺失，TUI 必须显示 unavailable/empty，不伪装成功",
			FixtureTag: "demo-review-golden",
		},
	}
}

func confidenceLabel(v float64) string {
	switch {
	case v >= 0.9:
		return fmt.Sprintf("高置信 %.2f", v)
	case v >= 0.7:
		return fmt.Sprintf("中置信 %.2f", v)
	case v > 0:
		return fmt.Sprintf("低置信 %.2f", v)
	default:
		return ""
	}
}

func evidenceDisplayAuthorized(policy displayPolicy) bool {
	return policy.Authorized
}

func safeJSONString(value any) string {
	raw, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	return string(raw)
}

func mapKeysSorted(value map[string]any) []string {
	keys := make([]string, 0, len(value))
	for k := range value {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
