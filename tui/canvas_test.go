package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// TestViewCoversFullTerminalWithBlackCanvas 回归测试：View() 输出必须恰好
// 覆盖终端全部行，且每行都有 Canvas 黑色背景（防止布局漂移导致底部裸露
// 终端默认背景，如 IDE 灰色）。
func TestViewCoversFullTerminalWithBlackCanvas(t *testing.T) {
	// 先捕获当前 profile 再切 TrueColor（restoreDarkTheme 会改全局 profile）。
	prev := lipgloss.ColorProfile()
	restoreDarkTheme(t)
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	for _, size := range []struct{ w, h int }{{80, 24}, {120, 40}, {160, 50}} {
		m := initialModel()
		next, _ := m.Update(tea.WindowSizeMsg{Width: size.w, Height: size.h})
		got := next.(model)
		view := got.View()
		lines := strings.Split(view, "\n")
		if len(lines) < size.h {
			t.Fatalf("%dx%d: view only covers %d lines, bottom would expose terminal background", size.w, size.h, len(lines))
		}
		for i, ln := range lines {
			if i >= size.h {
				break
			}
			if !strings.Contains(ln, "48;2;0;0;0m") {
				t.Fatalf("%dx%d: line %d lacks black canvas background: %q", size.w, size.h, i, ln[:minInt(len(ln), 40)])
			}
		}
	}
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
