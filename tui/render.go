package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func asciiBrand(width int) string {
	if width < 86 {
		return stAccent.Render("SciScope")
	}
	lines := []string{
		"███████╗ ██████╗██╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗",
		"██╔════╝██╔════╝██║██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝",
		"███████╗██║     ██║███████╗██║     ██║   ██║██████╔╝█████╗  ",
		"╚════██║██║     ██║╚════██║██║     ██║   ██║██╔═══╝ ██╔══╝  ",
		"███████║╚██████╗██║███████║╚██████╗╚██████╔╝██║     ███████╗",
		"╚══════╝ ╚═════╝╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝     ╚══════╝",
	}
	return stAccent.Render(strings.Join(lines, "\n"))
}

func renderSplash(width int, sessions []sessionFile) string {
	_ = sessions
	if width < 60 {
		width = 60
	}
	subtitle := "证据接地的科研文献智能体"
	if width < 76 {
		subtitle = "证据接地的科研智能体"
	}
	prompt := "从一个论断、论文、主题或趋势开始;输入 / 查看命令。"
	body := []string{
		asciiBrand(width),
		stInk.Render("科研智能体终端"),
		stFaint.Render(subtitle),
		"",
		stConn.Render(strings.Repeat("─", minInt(width-12, 72))),
		stFaint.Render(prompt),
		"",
	}
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(cAccent).
		Padding(1, 2).
		Width(width - 4).
		Render(strings.Join(body, "\n"))
}

func renderThemeBlock() string {
	lines := []string{stFaint.Render("  可用主题:")}
	for _, name := range themeOrder {
		theme := themes[name]
		mark := " "
		style := stCmd
		if name == currentTheme {
			mark = "◆"
			style = stAccent
		}
		lines = append(lines, style.Render(fmt.Sprintf("  %s %-8s %s · %s", mark, theme.Name, theme.Title, theme.Desc)))
	}
	lines = append(lines, "")
	lines = append(lines, stFaint.Render("  用法: /theme paper  或启动前设置 SCISCOPE_TUI_THEME=paper"))
	return strings.Join(lines, "\n")
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func splashStatusLines() []string {
	dir := sessionDir()
	return []string{
		stFaint.Render("Backend  check with /doctor"),
		stFaint.Render("LLM      check with /doctor"),
		stFaint.Render("Sessions " + clip(dir, 30)),
	}
}

func recentSplashLines(sessions []sessionFile) []string {
	if len(sessions) == 0 {
		return []string{
			stFaint.Render("暂无本地会话"),
			stFaint.Render("/demo 播放黄金演示流"),
			stFaint.Render("完成回答后自动保存"),
		}
	}
	lines := []string{}
	for i, session := range sessions {
		if i >= 3 {
			break
		}
		question := session.LastQuestion
		if question == "" {
			question = strings.TrimSuffix(session.Name, filepath.Ext(session.Name))
		}
		lines = append(lines, stFaint.Render(fmt.Sprintf("/resume %d  %s", session.Index, clip(question, 32))))
		lines = append(lines, stFaint.Render("  "+session.ModTime.Format("01-02 15:04")))
	}
	return lines
}

// kindIcon previews what a command does before it is run: ◇ expands into an
// agent question, ▤ opens a submenu, • runs instantly.
func kindIcon(k slashCommandKind) string {
	switch k {
	case commandPrompt:
		return "◇"
	case commandUI:
		return "▤"
	default:
		return "•"
	}
}

// styleUsageCell dims a usage hint but renders its "<...>" argument placeholder in
// the accent colour, so commands that take an argument stand out at a glance.
func styleUsageCell(cell string) string {
	if i := strings.IndexByte(cell, '<'); i >= 0 {
		return stFaint.Render(cell[:i]) + stAccent.Render(cell[i:])
	}
	return stFaint.Render(cell)
}

func (m model) renderCommandPalette(width int) string {
	if width < 48 {
		width = 48
	}
	matches := filterCmds(m.ti.Value())
	if len(matches) == 0 {
		return ""
	}
	inner := width - 6
	if inner < 38 {
		inner = 38
	}
	idx := m.menuIdx % len(matches)
	cursorW, iconW, cmdW, titleW, keyW := 2, 2, 12, 10, 18
	descW := inner - cursorW - iconW - cmdW - titleW - keyW
	if descW < 10 {
		descW = 10
	}
	pad := func(s string, w int) string { return lipgloss.NewStyle().Width(w).Render(s) }
	rows := []string{
		stAccent.Render("命令启动器") + stFaint.Render("  · Enter 执行 · Esc 关闭 · / 命令"),
	}
	lastCat := ""
	for i, c := range matches {
		if c.category != lastCat { // group commands under faint category headers
			rows = append(rows, stFaint.Render("  "+c.category))
			lastCat = c.category
		}
		sel := i == idx
		marker := "  "
		if sel {
			marker = "▶ "
		}
		cells := []string{
			pad(marker, cursorW),
			pad(kindIcon(c.kind), iconW),
			pad(c.cmd, cmdW),
			pad(clipWidth(c.title, titleW-1), titleW),
			pad(clipWidth(c.desc, descW-1), descW),
			pad(clipWidth(c.key, keyW-1), keyW),
		}
		if sel { // uniform high-contrast highlight for the selected row
			rows = append(rows, stSelCmd.Width(inner).Render(strings.Join(cells, "")))
			continue
		}
		styled := stFaint.Render(cells[0]) + stAccent.Render(cells[1]) + stInk.Render(cells[2]) +
			stMuted.Render(cells[3]) + stFaint.Render(cells[4]) + styleUsageCell(cells[5])
		rows = append(rows, lipgloss.NewStyle().Width(inner).Render(styled))
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(rows, "\n"))
}

func durationText(d time.Duration) string {
	if d <= 0 {
		return ""
	}
	return fmt.Sprintf("%.1fs", d.Seconds())
}

func permissionNotice(name string) (string, bool) {
	switch name {
	case "export_bibliography":
		return "权限提示: 引文导出会生成可复制的外部文本，请确认导出内容适合写入报告或会话记录。", true
	default:
		return "", false
	}
}

func toolResultLabel(name, result string) string {
	if strings.HasPrefix(result, "[未执行]") {
		return "校验拦截"
	}
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			return fmt.Sprintf("证据卡 %d 篇", len(papers))
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			if cr.TopSimilarity > 0 {
				return fmt.Sprintf("论断核查 · %s · %.3f", cr.Verdict, cr.TopSimilarity)
			}
			return "论断核查 · " + cr.Verdict
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			return fmt.Sprintf("趋势卡 %d 条", len(rows))
		}
	}
	return "工具返回"
}

func timelineMarkdownBody(events []timelineEvent) string {
	lines := []string{}
	lastPhase := ""
	for _, ev := range events {
		phase := eventPhase(ev)
		if phase != lastPhase {
			lines = append(lines, "### "+phase)
			lastPhase = phase
		}
		label := strings.TrimSpace(ev.Label)
		if label == "" {
			label = toolPlainLabel(ev.Tool)
		}
		line := "- " + label
		if ev.Detail != "" {
			line += ": " + ev.Detail
		}
		if d := durationText(ev.Duration); d != "" {
			line += " (" + d + ")"
		}
		lines = append(lines, line)
	}
	return strings.Join(lines, "\n")
}

func renderTimelineMarkdown(events []timelineEvent) string {
	body := timelineMarkdownBody(events)
	if body == "" {
		return ""
	}
	return "## 科研工作流时间线\n\n" + body + "\n"
}

func renderTimelineBlock(events []timelineEvent) string {
	if len(events) == 0 {
		return panelRow("timeline", "本轮执行时间线", "empty", []string{
			"暂无本轮执行轨迹。",
			"先输入一个科研问题, 或运行 /demo 播放黄金演示流。",
		})
	}
	body := []string{}
	lastPhase := ""
	for _, ev := range events {
		phase := eventPhase(ev)
		if phase != lastPhase {
			body = append(body, phase)
			lastPhase = phase
		}
		label := ev.Label
		if label == "" {
			label = toolPlainLabel(ev.Tool)
		}
		line := "  - " + label
		if ev.Detail != "" {
			line += " · " + ev.Detail
		}
		if d := durationText(ev.Duration); d != "" {
			line += " · " + d
		}
		body = append(body, line)
	}
	return panelRow("timeline", "本轮执行时间线", fmt.Sprintf("%d events", len(events)), body)
}

func renderPlanBlock(plan planMsg) string {
	body := []string{}
	for i, step := range plan {
		body = append(body, fmt.Sprintf("[%d] %s", i+1, step))
	}
	return panelRow("thinking", "思考过程", fmt.Sprintf("%d 步", len(plan)), body)
}

func renderToolCallBlock(name, args string) string {
	body := []string{}
	if strings.TrimSpace(args) != "" {
		body = append(body, args)
	}
	return panelRow("action", toolPlainLabel(name), "tool call", body)
}

func renderReflectBlock(s string) string {
	return panelRow("thinking", "自我纠错", "", []string{s})
}

func renderStructuredAnswerCard(meta map[string]any, width int) string {
	contract, ok := parseStructuredAnswerValue(meta)
	if !ok {
		return ""
	}
	if contract.Status == "" || (contract.Status == "not_applicable" && contract.CitationCompliance == "not_applicable") {
		return ""
	}
	label := contract.VerdictLabel
	if label == "" {
		label = contract.Status
	}
	metaParts := []string{label}
	if contract.AnswerMode == "generative_non_evidentiary" {
		metaParts = append(metaParts, "non-evidentiary")
	}
	if contract.CitationCompliance != "" && contract.CitationCompliance != "not_applicable" {
		metaParts = append(metaParts, "citations "+contract.CitationCompliance)
	}
	body := []string{}
	if contract.Claim != "" {
		body = append(body, "claim   "+clip(contract.Claim, 96))
	}
	if contract.Uncertainty.Category != "" && contract.Uncertainty.Category != "none" {
		line := "uncert  " + contract.Uncertainty.Category
		if contract.Uncertainty.CalibratedRejection {
			line += " · calibrated rejection"
		}
		body = append(body, line)
		if msg := strings.TrimSpace(contract.Uncertainty.Message); msg != "" {
			body = append(body, "reason  "+clip(msg, 96))
		}
		for _, hint := range contract.Uncertainty.QualificationHints {
			body = append(body, "limit   "+clip(hint, 96))
		}
	}
	if len(contract.Citations) == 0 {
		body = append(body, "source  无可显示引文；保持 fail-closed，不把生成文本当证据。")
	} else {
		for i, citation := range contract.Citations {
			if i >= 3 {
				body = append(body, fmt.Sprintf("+%d 条更多引文 · /timeline 查看调用过程", len(contract.Citations)-i))
				break
			}
			title := citation.Title
			if title == "" {
				title = citation.PaperID
			}
			body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(title, 76)))
			meta := []string{}
			if citation.PaperID != "" {
				meta = append(meta, citation.PaperID)
			}
			if citation.Year != 0 {
				meta = append(meta, fmt.Sprintf("%d", citation.Year))
			}
			if citation.Stance != "" {
				meta = append(meta, citation.Stance)
			}
			if label := confidenceLabel(citation.Confidence); label != "" {
				meta = append(meta, label)
			}
			if len(meta) > 0 {
				body = append(body, strings.Join(meta, " · "))
			}
			if citation.ChunkUID != "" {
				body = append(body, "审计链 chunk "+clip(citation.ChunkUID, 12))
			}
			if evidenceDisplayAuthorized(citation.DisplayPolicy) {
				prov := []string{}
				if citation.SourceField != "" {
					prov = append(prov, citation.SourceField)
				}
				if len(prov) > 0 {
					body = append(body, "来源链 "+strings.Join(prov, " · "))
				}
			}
			if evidenceDisplayAuthorized(citation.DisplayPolicy) {
				if sentence := strings.TrimSpace(citation.EvidenceSentence); sentence != "" {
					body = append(body, clip(sentence, 96))
				}
			} else if strings.TrimSpace(citation.DisplayPolicy.Reason) != "" {
				body = append(body, "正文隐藏 · "+clip(citation.DisplayPolicy.Reason, 88))
			}
		}
	}
	if len(contract.ToolBasis) > 0 {
		body = append(body, "basis   "+strings.Join(contract.ToolBasis, ", "))
	}
	return panelRow("contract", "答案合同", strings.Join(metaParts, " · "), body)
}

func renderEnvelopeCard(kind, title string, env resultEnvelope, elapsed time.Duration, body []string) string {
	meta := env.Status
	if d := durationText(elapsed); d != "" {
		meta += " · " + d
	}
	if env.DataSource != "" {
		body = append(body, "source  "+env.DataSource)
	}
	if env.UnavailableReason != "" {
		body = append(body, "reason  "+env.UnavailableReason)
	}
	if env.DegradedReason != "" {
		body = append(body, "degrade "+env.DegradedReason)
	}
	if note := strings.TrimSpace(env.Note); note != "" {
		body = append(body, "note    "+clip(note, 96))
	}
	return panelRow(kind, title, meta, body)
}

func renderToolResult(name, result string, width int, elapsed time.Duration) string {
	// A validation gate rejected the call (e.g. fabricated paper_id). Surface it
	// as a distinct recovery card — the model also gets this back and self-corrects.
	if strings.HasPrefix(result, "[未执行]") {
		reason := strings.TrimSpace(strings.TrimPrefix(result, "[未执行]"))
		return panelRow("recovery", "校验拦截 · "+toolPlainLabel(name), durationText(elapsed), []string{stWarn.Render(reason)})
	}
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			body := []string{}
			for i, p := range papers {
				if i >= 4 {
					body = append(body, fmt.Sprintf("+%d 篇更多证据 · /timeline 查看完整证据链", len(papers)-i))
					break
				}
				meta := []string{p.PaperID}
				if p.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", p.Year))
				}
				if len(p.Authors) > 0 {
					meta = append(meta, strings.Join(p.Authors, ", "))
				}
				body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(p.Title, 72)))
				body = append(body, strings.Join(meta, " · "))
				if p.Snippet != "" {
					body = append(body, clip(p.Snippet, 96))
				}
			}
			return panelRow("evidence", fmt.Sprintf("证据卡 %d 篇", len(papers)), durationText(elapsed), body)
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			meta := cr.Verdict
			if cr.TopSimilarity > 0 {
				meta += fmt.Sprintf(" · %.3f", cr.TopSimilarity)
			}
			if d := durationText(elapsed); d != "" {
				meta += " · " + d
			}
			body := []string{}
			if cr.Claim != "" {
				body = append(body, clip(cr.Claim, 96))
			}
			reason := strings.TrimSpace(cr.RejectionReason)
			if reason == "" {
				reason = strings.TrimSpace(cr.Reason)
			}
			if len(cr.Evidence) == 0 {
				if reason == "" {
					reason = "未找到可核验的证据。"
				}
				body = append(body, stWarn.Render("证据不足: "+reason))
			}
			for _, hint := range cr.Qualification {
				body = append(body, "限定条件 · "+clip(hint, 92))
			}
			for i, ev := range cr.Evidence {
				if i >= 4 {
					body = append(body, fmt.Sprintf("+%d 条更多证据 · /timeline 查看", len(cr.Evidence)-i))
					break
				}
				meta := []string{ev.PaperID}
				if ev.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", ev.Year))
				}
				if ev.Stance != "" {
					meta = append(meta, ev.Stance)
				}
				if ev.Similarity > 0 {
					meta = append(meta, fmt.Sprintf("相似度 %.3f", ev.Similarity))
				}
				if label := confidenceLabel(ev.Confidence); label != "" {
					meta = append(meta, label)
				}
				body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(ev.Title, 78)))
				body = append(body, strings.Join(meta, " · "))
				if ev.ChunkUID != "" {
					body = append(body, "审计链 · chunk "+clip(ev.ChunkUID, 12))
				}
				if evidenceDisplayAuthorized(ev.DisplayPolicy) {
					prov := []string{}
					if ev.SourceField != "" {
						prov = append(prov, ev.SourceField)
					}
					if len(prov) > 0 {
						body = append(body, "来源链 · "+strings.Join(prov, " · "))
					}
					if sentence := strings.TrimSpace(ev.EvidenceSentence); sentence != "" {
						body = append(body, clip(sentence, 96))
					}
				} else if strings.TrimSpace(ev.DisplayPolicy.Reason) != "" {
					body = append(body, "正文隐藏 · "+clip(ev.DisplayPolicy.Reason, 88))
				}
			}
			if reason != "" && len(cr.Evidence) > 0 && cr.Verdict != "强支持" && cr.Verdict != "部分支持" {
				body = append(body, stWarn.Render("边界: "+clip(reason, 90)))
			}
			return panelRow("verify", "论断核查", meta, body)
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			body := []string{}
			for i, row := range rows {
				if i >= 3 {
					body = append(body, fmt.Sprintf("+%d 条更多趋势 · /timeline 查看", len(rows)-i))
					break
				}
				kw := fmt.Sprintf("%v", row["关键词"])
				body = append(body, fmt.Sprintf("[%d] %s · 方向 %s · 阶段 %s · 依据 %s", i+1, kw, trendDirection(row), trendStage(row), trendBasis(row)))
			}
			return panelRow("trend", fmt.Sprintf("趋势卡 %d 条", len(rows)), durationText(elapsed), body)
		}
		if env, ok := parseResultEnvelope(result); ok {
			body := []string{}
			if policy := env.TrendPolicy; len(policy) > 0 {
				if value, ok := policy["descriptive_only"].(bool); ok && value {
					body = append(body, "policy  仅描述性趋势；不输出未来数值预测")
				}
			}
			rows, _ := env.Results.([]any)
			for i, item := range rows {
				if i >= 3 {
					body = append(body, fmt.Sprintf("+%d 条更多趋势 · /timeline 查看", len(rows)-i))
					break
				}
				row, _ := item.(map[string]any)
				body = append(body, fmt.Sprintf("[%d] %v · 方向 %s · 阶段 %s · 依据 %s", i+1, row["关键词"], trendDirection(row), trendStage(row), trendBasis(row)))
			}
			if len(rows) == 0 && env.Status != "ok" {
				body = append(body, "结果为空；保持 fail-closed。")
			}
			return renderEnvelopeCard("trend", "趋势卡", env, elapsed, body)
		}
	case "recommend_papers":
		if env, ok := parseResultEnvelope(result); ok {
			body := []string{}
			if queryID := fieldText(env.Query, "paper_id"); queryID != "" {
				body = append(body, "query   "+queryID)
			}
			rows, _ := env.Results.([]any)
			for i, item := range rows {
				if i >= 3 {
					body = append(body, fmt.Sprintf("+%d 条更多推荐 · /timeline 查看", len(rows)-i))
					break
				}
				row, _ := item.(map[string]any)
				body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(fieldText(row, "title"), 78)))
				meta := []string{}
				if value := fieldText(row, "paper_id"); value != "" {
					meta = append(meta, value)
				}
				if value := fieldText(row, "year"); value != "" {
					meta = append(meta, value)
				}
				if value := fieldText(row, "field"); value != "" {
					meta = append(meta, value)
				}
				if value := fieldText(row, "similarity"); value != "" {
					meta = append(meta, "相似度 "+clip(value, 8))
				}
				if len(meta) > 0 {
					body = append(body, strings.Join(meta, " · "))
				}
				if keywords, ok := row["shared_keywords"].([]any); ok && len(keywords) > 0 {
					parts := []string{}
					for _, kw := range keywords {
						parts = append(parts, fmt.Sprintf("%v", kw))
					}
					body = append(body, "关键词 · "+strings.Join(parts, ", "))
				}
				if factors, ok := row["factors"].(map[string]any); ok && len(factors) > 0 {
					keys := mapKeysSorted(factors)
					parts := []string{}
					for _, key := range keys {
						parts = append(parts, fmt.Sprintf("%s=%v", key, factors[key]))
					}
					body = append(body, "推荐理由 · "+strings.Join(parts, " · "))
				}
			}
			if len(rows) == 0 && env.Status != "ok" {
				body = append(body, "当前无可展示推荐；不伪造语义近邻。")
			}
			return renderEnvelopeCard("recommend", "论文推荐", env, elapsed, body)
		}
	case "query_knowledge_graph":
		if env, ok := parseResultEnvelope(result); ok {
			body := []string{}
			if kind := fieldText(env.Query, "type"); kind != "" {
				line := "query   " + kind
				if center := fieldText(env.Query, "center"); center != "" {
					line += " · " + center
				} else if value := fieldText(env.Query, "value"); value != "" {
					line += " · " + value
				}
				body = append(body, line)
			}
			switch results := env.Results.(type) {
			case map[string]any:
				if paper, ok := results["paper"].(map[string]any); ok {
					body = append(body, "paper   "+clip(fieldText(paper, "title"), 78))
				}
				if rels, ok := results["relations"].(map[string]any); ok && len(rels) > 0 {
					relNames := mapKeysSorted(rels)
					body = append(body, "关系   "+strings.Join(relNames, ", "))
				}
				if neighbours, ok := results["neighbours"].([]any); ok {
					for i, item := range neighbours {
						if i >= 3 {
							body = append(body, fmt.Sprintf("+%d 条更多关系 · /timeline 查看", len(neighbours)-i))
							break
						}
						row, _ := item.(map[string]any)
						body = append(body, fmt.Sprintf("[%d] %s → %s", i+1, fieldText(row, "relation"), clip(fieldText(row, "target_label"), 54)))
						if prov, ok := row["provenance"].(map[string]any); ok {
							meta := []string{}
							if pid := fieldText(prov, "paper_id"); pid != "" {
								meta = append(meta, pid)
							}
							if status := fieldText(prov, "record_sha256_status"); status != "" {
								meta = append(meta, "hash "+status)
							}
							if len(meta) > 0 {
								body = append(body, "来源链 · "+strings.Join(meta, " · "))
							}
						}
					}
				}
				if entity, ok := results["entity"].(map[string]any); ok {
					body = append(body, "entity  "+clip(fieldText(entity, "label"), 72))
				}
				if papers, ok := results["papers"].([]any); ok && len(papers) > 0 {
					parts := []string{}
					for i, pid := range papers {
						if i >= 5 {
							break
						}
						parts = append(parts, fmt.Sprintf("%v", pid))
					}
					body = append(body, "papers  "+strings.Join(parts, ", "))
				}
			case []any:
				for i, item := range results {
					if i >= 3 {
						body = append(body, fmt.Sprintf("+%d 条更多结果 · /timeline 查看", len(results)-i))
						break
					}
					row, _ := item.(map[string]any)
					terms := fieldText(row, "top_terms")
					if terms == "" {
						terms = clip(safeJSONString(row), 88)
					}
					body = append(body, fmt.Sprintf("[%d] %s", i+1, terms))
				}
			}
			if len(body) == 0 {
				body = append(body, "当前无图谱结果；保持 fail-closed。")
			}
			return renderEnvelopeCard("graph", "知识图谱", env, elapsed, body)
		}
	case "list_disputes":
		if env, ok := parseDisputeEnvelope(result); ok {
			body := []string{}
			if env.Count == 0 {
				body = append(body, "当前资产中尚无满足条件的争议；空结果不等于不存在科学分歧。")
			}
			for i, row := range env.Rows {
				if i >= 3 {
					body = append(body, fmt.Sprintf("+%d 条更多争议 · /timeline 查看", len(env.Rows)-i))
					break
				}
				body = append(body, fmt.Sprintf("[%d] %s", i+1, clip(fieldText(row, "claim"), 76)))
				body = append(body, strings.Join([]string{
					"support " + fieldText(row, "support_count"),
					"contradict " + fieldText(row, "contradict_count"),
					"papers " + fieldText(row, "paper_count"),
				}, " · "))
				if ids, ok := row["paper_ids"].([]any); ok && len(ids) > 0 {
					parts := []string{}
					for j, id := range ids {
						if j >= 4 {
							break
						}
						parts = append(parts, fmt.Sprintf("%v", id))
					}
					body = append(body, "paper_ids · "+strings.Join(parts, ", "))
				}
			}
			if env.Border != "" {
				body = append(body, "边界   "+clip(env.Border, 96))
			}
			return panelRow("dispute", "争议前线", durationText(elapsed), body)
		}
	}
	return panelRow("result", toolPlainLabel(name), durationText(elapsed), []string{preview(result)})
}

func summarizeToolResultMarkdown(name, result string) string {
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			lines := []string{}
			for i, p := range papers {
				if i >= 8 {
					lines = append(lines, fmt.Sprintf("- 另有 %d 篇证据未展开", len(papers)-i))
					break
				}
				meta := []string{p.PaperID}
				if p.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", p.Year))
				}
				if len(p.Authors) > 0 {
					meta = append(meta, strings.Join(p.Authors, ", "))
				}
				lines = append(lines, fmt.Sprintf("- [%d] %s", i+1, p.Title))
				if len(meta) > 0 {
					lines = append(lines, "  "+strings.Join(meta, " · "))
				}
				if p.Snippet != "" {
					lines = append(lines, "  "+p.Snippet)
				}
			}
			return strings.Join(lines, "\n")
		}
	case "verify_claim":
		var cr claimResult
		if json.Unmarshal([]byte(result), &cr) == nil && cr.Verdict != "" {
			head := fmt.Sprintf("论断: %s\n支持等级: %s", cr.Claim, cr.Verdict)
			if cr.TopSimilarity > 0 {
				head += fmt.Sprintf("\n最高接地相似度: %.3f", cr.TopSimilarity)
			}
			if len(cr.Evidence) == 0 {
				reason := strings.TrimSpace(cr.Reason)
				if reason == "" {
					reason = "未找到可核验的证据。"
				}
				head += "\n证据不足: " + reason
			}
			lines := []string{head}
			for i, ev := range cr.Evidence {
				if i >= 8 {
					break
				}
				meta := []string{ev.PaperID}
				if ev.Year != 0 {
					meta = append(meta, fmt.Sprintf("%d", ev.Year))
				}
				if ev.Similarity > 0 {
					meta = append(meta, fmt.Sprintf("相似度 %.3f", ev.Similarity))
				}
				lines = append(lines, fmt.Sprintf("- [%d] %s", i+1, ev.Title))
				if len(meta) > 0 {
					lines = append(lines, "  "+strings.Join(meta, " · "))
				}
			}
			return strings.Join(lines, "\n")
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			lines := []string{}
			for i, row := range rows {
				if i >= 8 {
					break
				}
				lines = append(lines, fmt.Sprintf("- [%d] %v: 方向 %s · 阶段 %s · 依据 %s", i+1, row["关键词"], trendDirection(row), trendStage(row), trendBasis(row)))
			}
			return strings.Join(lines, "\n")
		}
	}
	return preview(result)
}

func trendDirection(row map[string]any) string {
	if value := stringField(row, "增长方向"); value != "" {
		return value
	}
	if value := stringField(row, "趋势判定"); value != "" {
		return value
	}
	return "待判断"
}

func trendStage(row map[string]any) string {
	if value := stringField(row, "生命周期阶段"); value != "" {
		return value
	}
	return "未分层"
}

func trendBasis(row map[string]any) string {
	stats, _ := row["统计依据"].(map[string]any)
	parts := []string{}
	if value := fieldText(stats, "近期活跃度分"); value != "" {
		parts = append(parts, "近年活跃 "+value)
	} else if value := fieldText(row, "动量分"); value != "" {
		parts = append(parts, "近年活跃 "+value)
	}
	if value := fieldText(stats, "短期加速分"); value != "" {
		parts = append(parts, "短期加速 "+value)
	} else if value := fieldText(row, "爆发分"); value != "" {
		parts = append(parts, "短期加速 "+value)
	}
	if value := fieldText(stats, "稳健年增长斜率"); value != "" {
		parts = append(parts, "年增长 "+value)
	}
	if len(parts) == 0 {
		return "样本年度分布"
	}
	return strings.Join(parts, " · ")
}

func stringField(row map[string]any, key string) string {
	value, ok := row[key]
	if !ok || value == nil {
		return ""
	}
	text := strings.TrimSpace(fmt.Sprintf("%v", value))
	if text == "" || text == "<nil>" {
		return ""
	}
	return text
}

func fieldText(row map[string]any, key string) string {
	if row == nil {
		return ""
	}
	return stringField(row, key)
}

func exportMarkdown(events []transcriptEvent, generatedAt time.Time) string {
	lines := []string{
		"# SciScope 会话导出",
		"",
		"导出时间: " + generatedAt.Format("2006-01-02 15:04:05 MST"),
		"",
	}
	for _, ev := range events {
		content := strings.TrimSpace(ev.Content)
		if content == "" {
			continue
		}
		switch ev.Kind {
		case "user":
			lines = append(lines, "## 用户问题", "", content, "")
		case "plan":
			lines = append(lines, "## 执行计划", "", content, "")
		case "tool_call":
			lines = append(lines, "## 工具调用: "+ev.Tool, "", content, "")
		case "tool_result":
			lines = append(lines, "## 证据结果: "+ev.Tool, "", content, "")
		case "timeline":
			lines = append(lines, "## 工具调用时间线", "", content, "")
		case "permission":
			lines = append(lines, "## 权限提示: "+ev.Tool, "", content, "")
		case "reflect":
			lines = append(lines, "## 自我纠错", "", content, "")
		case "assistant":
			lines = append(lines, "## 智能体回答", "", content, "")
		case "error":
			lines = append(lines, "## 错误与恢复建议", "", content, "")
		default:
			lines = append(lines, "## "+ev.Kind, "", content, "")
		}
	}
	return strings.TrimSpace(strings.Join(lines, "\n")) + "\n"
}

func exportLastSession(dir string) (string, string, error) {
	sessions, err := listSessionFiles(dir, 1)
	if err != nil {
		return "", "", err
	}
	if len(sessions) == 0 {
		return "", "", fmt.Errorf("no saved sessions in %s", dir)
	}
	b, err := os.ReadFile(sessions[0].Path)
	if err != nil {
		return "", "", err
	}
	return string(b), sessions[0].Path, nil
}

func sessionDir() string {
	// Session persistence layout:
	// 1) explicit override via SCISCOPE_SESSION_DIR
	// 2) fallback to ~/.sciscope/sessions
	// 3) final fallback to ./sessions
	if v := os.Getenv("SCISCOPE_SESSION_DIR"); v != "" {
		return v
	}
	if home, err := os.UserHomeDir(); err == nil {
		return filepath.Join(home, ".sciscope", "sessions")
	}
	return "sessions"
}

func listSessionFiles(dir string, limit int) ([]sessionFile, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	sessions := []sessionFile{}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".md" {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		lastQuestion := ""
		if b, err := os.ReadFile(path); err == nil {
			lastQuestion = extractLastQuestion(string(b))
		}
		sessions = append(sessions, sessionFile{
			Path:         path,
			Name:         entry.Name(),
			LastQuestion: lastQuestion,
			ModTime:      info.ModTime(),
			Size:         info.Size(),
		})
	}
	sort.Slice(sessions, func(i, j int) bool {
		return sessions[i].ModTime.After(sessions[j].ModTime)
	})
	if limit > 0 && len(sessions) > limit {
		sessions = sessions[:limit]
	}
	for i := range sessions {
		sessions[i].Index = i + 1
	}
	return sessions, nil
}

func extractLastQuestion(markdown string) string {
	lines := strings.Split(markdown, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) != "## 用户问题" {
			continue
		}
		chunk := []string{}
		for j := i + 1; j < len(lines); j++ {
			line := strings.TrimSpace(lines[j])
			if strings.HasPrefix(line, "## ") {
				break
			}
			if line != "" {
				chunk = append(chunk, line)
			}
		}
		return strings.TrimSpace(strings.Join(chunk, "\n"))
	}
	return ""
}

func loadSessionMarkdown(path string) (loadedSession, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return loadedSession{}, err
	}
	content := string(b)
	return loadedSession{
		Path:         path,
		Content:      content,
		LastQuestion: extractLastQuestion(content),
	}, nil
}

func renderSessionsList(sessions []sessionFile) string {
	if len(sessions) == 0 {
		return stWarn.Render("  没有找到已保存会话。完成一次回答后会自动保存。")
	}
	lines := []string{stBullet.Render("⏺ ") + stAccent.Render("最近会话")}
	for _, s := range sessions {
		sizeKB := float64(s.Size) / 1024
		meta := fmt.Sprintf("/resume %d · %s · %.1f KB", s.Index, s.ModTime.Format("01-02 15:04"), sizeKB)
		lines = append(lines,
			stConn.Render("  ⎿  ")+stInk.Render(s.Name),
			stFaint.Render("      "+meta),
		)
	}
	return strings.Join(lines, "\n")
}

func writeSessionMarkdown(dir string, events []transcriptEvent, now time.Time) (string, error) {
	// Persisted sessions are append-only; if a timestamped filename exists,
	// a numeric suffix is appended to avoid overwrite.
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	base := "sciscope-session-" + now.Format("20060102-150405")
	path := filepath.Join(dir, base+".md")
	for i := 2; ; i++ {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			break
		}
		path = filepath.Join(dir, fmt.Sprintf("%s-%02d.md", base, i))
	}
	if err := os.WriteFile(path, []byte(exportMarkdown(events, now)), 0o644); err != nil {
		return "", err
	}
	return path, nil
}

func recoveryActionForBackend(baseURL, errText string) recoveryHint {
	if backendMode(baseURL) == "local" {
		return recoveryHint{
			Title:     "后端未连接",
			Command:   "make backend",
			Message:   "建议: 先运行 make backend, 然后输入 /retry 重试上一问。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: true,
		}
	}
	return recoveryHint{
		Title:     "托管服务暂不可用",
		Command:   "/demo",
		Message:   "托管后端暂时不可达。可先输入 /demo 查看完整演示流, 或稍后 /retry。",
		Severity:  "blocked",
		Inspect:   "/doctor",
		Retryable: true,
	}
}

func recoveryAction(s string) recoveryHint {
	low := strings.ToLower(s)
	switch {
	case strings.Contains(low, "connection refused") || strings.Contains(low, "无法连接后端"):
		return recoveryActionForBackend(backendURL(), s)
	case strings.Contains(low, "forbidden") || strings.Contains(low, "permission denied") || strings.Contains(low, " 403 "):
		return recoveryHint{
			Title:     "权限限制",
			Message:   "本次操作被服务端权限规则拒绝。请改用允许的只读方式（如 /demo），或联系管理员开通权限后重试。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: false,
		}
	case strings.Contains(low, "llm") && (strings.Contains(low, "timeout") || strings.Contains(low, "timed out")):
		return recoveryHint{
			Title:     "LLM 超时",
			Command:   "make llm",
			Message:   "LLM 响应超时。建议: 检查 make llm 是否已启动且未过载, 稍后输入 /retry。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "timed out") || strings.Contains(low, "timeout") || strings.Contains(low, "gateway"):
		return recoveryHint{
			Title:     "请求超时",
			Message:   "后端响应超时。建议: 稍等片刻后输入 /retry; 若反复超时, 用 /doctor 检查后端与 LLM 状态。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "llm") || strings.Contains(low, "vllm") || strings.Contains(low, "8001"):
		return recoveryHint{
			Title:     "LLM 服务不可用",
			Command:   "make llm",
			Message:   "建议: 检查 make llm 或 make dev-vllm 是否已启动，然后输入 /retry。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "graphs not built"):
		return recoveryHint{
			Title:     "图谱未构建",
			Command:   "make graph-export",
			Message:   "建议: 运行 make graph-export 后输入 /retry。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "database") || strings.Contains(low, "postgres") || strings.Contains(low, "pgvector"):
		return recoveryHint{
			Title:     "数据库不可用",
			Command:   "make postgres-refresh",
			Message:   "建议: 检查 PostgreSQL, 必要时运行 make postgres-refresh, 然后输入 /retry。",
			Severity:  "blocked",
			Inspect:   "/doctor",
			Retryable: true,
		}
	case strings.Contains(low, "paper_embeddings") || strings.Contains(low, "does not exist") ||
		strings.Contains(low, "undefinedtable") || strings.Contains(low, "embedding"):
		return recoveryHint{
			Title:     "数据/向量资产不可用",
			Command:   "make embeddings",
			Message:   "推荐/向量检索所需资产未就绪。建议: 按 /doctor 提示补齐资产（make embeddings）后重试；资产缺失期间该能力如实降级，不伪造结果。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	default:
		return recoveryHint{
			Title:     "请求失败",
			Message:   "建议: 查看错误详情；如果环境已恢复，可输入 /retry 重试上一问。",
			Severity:  "recoverable",
			Inspect:   "/doctor",
			Retryable: true,
		}
	}
}

func friendlyError(s string) string {
	action := recoveryAction(s)
	lines := []string{s, "  " + action.Message}
	if action.Command != "" {
		lines = append(lines, "  恢复动作: "+action.Command)
	}
	return strings.Join(lines, "\n")
}

func renderRecoveryPanel(s string) string {
	action := recoveryAction(s)
	meta := action.Severity
	if meta == "" {
		meta = "recoverable"
	}
	body := []string{
		"error   " + preview(s),
		"reason  " + action.Message,
	}
	if action.Command != "" {
		body = append(body, "primary "+action.Command)
	}
	if action.Retryable {
		body = append(body, "next    /retry")
	}
	if action.Inspect != "" {
		body = append(body, "inspect "+action.Inspect)
	}
	return panelRow("recovery", action.Title, meta, body)
}

func (m *model) startQuestion(v string, retry bool) tea.Cmd {
	hist := append([]turn(nil), m.history...)
	m.ti.SetValue("")
	m.appendUserMessage(v, retry)
	m.record("user", "", v)
	m.history = append(m.history, turn{"user", v})
	m.lastQuestion = v
	m.answering = true
	m.answer = ""
	m.used = nil
	m.toolStart = map[string]time.Time{}
	m.timeline = nil
	m.lastMeta = eventMeta{}
	m.lastStreamKind = ""
	m.nodeSeen = nil
	m.livePlan = nil
	m.liveReflect = ""
	m.verb = verbs[rand.Intn(len(verbs))]
	m.start = time.Now()
	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel
	q := v
	return tea.Batch(
		func() tea.Msg { go stream(ctx, backendURL(), q, hist, m.sessionID, retry, m.sub); return nil },
		listen(m.sub),
		m.spin.Tick,
	)
}
