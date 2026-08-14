package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// TestFullDemoScriptViewHasNoLiteralSGRResidue 乱码根治回归：
// 完整 demo 事件流（含 doneMsg 转正）后的 View 输出不得含任何
// 无 ESC 前缀的 SGR 残骸（[0m / [38;5;252m / [1;38;2;…m 字面形态）。
func TestFullDemoScriptViewHasNoLiteralSGRResidue(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	m := initialModel()
	m.demo = true
	next, _ := m.Update(tea.WindowSizeMsg{Width: 80, Height: 40})
	m = next.(model)
	for _, msg := range demoScriptMessages() {
		next, _ = m.Update(msg)
		m = next.(model)
	}
	next, _ = m.Update(doneMsg{})
	m = next.(model)

	out := m.View()
	bad := 0
	for _, l := range strings.Split(out, "\n") {
		runes := []rune(l)
		for j := 0; j < len(runes); j++ {
			if runes[j] == '[' && (j == 0 || runes[j-1] != '\x1b') {
				if j+1 < len(runes) && runes[j+1] >= '0' && runes[j+1] <= '9' {
					k := j + 1
					for k < len(runes) && ((runes[k] >= '0' && runes[k] <= '9') || runes[k] == ';') {
						k++
					}
					if k < len(runes) && runes[k] == 'm' && k > j+1 {
						bad++
					}
				}
			}
		}
	}
	if bad > 0 {
		t.Fatalf("View 输出含 %d 处字面 SGR 残骸（乱码根因回归）", bad)
	}
}

// TestAnswerBlockRawStaysPlainText Raw 语义回归：doneMsg 转正后
// BlockAnswer.Raw 必须是纯文本（不得混入渲染 ANSI）。
func TestAnswerBlockRawStaysPlainText(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	m := initialModel()
	m.demo = true
	next, _ := m.Update(tea.WindowSizeMsg{Width: 80, Height: 40})
	m = next.(model)
	for _, msg := range demoScriptMessages() {
		next, _ = m.Update(msg)
		m = next.(model)
	}
	next, _ = m.Update(doneMsg{})
	m = next.(model)

	for i := range m.blockItems {
		b := &m.blockItems[i]
		if b.Kind != BlockAnswer {
			continue
		}
		if strings.Contains(b.Raw, "\x1b[") {
			t.Fatalf("BlockAnswer.Raw 混入 ANSI（应保持纯文本）: %q", b.Raw[:minH(len(b.Raw), 60)])
		}
		if strings.TrimSpace(b.Raw) == "" {
			t.Fatal("BlockAnswer.Raw 为空")
		}
	}
}

func minH(a, b int) int {
	if a < b {
		return a
	}
	return b
}
