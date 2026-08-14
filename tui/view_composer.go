// view_composer.go — T05-10 文件职责收敛：底部输入框与状态行（单一视觉职责）。
//
// 从 main.go / commands_run.go 搬移（行为零变化，纯文件拆分）：
//   - renderComposer：主题化匣式边框输入框（聚焦 Accent / 未聚焦 Border）
//   - renderStatusLine：低视觉权重 status + shortcut strip
package main

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
)

// layoutTier 三档响应式布局（提示词：Compact 40-60 列 / Normal 80 列 / Wide
// 120 列）。档位用于组件在窄屏隐藏次要信息、宽屏增加来源与 metadata；
// 禁止组件自行硬编码最小宽度（如 width=48）假装终端更宽。
type layoutTier int

const (
	tierCompact layoutTier = iota // < 64 列：隐藏次要信息
	tierNormal                    // 64-110 列：完整体验
	tierWide                      // > 110 列：增加来源和 metadata
)

func layoutTierFor(width int) layoutTier {
	switch {
	case width < 64:
		return tierCompact
	case width <= 110:
		return tierNormal
	default:
		return tierWide
	}
}

func (m model) renderComposer(width int) string {
	// 最小宽度防御只防零值/极端窄屏，不假装终端更宽（提示词禁止 width=48
	// 一类硬编码）：< 24 列时以实际宽度渲染（无边框）。
	if width < 24 {
		width = 24
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
		Width(width - 4).
		Render(inputLine)
}

// pushHistory 记录已发送输入到历史（去重、最新在前、上限 50），重置浏览位置。
func (m *model) pushHistory(v string) {
	v = strings.TrimSpace(v)
	if v == "" {
		return
	}
	if len(m.inputHistory) > 0 && m.inputHistory[0] == v {
		m.historyIdx = -1
		return
	}
	m.inputHistory = append([]string{v}, m.inputHistory...)
	if len(m.inputHistory) > 50 {
		m.inputHistory = m.inputHistory[:50]
	}
	m.historyIdx = -1
}

// browseHistory ↑/↓ 浏览输入历史：up 向更旧、down 向更新；down 到底恢复
// 进入浏览前的草稿。
func (m *model) browseHistory(up bool) {
	if len(m.inputHistory) == 0 {
		return
	}
	if m.historyIdx < 0 {
		m.draftBeforeHistory = m.ti.Value()
		m.historyIdx = 0
	} else if up {
		if m.historyIdx < len(m.inputHistory)-1 {
			m.historyIdx++
		}
	} else {
		m.historyIdx--
	}
	if m.historyIdx < 0 {
		m.historyIdx = -1
		m.ti.SetValue(m.draftBeforeHistory)
	} else {
		m.ti.SetValue(m.inputHistory[m.historyIdx])
	}
	m.ti.SetCursor(len(m.ti.Value()))
}

func (m model) renderStatusLine(width int) string {
	// 提示词：状态栏最多一行——✻ 正在核查证据 · 8s · Esc取消。
	// 不堆叠 spinner/workflow/timer/live preview：running 时合并为
	// spinner + 动作 + 计时 + 取消提示；空闲时只留 backend 模式 + 快捷键。
	var left, right string
	if m.answering {
		elapsed := ""
		if !m.start.IsZero() {
			elapsed = fmt.Sprintf(" · %ds", int(time.Since(m.start).Seconds()))
		}
		left = m.spin.View() + " " + stAccent.Render(m.verb+"…") + stFaint.Render(elapsed)
		right = stFaint.Render("Esc 取消")
	} else {
		left = stFaint.Render("backend " + backendMode(backendURL()))
		if m.demo {
			left = stFaint.Render("演示模式 · esc 中断")
		}
		right = stFaint.Render("Enter 发送 · Ctrl+J 换行 · Esc 中断/关闭 · / 命令")
	}
	gap := width - lipgloss.Width(stripANSI(left)) - lipgloss.Width(right)
	if gap < 1 {
		return left
	}
	return left + strings.Repeat(" ", gap) + right
}
