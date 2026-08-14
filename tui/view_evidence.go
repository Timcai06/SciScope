// view_evidence.go — T05-06 Evidence、Claim 与 Answer Contract 纯函数渲染层。
//
// 计划 5.6 节：Evidence 是 SciScope 的例外，不套用「少框」原则。Evidence 卡
// 使用 style_primitives.go 的 domainCard 基元（强领域对象，允许完整边框）；
// Answer Contract 压缩行使用 inlineBlock（普通无框块，缩进一行）。
//
// 颜色纪律：Warning 只用于 insufficient / degraded（证据不足、uncertainty、
// 边界提示）；Error 只用于真实执行失败——本层不渲染执行失败，因此完全不使用
// Error 语义；Evidence 的强调（序号、Stance 标签）用 Accent，SUPPORT 与
// REFUTE 共用同一 Accent 样式、视觉权重相当；置信度 / 相似度 / 审计链等
// 量值与溯源信息走灰阶（Muted / Faint）；本文件不出现散落 hex。
//
// 导出函数（全部为纯函数：输入显式参数、输出 string，不读取 model / 时钟
// 等外部状态；elapsed 由调用方显式传入）：
//
//	RenderEvidencePapersCard(papers []evidencePaper, maxShow int, elapsed time.Duration) string
//	  对应 renderToolResult 的 search_literature / summarize_field 分支：
//	  domainCard("evidence", "证据卡 N 篇")，逐条渲染
//	  Title / Year / Author / PaperID / Snippet。
//
//	RenderClaimEvidenceCard(cr claimResult, maxShow int, elapsed time.Duration) string
//	  对应 renderToolResult 的 verify_claim 分支：domainCard("evidence",
//	  "论断核查 · <verdict>")，逐条渲染 claimEvidence 的 Title / Year /
//	  PaperID / Stance / Similarity / Confidence / EvidenceSentence（仅
//	  display_policy 允许）/ SourceField（仅允许）/ ChunkUID 审计链 /
//	  hidden reason；len(Evidence)==0 时自动降级为 Evidence Insufficient 卡。
//
//	RenderEvidenceInsufficientCard(claim, verdict, reason string, qualification []string, elapsed time.Duration) string
//	  证据不足卡：Warning 色（不是 Error），文案明确「系统拒绝无证据结论」，
//	  不显示任何置信度 / 相似度数值（不伪造成功）。依赖失败（真实失败）
//	  仍由 recovery / error 路径表达，与本卡严格区分。
//
//	RenderAnswerContractCompressed(card structuredAnswerCard) string
//	  Answer Contract 默认压缩一行，如：`强支持 · 4 条证据 · 引文已验证`
//	  （verdict_label 原样 + 引文数 + citation_compliance 语义翻译）。
//	  详细字段见 RenderAnswerContractFull，schema 不删除、仅降权。
//
//	RenderAnswerContractFull(card structuredAnswerCard) string
//	  Answer Contract 完整版：domainCard("contract", "答案合同")，保留
//	  claim / uncertainty / citations / tool_basis / answer_mode /
//	  citation_compliance 全部 schema 字段，呈现降权（Muted 基色）。
//
//	StanceText(stance string) string
//	  Stance 语义真实映射：SUPPORT→支持、REFUTE/CONTRADICT→反驳、
//	  NEUTRAL→中立；未知值原样返回，空值返回空串。不携带颜色。

package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const (
	// defaultMaxEvidence 证据卡默认展示条数（与既有 renderToolResult 一致）。
	defaultMaxEvidence = 4
	// maxContractCitations 答案合同完整版默认展开的引文条数。
	maxContractCitations = 3
)

// StanceText 把 Stance 原始值映射为语义真实的中文标签（见文件头）。
func StanceText(stance string) string {
	switch strings.ToUpper(strings.TrimSpace(stance)) {
	case "SUPPORT":
		return "支持"
	case "REFUTE", "CONTRADICT", "CONTRADICTION", "反对":
		return "反驳"
	case "NEUTRAL", "N/A", "NA":
		return "中立"
	default:
		return strings.TrimSpace(stance)
	}
}

// stanceToken 渲染 Stance 标签。SUPPORT 与 REFUTE 走同一个 Accent 样式
// 函数，保证 supporting / contradicting 视觉权重相当（计划 5.6：不把
// refute 画成错误红）。
func stanceToken(stance string) string {
	label := StanceText(stance)
	if label == "" {
		return ""
	}
	return AccentText().Render(label)
}

// indexToken 证据序号：Accent 强调。
func indexToken(index int) string {
	return AccentText().Render(fmt.Sprintf("[%d]", index))
}

// RenderEvidencePapersCard 渲染 search_literature / summarize_field 证据卡。
func RenderEvidencePapersCard(papers []evidencePaper, maxShow int, elapsed time.Duration) string {
	if len(papers) == 0 {
		return ""
	}
	if maxShow <= 0 {
		maxShow = defaultMaxEvidence
	}
	body := make([]string, 0, maxShow*3+1)
	for i, p := range papers {
		if i >= maxShow {
			body = append(body, MutedText().Render(fmt.Sprintf("+%d 篇更多证据 · /timeline 查看完整证据链", len(papers)-i)))
			break
		}
		body = append(body, indexToken(i+1)+" "+PrimaryText().Render(clip(p.Title, 72)))
		meta := []string{}
		if p.PaperID != "" {
			meta = append(meta, MutedText().Render(p.PaperID))
		}
		if p.Year != 0 {
			meta = append(meta, MutedText().Render(fmt.Sprintf("%d", p.Year)))
		}
		if len(p.Authors) > 0 {
			meta = append(meta, MutedText().Render(strings.Join(p.Authors, ", ")))
		}
		if len(meta) > 0 {
			body = append(body, strings.Join(meta, " · "))
		}
		if p.Snippet != "" {
			body = append(body, PrimaryText().Render(clip(p.Snippet, 96)))
		}
	}
	title := fmt.Sprintf("证据卡 %d 篇", len(papers))
	if d := durationText(elapsed); d != "" {
		title += " · " + d
	}
	return domainCard("evidence", title, body)
}

// claimEvidenceRows 渲染单条 claimEvidence（verify_claim 证据）。
// Similarity 与 Confidence 使用不同标签分开展示，互不混淆。
func claimEvidenceRows(ev claimEvidence, index int) []string {
	rows := []string{indexToken(index) + " " + PrimaryText().Render(clip(ev.Title, 78))}
	meta := []string{}
	if ev.PaperID != "" {
		meta = append(meta, MutedText().Render(ev.PaperID))
	}
	if ev.Year != 0 {
		meta = append(meta, MutedText().Render(fmt.Sprintf("%d", ev.Year)))
	}
	if token := stanceToken(ev.Stance); token != "" {
		meta = append(meta, token)
	}
	if ev.Similarity > 0 {
		meta = append(meta, MutedText().Render(fmt.Sprintf("相似度 %.3f", ev.Similarity)))
	}
	if label := confidenceLabel(ev.Confidence); label != "" {
		meta = append(meta, MutedText().Render(label))
	}
	if len(meta) > 0 {
		rows = append(rows, strings.Join(meta, " · "))
	}
	if ev.ChunkUID != "" {
		rows = append(rows, FaintText().Render("审计链 · chunk "+clip(ev.ChunkUID, 12)))
	}
	if evidenceDisplayAuthorized(ev.DisplayPolicy) {
		if ev.SourceField != "" {
			rows = append(rows, FaintText().Render("来源链 · "+ev.SourceField))
		}
		if sentence := strings.TrimSpace(ev.EvidenceSentence); sentence != "" {
			rows = append(rows, PrimaryText().Render(clip(sentence, 96)))
		}
	} else if reason := strings.TrimSpace(ev.DisplayPolicy.Reason); reason != "" {
		rows = append(rows, MutedText().Render("正文隐藏 · "+clip(reason, 88)))
	}
	return rows
}

// RenderClaimEvidenceCard 渲染 verify_claim 论断核查卡；无证据时降级为
// Evidence Insufficient 卡。display_policy 语义复用 contracts.go 的
// evidenceDisplayAuthorized（fail-closed 不可绕过）。
func RenderClaimEvidenceCard(cr claimResult, maxShow int, elapsed time.Duration) string {
	if strings.TrimSpace(cr.Verdict) == "" {
		return ""
	}
	reason := strings.TrimSpace(cr.RejectionReason)
	if reason == "" {
		reason = strings.TrimSpace(cr.Reason)
	}
	if len(cr.Evidence) == 0 {
		return RenderEvidenceInsufficientCard(cr.Claim, cr.Verdict, reason, cr.Qualification, elapsed)
	}
	if maxShow <= 0 {
		maxShow = defaultMaxEvidence
	}
	body := []string{}
	if cr.Claim != "" {
		body = append(body, PrimaryText().Render(clip(cr.Claim, 96)))
	}
	for _, hint := range cr.Qualification {
		body = append(body, MutedText().Render("限定条件 · "+clip(hint, 92)))
	}
	for i, ev := range cr.Evidence {
		if i >= maxShow {
			body = append(body, MutedText().Render(fmt.Sprintf("+%d 条更多证据 · /timeline 查看", len(cr.Evidence)-i)))
			break
		}
		body = append(body, claimEvidenceRows(ev, i+1)...)
	}
	if reason != "" && cr.Verdict != "强支持" && cr.Verdict != "部分支持" {
		body = append(body, WarningText().Render("边界: "+clip(reason, 90)))
	}
	title := "论断核查 · " + cr.Verdict
	if cr.TopSimilarity > 0 {
		title += fmt.Sprintf(" · 最高相似度 %.3f", cr.TopSimilarity)
	}
	if d := durationText(elapsed); d != "" {
		title += " · " + d
	}
	return domainCard("evidence", title, body)
}

// RenderEvidenceInsufficientCard 渲染证据不足卡：Warning 色（不是 Error）、
// 明确「系统拒绝无证据结论」、不显示任何置信度 / 相似度数值。
func RenderEvidenceInsufficientCard(claim, verdict, reason string, qualification []string, elapsed time.Duration) string {
	verdictLabel := strings.TrimSpace(verdict)
	if verdictLabel == "" {
		verdictLabel = "证据不足"
	}
	body := []string{}
	if claim != "" {
		body = append(body, PrimaryText().Render(clip(claim, 96)))
	}
	body = append(body, WarningText().Render("证据不足: 系统拒绝无证据结论"))
	if reason == "" {
		reason = "未找到可核验的证据。"
	}
	body = append(body, WarningText().Render("理由: "+clip(reason, 88)))
	for _, hint := range qualification {
		body = append(body, MutedText().Render("限定条件 · "+clip(hint, 92)))
	}
	title := "论断核查 · " + verdictLabel
	if d := durationText(elapsed); d != "" {
		title += " · " + d
	}
	return domainCard("evidence", title, body)
}

// answerContractEmpty 与既有 renderStructuredAnswerCard 相同的空卡 gate：
// Status 缺失，或 status 与 citation_compliance 同时 not_applicable 时不渲染。
func answerContractEmpty(card structuredAnswerCard) bool {
	return card.Status == "" || (card.Status == "not_applicable" && card.CitationCompliance == "not_applicable")
}

// contractVerdictLabel 取 verdict_label，缺失时回退 status。
func contractVerdictLabel(card structuredAnswerCard) string {
	if card.VerdictLabel != "" {
		return card.VerdictLabel
	}
	return card.Status
}

// contractComplianceText 把 citation_compliance 翻译为一行内的中文语义。
func contractComplianceText(compliance string) string {
	switch compliance {
	case "ok":
		return "引文已验证"
	case "", "not_applicable":
		return "引文未验证"
	default:
		return "引文 " + compliance
	}
}

// RenderAnswerContractCompressed Answer Contract 默认压缩一行（计划 5.6）：
//
//	强支持 · 4 条证据 · 引文已验证
//
// verdict 用 Accent 强调，计数与合规状态用 Muted；详细字段保留在
// RenderAnswerContractFull（schema 不删除，仅降权）。
func RenderAnswerContractCompressed(card structuredAnswerCard) string {
	if answerContractEmpty(card) {
		return ""
	}
	parts := []string{
		AccentText().Render(contractVerdictLabel(card)),
		MutedText().Render(fmt.Sprintf("%d 条证据", len(card.Citations))),
		MutedText().Render(contractComplianceText(card.CitationCompliance)),
	}
	return inlineBlock([]string{strings.Join(parts, " · ")})
}

// RenderAnswerContractFull Answer Contract 完整版：保留全部 schema 字段
// （claim / uncertainty / citations / tool_basis / answer_mode /
// citation_compliance），呈现降权（Muted 基色；uncertainty 属 degraded，
// 用 Warning；审计链与来源链用 Faint；证据正文仍受 display_policy
// fail-closed 保护）。
func RenderAnswerContractFull(card structuredAnswerCard) string {
	if answerContractEmpty(card) {
		return ""
	}
	label := contractVerdictLabel(card)
	metaParts := []string{label}
	if card.AnswerMode == "generative_non_evidentiary" {
		metaParts = append(metaParts, "non-evidentiary")
	}
	if card.CitationCompliance != "" && card.CitationCompliance != "not_applicable" {
		metaParts = append(metaParts, "citations "+card.CitationCompliance)
	}
	body := []string{MutedText().Render(strings.Join(metaParts, " · "))}
	if card.Claim != "" {
		body = append(body, PrimaryText().Render("claim   "+clip(card.Claim, 96)))
	}
	if card.Uncertainty.Category != "" && card.Uncertainty.Category != "none" {
		line := "uncert  " + card.Uncertainty.Category
		if card.Uncertainty.CalibratedRejection {
			line += " · calibrated rejection"
		}
		body = append(body, WarningText().Render(line))
		if msg := strings.TrimSpace(card.Uncertainty.Message); msg != "" {
			body = append(body, WarningText().Render("reason  "+clip(msg, 96)))
		}
		for _, hint := range card.Uncertainty.QualificationHints {
			body = append(body, MutedText().Render("limit   "+clip(hint, 96)))
		}
	}
	if len(card.Citations) == 0 {
		body = append(body, MutedText().Render("source  无可显示引文；保持 fail-closed，不把生成文本当证据。"))
	} else {
		for i, citation := range card.Citations {
			if i >= maxContractCitations {
				body = append(body, MutedText().Render(fmt.Sprintf("+%d 条更多引文 · /timeline 查看调用过程", len(card.Citations)-i)))
				break
			}
			title := citation.Title
			if title == "" {
				title = citation.PaperID
			}
			body = append(body, indexToken(i+1)+" "+PrimaryText().Render(clip(title, 76)))
			meta := []string{}
			if citation.PaperID != "" {
				meta = append(meta, MutedText().Render(citation.PaperID))
			}
			if citation.Year != 0 {
				meta = append(meta, MutedText().Render(fmt.Sprintf("%d", citation.Year)))
			}
			if token := stanceToken(citation.Stance); token != "" {
				meta = append(meta, token)
			}
			if lab := confidenceLabel(citation.Confidence); lab != "" {
				meta = append(meta, MutedText().Render(lab))
			}
			if len(meta) > 0 {
				body = append(body, strings.Join(meta, " · "))
			}
			if citation.ChunkUID != "" {
				body = append(body, FaintText().Render("审计链 chunk "+clip(citation.ChunkUID, 12)))
			}
			if evidenceDisplayAuthorized(citation.DisplayPolicy) {
				if citation.SourceField != "" {
					body = append(body, FaintText().Render("来源链 "+citation.SourceField))
				}
				if sentence := strings.TrimSpace(citation.EvidenceSentence); sentence != "" {
					body = append(body, PrimaryText().Render(clip(sentence, 96)))
				}
			} else if reason := strings.TrimSpace(citation.DisplayPolicy.Reason); reason != "" {
				body = append(body, MutedText().Render("正文隐藏 · "+clip(reason, 88)))
			}
		}
	}
	if len(card.ToolBasis) > 0 {
		body = append(body, MutedText().Render("basis   "+strings.Join(card.ToolBasis, ", ")))
	}
	return domainCard("contract", "答案合同", body)
}

// ---- T05-06 接线封装（由主线在接线时补充；仍是纯函数）----

// renderEvidenceToolResult 是 toolResultMsg 的证据类工具入口：evidence 工具走
// typed 渲染层，其余工具回退旧 renderToolResult。
func renderEvidenceToolResult(name, result string, width int, elapsed time.Duration) string {
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			return RenderEvidencePapersCard(papers, defaultMaxEvidence, elapsed)
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			if len(cr.Evidence) == 0 {
				reason := strings.TrimSpace(cr.RejectionReason)
				if reason == "" {
					reason = strings.TrimSpace(cr.Reason)
				}
				if reason == "" {
					reason = "未找到可核验的证据。"
				}
				return RenderEvidenceInsufficientCard(cr.Claim, cr.Verdict, reason, cr.Qualification, elapsed)
			}
			return RenderClaimEvidenceCard(cr, defaultMaxEvidence, elapsed)
		}
	}
	return renderToolResult(name, result, width, elapsed)
}

// renderStructuredAnswerCardCompressed 是 doneMsg sidecar 的默认入口：Answer
// Contract 压缩为一行（详细字段保留在 RenderAnswerContractFull，供 /timeline
// 或后续 expandable 使用）。
func renderStructuredAnswerCardCompressed(meta map[string]any, width int) string {
	contract, ok := parseStructuredAnswerValue(meta)
	if !ok {
		return ""
	}
	if contract.Status == "" || (contract.Status == "not_applicable" && contract.CitationCompliance == "not_applicable") {
		return ""
	}
	return RenderAnswerContractCompressed(contract)
}

// contractSummaryText 返回 answer-contract 的一行纯文本摘要（渲染层上色，
// 不预渲染 ANSI——语义化 Block 原则）。
func contractSummaryText(meta map[string]any) string {
	contract, ok := parseStructuredAnswerValue(meta)
	if !ok {
		return ""
	}
	if contract.Status == "" || (contract.Status == "not_applicable" && contract.CitationCompliance == "not_applicable") {
		return ""
	}
	parts := []string{contractVerdictLabel(contract)}
	parts = append(parts, fmt.Sprintf("%d 条证据", len(contract.Citations)))
	parts = append(parts, contractComplianceText(contract.CitationCompliance))
	return strings.Join(parts, " · ")
}

// isEvidenceTool 判断工具是否属于证据类（typed BlockEvidence kind）。
func isEvidenceTool(name string) bool {
	switch name {
	case "search_literature", "summarize_field", "verify_claim":
		return true
	}
	return false
}
