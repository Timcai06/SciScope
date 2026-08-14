// view_trace.go — T05-10 文件职责收敛：科研轨迹/工作流渲染（单一视觉职责）。
//
// 从 main.go / render.go 搬移（行为零变化，纯文件拆分）：
//   - workflow 状态：renderWorkflowStatus / streamKindLabel / kaomojiForState
//   - 轨迹块：renderTimelineBlock / renderPlanBlock / renderToolCallBlock / renderReflectBlock
//   - 工具结果标签：toolResultLabel / permissionNotice / durationText
//   - 内部线语法：panelRow
package main

import (
	"encoding/json"
	"fmt"
	"github.com/charmbracelet/lipgloss"
	"strings"
	"time"
)

func metaDetail(meta eventMeta) string {
	parts := []string{}
	if meta.Phase != "" {
		parts = append(parts, "阶段 "+meta.Phase)
	} else if meta.Node != "" {
		parts = append(parts, "阶段 "+nodeLabel(meta.Node))
	}
	if meta.ElapsedMS > 0 {
		parts = append(parts, fmt.Sprintf("%dms", meta.ElapsedMS))
	}
	if meta.Retry {
		parts = append(parts, "重试")
	}
	return strings.Join(parts, " · ")
}

func metaEmpty(meta eventMeta) bool {
	return meta.Runtime == "" &&
		meta.Node == "" &&
		meta.Phase == "" &&
		meta.SessionID == "" &&
		meta.ElapsedMS == 0 &&
		!meta.Retry &&
		len(meta.StructuredAnswer) == 0
}

func nodeLabel(node string) string {
	switch node {
	case "prepare":
		return "理解问题"
	case "plan":
		return "制定研究计划"
	case "llm_step":
		return "推理与检索决策"
	case "execute_tools":
		return "证据检索"
	case "reflect":
		return "自检修正"
	case "force_synthesis":
		return "综合回答"
	default:
		if node == "" {
			return "等待事件"
		}
		return node
	}
}

func eventPhase(ev timelineEvent) string {
	if strings.TrimSpace(ev.Phase) != "" {
		return strings.TrimSpace(ev.Phase)
	}
	switch ev.Kind {
	case "plan":
		return "制定研究计划"
	case "tool_call", "tool_result", "permission":
		return "证据检索"
	case "reflect":
		return "自检修正"
	case "final":
		return "综合回答"
	case "error":
		return "错误恢复"
	default:
		return "执行过程"
	}
}

func metaPhase(meta eventMeta) string {
	if strings.TrimSpace(meta.Phase) != "" {
		return strings.TrimSpace(meta.Phase)
	}
	return nodeLabel(meta.Node)
}

func streamKindLabel(kind string) string {
	switch kind {
	case "plan":
		return "plan"
	case "text":
		return "text"
	case "tool_call":
		return "tool call"
	case "tool_result":
		return "tool result"
	case "reflect":
		return "reflect"
	case "final":
		return "final"
	case "error":
		return "error"
	default:
		return "stream"
	}
}

func kaomojiForState(kind string, meta eventMeta, answering bool) string {
	if !answering {
		return "(´▽`)"
	}
	if kind == "error" {
		return "(；￣Д￣)"
	}
	if meta.Retry {
		return "(ง •̀_•́)ง"
	}
	switch kind {
	case "tool_call", "tool_result":
		switch meta.Node {
		case "execute_tools":
			return "(つ•̀ω•́)つ"
		default:
			return "(｀・ω・´)"
		}
	case "reflect":
		return "( ･᷄ὢ･᷅ )"
	case "final":
		return "(๑•̀ㅂ•́)و✧"
	case "plan":
		return "(。-`ω´-)"
	case "text":
		return "( ..)φ"
	default:
		return "(。-`ω´-)"
	}
}

func renderWorkflowStatus(meta eventMeta, nodes []string, kind string, elapsed time.Duration, width int) string {
	if width < 20 {
		width = 20
	}
	current := metaPhase(meta)
	if current == "等待事件" && len(nodes) > 0 {
		current = nodeLabel(nodes[len(nodes)-1])
	}
	phases := []string{"理解问题", "制定研究计划", "推理与检索决策", "证据检索", "自检修正", "综合回答"}
	active := -1
	for i, phase := range phases {
		if phase == current {
			active = i
			break
		}
	}
	steps := []string{}
	for i, phase := range phases {
		mark := "○"
		style := stFaint
		if active >= 0 && i < active {
			mark = "●"
		}
		if i == active {
			mark = "◆"
			style = stAccent
		}
		steps = append(steps, style.Render(mark+" "+phase))
	}
	phaseLines := []string{strings.Join(steps, stFaint.Render("  →  "))}
	if width < 96 {
		phaseLines = []string{
			strings.Join(steps[:3], stFaint.Render("  →  ")),
			strings.Join(steps[3:], stFaint.Render("  →  ")),
		}
	}
	session := meta.SessionID
	if session == "" {
		session = "local session"
	}
	status := []string{
		stAccent.Render(kaomojiForState(kind, meta, true)),
		stAccent.Render("当前阶段"),
		stInk.Render(current),
		stFaint.Render(streamKindLabel(kind)),
		stFaint.Render(fmt.Sprintf("%.0fs", elapsed.Seconds())),
	}
	if meta.Retry {
		status = append(status, stWarn.Render("重试"))
	}
	if meta.ElapsedMS > 0 {
		status = append(status, stFaint.Render(fmt.Sprintf("%dms", meta.ElapsedMS)))
	}
	body := []string{
		strings.Join(status, stFaint.Render(" · ")),
	}
	body = append(body, phaseLines...)
	body = append(body, stFaint.Render("线程 "+clip(session, 42)))
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(body, "\n"))
}

func appendUniqueNode(nodes []string, node string) []string {
	node = strings.TrimSpace(node)
	if node == "" {
		return nodes
	}
	for _, seen := range nodes {
		if seen == node {
			return nodes
		}
	}
	return append(nodes, node)
}

func renderStreamRail(events []timelineEvent, meta eventMeta, nodes []string, kind string, elapsed time.Duration, width int) string {
	if width < 20 {
		width = 20
	}
	runtime := meta.Runtime
	if runtime == "" {
		runtime = "langgraph"
	}
	node := meta.Phase
	if node == "" {
		node = nodeLabel(meta.Node)
	}
	if meta.Node == "" && meta.Phase == "" && len(nodes) > 0 {
		node = nodeLabel(nodes[len(nodes)-1])
	}
	session := meta.SessionID
	if session == "" {
		session = "local session"
	}
	status := []string{
		stAccent.Render(runtime),
		stFaint.Render("阶段 ") + stInk.Render(node),
		stFaint.Render(streamKindLabel(kind)),
		stFaint.Render(fmt.Sprintf("%.0fs", elapsed.Seconds())),
	}
	if meta.Retry {
		status = append(status, stWarn.Render("重试"))
	}
	if meta.ElapsedMS > 0 {
		status = append(status, stFaint.Render(fmt.Sprintf("%dms", meta.ElapsedMS)))
	}

	body := []string{
		strings.Join(status, stFaint.Render(" · ")),
		stFaint.Render("线程 " + clip(session, 38)),
	}
	if len(nodes) > 0 {
		labels := []string{}
		start := len(nodes) - 5
		if start < 0 {
			start = 0
		}
		for _, node := range nodes[start:] {
			labels = append(labels, nodeLabel(node))
		}
		body = append(body, stFaint.Render("图谱  ")+stInk.Render(strings.Join(labels, stFaint.Render(" → "))))
	}
	if len(events) > 0 {
		body = append(body, stFaint.Render("最新"))
		start := len(events) - 4
		if start < 0 {
			start = 0
		}
		for _, ev := range events[start:] {
			label := ev.Label
			if label == "" {
				label = toolPlainLabel(ev.Tool)
			}
			line := "  " + label
			if ev.Detail != "" {
				line += " · " + clip(ev.Detail, 54)
			}
			if d := durationText(ev.Duration); d != "" {
				line += " · " + d
			}
			body = append(body, line)
		}
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(body, "\n"))
}

func renderThinkingShelf(plan []string, reflect string, width int) string {
	if len(plan) == 0 && strings.TrimSpace(reflect) == "" {
		return ""
	}
	if width < 20 {
		width = 20
	}
	body := []string{}
	if len(plan) > 0 {
		body = append(body, stFaint.Render("研究计划"))
		for i, step := range plan {
			if i >= 4 {
				break
			}
			body = append(body, fmt.Sprintf("  [%d] %s", i+1, clip(step, 86)))
		}
	}
	if strings.TrimSpace(reflect) != "" {
		if len(body) > 0 {
			body = append(body, "")
		}
		body = append(body, stFaint.Render("自检修正"))
		body = append(body, "  "+clip(reflect, 110))
	}
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder(), true, false, true, false).
		BorderForeground(cFaint).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(body, "\n"))
}

func panelRow(kind, title, meta string, body []string) string {
	// panelRow is the internal line grammar for dashboard/splash/tool blocks:
	//   header: "╭─ <kind> · <title> [· <meta>]"
	//   body: each logical row prefixed with "│  "
	//   footer: "╰─"
	head := "╭─ " + kind + " · " + title
	if strings.TrimSpace(meta) != "" {
		head += " · " + meta
	}
	lines := []string{stConn.Render(head)}
	for _, line := range body {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		lines = append(lines, stFaint.Render("│  ")+line)
	}
	lines = append(lines, stConn.Render("╰─"))
	return strings.Join(lines, "\n")
}

// ---- 以下从 render.go 搬移 ----
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

// toolResultSummary 提取工具结果的一行纯文本摘要，用于 tool 块成功/失败行
// （提示词：Tool 展示为「找到 15 篇论文 · 完成 2.4s」式摘要，而非日志堆叠）。
func toolResultSummary(name, result string) string {
	if strings.HasPrefix(result, "[未执行]") {
		return strings.TrimSpace(strings.TrimPrefix(result, "[未执行]"))
	}
	switch name {
	case "search_literature", "summarize_field":
		var papers []evidencePaper
		if json.Unmarshal([]byte(result), &papers) == nil && len(papers) > 0 {
			return fmt.Sprintf("找到 %d 篇论文", len(papers))
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
					reason = "证据不足"
				}
				return "证据不足: " + clip(reason, 40)
			}
			label := cr.Verdict
			if cr.TopSimilarity > 0 {
				label += fmt.Sprintf(" · %.3f", cr.TopSimilarity)
			}
			return label
		}
	case "get_trends":
		var rows []map[string]any
		if json.Unmarshal([]byte(result), &rows) == nil && len(rows) > 0 {
			return fmt.Sprintf("%d 条趋势", len(rows))
		}
	}
	s := strings.TrimSpace(stripANSI(result))
	if s == "" {
		return ""
	}
	return clip(s, 48)
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
