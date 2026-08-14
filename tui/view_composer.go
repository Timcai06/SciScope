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
	//
	// Grok build 风格：快捷键/状态提示嵌入输入框边框内部底部一行
	// （prompt_widget 的 bottom shortcuts strip），不再单独占一行。
	//
	// 行宽补齐手动完成（padLine），不依赖 lipgloss 的 Width 属性：lipgloss
	// 的 reflow 对含 ANSI 的行会把转义序列计入宽度导致拆行（本项目已知问题，
	// 与 wrapWithFrame 的手动拼行同一纪律）。
	innerW := width - 4
	// textarea.View() 每行以换行符结尾（含末尾），TrimRight 避免拼出多余空行。
	inputLine := strings.TrimRight(m.ti.View(), "\n")
	hintLine := m.renderComposerHint(innerW)
	content := ""
	for i, ln := range strings.Split(inputLine+"\n"+hintLine, "\n") {
		if i > 0 {
			content += "\n"
		}
		content += padLine(ln, innerW)
	}
	borderColor := activeTheme().Border
	if m.ti.Focused() {
		borderColor = activeTheme().Accent
	}
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(borderColor).
		Padding(0, 1).
		Render(content)
}

// padLine 把行补齐到 w 列（ANSI 安全：空格只加在行尾纯文本区域）。
func padLine(line string, w int) string {
	if d := w - lipgloss.Width(line); d > 0 {
		line += strings.Repeat(" ", d)
	}
	return line
}

// renderComposerHint 输入框边框内底部提示行（grok prompt_widget shortcuts strip）：
//   - answering：左 = spinner + 动作 + 计时，右 = Esc 取消（提示词状态栏单行合并）；
//   - 空闲：右 = Enter 发送 · Ctrl+J 换行 · / 命令。
func (m model) renderComposerHint(width int) string {
	var left, right string
	if m.answering {
		elapsed := ""
		if !m.start.IsZero() {
			elapsed = fmt.Sprintf(" · %ds", int(time.Since(m.start).Seconds()))
		}
		left = m.spin.View() + " " + stAccent.Render(m.verb+"…") + stFaint.Render(elapsed)
		right = stFaint.Render("Esc 取消")
	} else {
		right = stFaint.Render("Enter 发送 · Ctrl+J 换行 · / 命令")
	}
	if left == "" {
		return right
	}
	gap := width - lipgloss.Width(stripANSI(left)) - lipgloss.Width(right)
	if gap < 1 {
		return left
	}
	return left + strings.Repeat(" ", gap) + right
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
