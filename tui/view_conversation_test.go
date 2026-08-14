package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// TestRenderAnswerMessageHasNo256ColorSeq 乱码根治回归：
// Glamour 的 256 色 ANSI（[38;5;252m 等）必须以纯文本块结构呈现——
// 输出中不得含任何 256 色序列参数；颜色只允许 RGB（38;2;r;g;b）。
func TestRenderAnswerMessageHasNo256ColorSeq(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	answers := []string{
		"hello",
		"**粗体** 与 *斜体* 与 `code` 混合。",
		"### 小节标题\n- 列表项一\n- 列表项二\n\n普通段落。",
		"证据核查：该论断得到 3 条文献支持（强支持 0.81）。",
	}
	for _, a := range answers {
		out := renderAnswerMessage(a, nil, 100)
		if strings.Contains(out, "38;5;") {
			t.Errorf("answer=%q 仍含 256 色序列: %q", a, out[:minW(len(out), 80)])
		}
		// 剥离后内容完整（块结构保留、无裸 [..m 参数文本）。
		plain := stripANSI(out)
		if strings.Contains(plain, "[38;5;") || strings.Contains(plain, "[0m") {
			t.Errorf("answer=%q 含字面残骸文本: %q", a, plain[:minW(len(plain), 80)])
		}
		// 高亮样式（RGB）仍生效：含 38;2; 是预期（theme token）。
		if !strings.Contains(out, "38;2;") {
			t.Errorf("answer=%q 应有 RGB 高亮样式", a)
		}
	}
}

func minW(a, b int) int {
	if a < b {
		return a
	}
	return b
}
