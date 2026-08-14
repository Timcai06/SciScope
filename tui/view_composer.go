// view_composer.go — T05-10 文件职责收敛：底部输入框与状态行（单一视觉职责）。
//
// 从 main.go / commands_run.go 搬移（行为零变化，纯文件拆分）：
//   - renderComposer：主题化匣式边框输入框（聚焦 Accent / 未聚焦 Border）
//   - renderStatusLine：低视觉权重 status + shortcut strip
package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

func (m model) renderComposer(width int) string {
	if width < 48 {
		width = 48
	}
	// T05-07 修订：composer 保留主题化输入框（Grok prompt_widget 的
	// show_borders 语义）——边框随 focus 状态：聚焦用 Accent、未聚焦用 Border。
	// 实测 lipgloss 带边框时 Width(W) 总宽 = W+2，故传 width-2。
	inputLine := m.ti.View()
	borderColor := activeTheme().Border
	if m.ti.Focused() {
		borderColor = activeTheme().Accent
	}
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(borderColor).
		Padding(0, 1).
		Width(width - 2).
		Render(inputLine)
}

func (m model) renderStatusLine(width int) string {
	left := stFaint.Render("backend " + backendMode(backendURL()))
	if m.answering {
		left = m.spin.View() + " " + stAccent.Render(m.verb+"…") + stFaint.Render(" · esc 中断")
	} else if m.demo {
		left = stFaint.Render("演示模式 · esc 中断")
	}
	right := stFaint.Render("Enter 发送 · Esc 中断/关闭 · / 命令")
	gap := width - lipgloss.Width(stripANSI(left)) - lipgloss.Width(right)
	if gap < 1 {
		return left
	}
	return left + strings.Repeat(" ", gap) + right
}
