package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func fillBlocks(t *testing.T, m model) model {
	t.Helper()
	for i := 0; i < 60; i++ {
		m.appendBlock(BlockSystem, "第 "+string(rune('a'+i%26))+" 行内容 "+strings.Repeat("x", 30))
	}
	m.refresh()
	return m
}

func TestUpDownDelegatesToViewportWhenNoMenu(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	m = fillBlocks(t, m)
	m.vp.GotoBottom()
	before := m.vp.YOffset
	// 输入框有内容时 up 也应该滚动 viewport（单行输入框 up 无意义）
	m.ti.SetValue("一些问题")
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	m = next.(model)
	if m.vp.YOffset >= before {
		t.Errorf("up 未滚动 viewport：YOffset before=%d after=%d", before, m.vp.YOffset)
	}
	// down 向底部滚动
	afterUp := m.vp.YOffset
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = next.(model)
	if m.vp.YOffset <= afterUp {
		t.Errorf("down 未滚动 viewport：before=%d after=%d", afterUp, m.vp.YOffset)
	}
}

func TestManualScrollStopsFollowAndBottomRestores(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	m = fillBlocks(t, m)
	m.vp.GotoBottom()
	if !m.vp.AtBottom() {
		t.Fatal("初始应贴底")
	}
	// 手动滚到顶
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyHome})
	m = next.(model)
	if m.vp.AtBottom() {
		t.Fatal("滚到顶后不应贴底")
	}
	// refresh（新内容到达）不跟底：保持顶部位置
	m.appendBlock(BlockSystem, "新内容")
	m.refresh()
	if m.vp.YOffset != 0 {
		t.Errorf("手动滚动后 refresh 应保持顶部位置，YOffset=%d", m.vp.YOffset)
	}
	// 滚回底 → refresh 恢复跟随
	m.vp.GotoBottom()
	m.appendBlock(BlockSystem, "再一条")
	m.refresh()
	if !m.vp.AtBottom() {
		t.Error("滚回底部后 refresh 应恢复跟随贴底")
	}
}

func TestResizeKeepsBottomAnchorAndPreservesTopOffset(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	m = fillBlocks(t, m)
	m.vp.GotoBottom()
	// 贴底时 resize：保持贴底
	next, _ = m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	m = next.(model)
	if !m.vp.AtBottom() {
		t.Error("贴底时 resize 应保持贴底")
	}
	// 滚到顶部后 resize：保持顶部（YOffset 不跳）
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyHome})
	m = next.(model)
	next, _ = m.Update(tea.WindowSizeMsg{Width: 90, Height: 25})
	m = next.(model)
	if m.vp.YOffset != 0 {
		t.Errorf("顶部锚定 resize 应保持 YOffset=0，实际=%d", m.vp.YOffset)
	}
}

func TestFollowFocusKeepsComposerTyping(t *testing.T) {
	// 输入框 focus 恒在：滚动键不污染输入框值
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")
	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	m = next.(model)
	m = fillBlocks(t, m)
	m.ti.SetValue("正在输入")
	next, _ = m.Update(tea.KeyMsg{Type: tea.KeyPgDown})
	m = next.(model)
	if got := m.ti.Value(); got != "正在输入" {
		t.Errorf("滚动不应修改输入框值，got=%q", got)
	}
}
