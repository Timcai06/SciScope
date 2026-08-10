package main

import "time"

type turn struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}
type eventMeta struct {
	Runtime          string         `json:"runtime"`
	Node             string         `json:"node"`
	Phase            string         `json:"phase"`
	SessionID        string         `json:"session_id"`
	ElapsedMS        int            `json:"elapsed_ms"`
	Retry            bool           `json:"retry"`
	StructuredAnswer map[string]any `json:"structured_answer"`
}
type planMsg []string
type textMsg string
type toolCallMsg struct {
	name string
	args map[string]any
	meta eventMeta
}
type toolResultMsg struct {
	name   string
	result string
	meta   eventMeta
}
type reflectMsg string
type finalMsg string
type errMsg string
type doneMsg struct{}
type refreshTickMsg struct{}
type demoStartMsg string
type nodePulseMsg struct {
	kind string
	meta eventMeta
}

type transcriptEvent struct {
	Kind    string
	Tool    string
	Content string
}

type recoveryHint struct {
	Title     string
	Command   string
	Message   string
	Severity  string
	Inspect   string
	Retryable bool
}

type doctorCheck struct {
	Name   string
	Status string
	Detail string
}

type sessionFile struct {
	Index        int
	Path         string
	Name         string
	LastQuestion string
	ModTime      time.Time
	Size         int64
}

type loadedSession struct {
	Path         string
	Content      string
	LastQuestion string
}

type timelineEvent struct {
	Kind     string
	Tool     string
	Phase    string
	Label    string
	Detail   string
	Duration time.Duration
}

type evidencePaper struct {
	PaperID string   `json:"paper_id"`
	Title   string   `json:"标题"`
	Year    int      `json:"年份"`
	Authors []string `json:"作者"`
	Snippet string   `json:"摘要片段"`
}

type claimEvidence struct {
	PaperID          string        `json:"paper_id"`
	Title            string        `json:"标题"`
	Year             int           `json:"年份"`
	Similarity       float64       `json:"接地相似度"`
	Stance           string        `json:"立场"`
	Confidence       float64       `json:"置信度"`
	EvidenceSentence string        `json:"证据句"`
	ChunkUID         string        `json:"chunk_uid"`
	SourceField      string        `json:"source_field"`
	DisplayPolicy    displayPolicy `json:"display_policy"`
}

type claimResult struct {
	Claim            string               `json:"论断"`
	Verdict          string               `json:"支持等级"`
	TopSimilarity    float64              `json:"最高接地相似度"`
	Reason           string               `json:"理由"`
	RejectionReason  string               `json:"拒答原因"`
	Qualification    []string             `json:"限定条件"`
	Evidence         []claimEvidence      `json:"证据"`
	StructuredAnswer structuredAnswerCard `json:"structured_answer"`
}
