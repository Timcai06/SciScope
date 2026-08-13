// style_primitives.go — T05-01 呈现 primitive。
//
// 定义 spacing / indent / separator / selected row / overlay border 五类基础
// primitive，以及 DomainCard（强领域对象）与 InlineBlock（普通无框块）两种
// 明确视觉等级（计划 5.3 节 Border Budget）：
//
//   - DomainCard：Evidence / Claim / Dispute / Recovery 等「需要独立审阅的领域
//     对象或交互表面」，允许完整边框；
//   - InlineBlock：user / plan / tool / answer 等普通事件，默认无框。
//
// 边框代表领域对象或交互表面，不是默认排版工具。

package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

const (
	// IndentStep 层级缩进（计划 5.4 心智模型的 plan/tool 缩进基准）。
	IndentStep = 2
	// CardPadX DomainCard 内容水平内边距。
	CardPadX = 2
	// OverlayMargin overlay 与屏幕边缘的间距。
	OverlayMargin = 2
)

// separator 返回一条 faint 色的水平分隔线（width 列）。
func separator(width int) string {
	if width < 1 {
		width = 1
	}
	return stFaint.Render(strings.Repeat("─", width))
}

// selectedRow 统一选中态：AccentSoft 背景 + Ink 加粗，不使用刺眼全反色
// （计划 5.4 / T05-08 规则）。
func selectedRow(line string) string {
	return lipgloss.NewStyle().
		Background(activeTheme().AccentSoft).
		Foreground(cInk).
		Bold(true).
		Render(line)
}

// overlayBorderStyle 统一 overlay / modal 边框：Accent 色边框 + Surface 表面。
// modal 与 picker 共享同一 grammar（T05-08 规则）。
func overlayBorderStyle() lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(cAccent).
		Background(activeTheme().Surface).
		Padding(1, CardPadX)
}

// domainCard 强领域对象卡（Evidence / Claim / Dispute / Recovery）。
//
//	╭─ <kind> · <title> ──────╮
//	│  <body...>              │
//	╰─────────────────────────╯
func domainCard(kind, title string, body []string) string {
	head := "╭─ " + kind + " · " + title
	lines := []string{stBorder(head)}
	for _, line := range body {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		lines = append(lines, stBorder("│")+strings.Repeat(" ", CardPadX-1)+line)
	}
	lines = append(lines, stBorder("╰─"))
	return strings.Join(lines, "\n")
}

// inlineBlock 普通无框块：每行 IndentStep 缩进，不产生任何边框
// （user / plan / tool / answer 的默认呈现，计划 5.3 节）。
func inlineBlock(body []string) string {
	pad := strings.Repeat(" ", IndentStep)
	lines := make([]string, 0, len(body))
	for _, line := range body {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		lines = append(lines, pad+line)
	}
	return strings.Join(lines, "\n")
}

// stBorder 结构边框样式（Border token）。
func stBorder(s string) string {
	return lipgloss.NewStyle().Foreground(activeTheme().Border).Render(s)
}
