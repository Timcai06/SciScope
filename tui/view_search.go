// view_search.go — T05-12 交互：transcript 搜索（ctrl+f）与 block 选择（ctrl+g）。
//
// 提示词交互优化：Transcript 支持滚动、block 选择、展开折叠；搜索是
// Block 级能力（配合折叠/选择/主题切换）。本文件负责：
//   - 搜索模式状态机（query 输入、匹配定位、Enter 跳转、Esc 退出）
//   - block 选择模式（↑/↓ 块间移动、Enter 折叠切换、Esc 退出）
//   - 搜索框与选中 marker 渲染（不破坏 canvas 黑底纪律）
package main

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// startSearch 进入搜索模式（ctrl+f）。
func (m *model) startSearch() {
	m.searchMode = true
	m.searchQuery = ""
	m.searchMatch = 0
	m.searchMatches = nil
}

// stopSearch 退出搜索模式并清理状态。
func (m *model) stopSearch() {
	m.searchMode = false
	m.searchQuery = ""
	m.searchMatch = 0
	m.searchMatches = nil
}

// updateSearchKey 处理搜索模式下的按键输入：字符/退格更新 query，
// 其余键（enter/esc 等）由 updateKey 顶层处理。
func (m model) updateSearchKey(msg tea.Msg) (model, tea.Cmd) {
	km, ok := msg.(tea.KeyMsg)
	if !ok {
		return m, nil
	}
	if km.Type == tea.KeyRunes {
		m.searchQuery += string(km.Runes)
		m.searchMatch = 0
		return m, nil
	}
	if km.String() == "backspace" {
		if r := []rune(m.searchQuery); len(r) > 0 {
			m.searchQuery = string(r[:len(r)-1])
		}
		m.searchMatch = 0
		return m, nil
	}
	return m, nil
}

// computeSearchMatches 在 viewport 内容行中定位包含 query 的行（ANSI 安全）。
func (m *model) computeSearchMatches() {
	m.searchMatches = nil
	q := strings.TrimSpace(m.searchQuery)
	if q == "" {
		return
	}
	lines := strings.Split(m.viewportContent, "\n")
	for i, ln := range lines {
		if strings.Contains(stripANSI(ln), q) {
			m.searchMatches = append(m.searchMatches, i)
		}
	}
}

// stepSearch 跳到第 delta 个（下一个/上一个）匹配行并滚动定位。
func (m *model) stepSearch(delta int) {
	m.computeSearchMatches()
	n := len(m.searchMatches)
	if n == 0 {
		return
	}
	m.searchMatch = (m.searchMatch + delta + n) % n
	m.vp.SetYOffset(m.searchMatches[m.searchMatch])
}

// markSearchMatches 给当前匹配行加 Accent marker（▍），供 View() 使用。
func (m *model) markSearchMatches(content string) string {
	m.computeSearchMatches()
	q := strings.TrimSpace(m.searchQuery)
	if q == "" || len(m.searchMatches) == 0 {
		return content
	}
	lines := strings.Split(content, "\n")
	li := m.searchMatches[m.searchMatch%len(m.searchMatches)]
	if li >= 0 && li < len(lines) {
		lines[li] = stAccent.Render("▍ ") + lines[li]
	}
	return strings.Join(lines, "\n")
}

// startSelect 进入 block 选择模式（ctrl+g），定位到最近一个块。
func (m *model) startSelect() {
	m.selectMode = true
	if m.selectIdx < 0 || m.selectIdx >= len(m.blockItems) {
		m.selectIdx = len(m.blockItems) - 1
	}
	if m.selectIdx >= 0 && m.selectIdx < len(m.blockStartLines) {
		m.vp.SetYOffset(m.blockStartLines[m.selectIdx])
	}
}

// stopSelect 退出 block 选择模式。
func (m *model) stopSelect() {
	m.selectMode = false
}

// moveSelect 在块间移动并保持视口锚定到块首行。
func (m *model) moveSelect(delta int) {
	if len(m.blockItems) == 0 {
		return
	}
	m.selectIdx += delta
	if m.selectIdx < 0 {
		m.selectIdx = 0
	}
	if m.selectIdx >= len(m.blockItems) {
		m.selectIdx = len(m.blockItems) - 1
	}
	if m.selectIdx < len(m.blockStartLines) {
		m.vp.SetYOffset(m.blockStartLines[m.selectIdx])
	}
}

// markSelectedBlock 给选中块首行加 marker（❯），供 View() 使用。
func (m *model) markSelectedBlock(content string) string {
	if m.selectIdx < 0 || m.selectIdx >= len(m.blockStartLines) {
		return content
	}
	lines := strings.Split(content, "\n")
	li := m.blockStartLines[m.selectIdx]
	if li >= 0 && li < len(lines) {
		lines[li] = stAccent.Render("❯ ") + lines[li]
	}
	return strings.Join(lines, "\n")
}

// renderSearchBox 搜索模式下的底部输入框（替代 composer）。
func (m model) renderSearchBox(width int) string {
	if width < 24 {
		width = 24
	}
	q := m.searchQuery
	if q == "" {
		q = "输入关键词搜索当前对话"
	}
	cnt := ""
	if len(m.searchMatches) > 0 {
		cnt = stFaint.Render(fmt.Sprintf(" · %d/%d", (m.searchMatch%len(m.searchMatches))+1, len(m.searchMatches)))
	} else if m.searchQuery != "" {
		cnt = stFaint.Render(" · 无匹配")
	}
	line := stAccent.Render("⌕ ") + stInk.Render(q) + cnt + stAccent.Render("▌")
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(activeTheme().Accent).
		Padding(0, 1).
		Width(width - 4).
		Render(line)
}
