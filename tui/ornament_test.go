package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func TestOrnamentStripShape(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	lines := ornamentLines()
	if len(lines) != ornamentRows {
		t.Fatalf("ornamentLines 行数 = %d, want %d", len(lines), ornamentRows)
	}
	for i, l := range lines {
		plain := stripANSI(l)
		if w := lipgloss.Width(plain); w != ornamentWidth {
			t.Errorf("行 %d 宽 = %d, want %d", i, w, ornamentWidth)
		}
		for _, r := range plain {
			if r < sextantBlockBase || r > sextantBlockBase+63 {
				t.Errorf("行 %d 含非 sextant 字符 U+%04X", i, r)
			}
		}
	}
	// 行 0 与行 2 相位相反（编织交错）。
	if stripANSI(lines[0]) == stripANSI(lines[2]) {
		t.Error("行 0/2 应相位相反")
	}
}

func TestMirrorOrnamentLine(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	src := ornamentLines()[0]
	mir := mirrorOrnamentLine(src)
	// 镜像后核心字符顺序反转；宽度不变；仍有样式包裹。
	if got, want := lipgloss.Width(stripANSI(mir)), lipgloss.Width(stripANSI(src)); got != want {
		t.Errorf("镜像宽 = %d, want %d", got, want)
	}
	if stripANSI(mir) == stripANSI(src) {
		t.Error("镜像应与原串不同（顺序反转）")
	}
	if !strings.Contains(mir, "\x1b[") {
		t.Error("镜像行丢失样式序列")
	}
}

func TestWelcomeBrandBlockOrnament(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	// 默认（无 SCISCOPE_TUI_ORNAMENT）：纹样关闭——sextant 在多数终端字体
	// 不支持会乱码（项目负责人真机反馈），welcomeBrandBlock 与纯 Logo 一致。
	t.Setenv("SCISCOPE_TUI_ORNAMENT", "")
	block := welcomeBrandBlock(116)
	if len(block) != 6 {
		t.Fatalf("行数 = %d, want 6", len(block))
	}
	pureLogo := strings.Split(welcomeBrand(116), "\n")
	for i := range block {
		if stripANSI(block[i]) != stripANSI(pureLogo[i]) {
			t.Errorf("默认模式行 %d 应与纯 Logo 一致: %q vs %q", i, stripANSI(block[i]), stripANSI(pureLogo[i]))
		}
	}

	// 显式启用 sextant：空间足够（116 列）时两侧纹样出现，总宽 ≤ 116。
	t.Setenv("SCISCOPE_TUI_ORNAMENT", "sextant")
	block = welcomeBrandBlock(116)
	if len(block) != 6 {
		t.Fatalf("行数 = %d, want 6", len(block))
	}
	for i, l := range block {
		if w := lipgloss.Width(l); w > 116 {
			t.Errorf("行 %d 宽 %d 超限", i, w)
		}
	}
	// 第 0 行与第 5 行两侧应为空白（顶点行留白）→ 纯文本与纯 Logo 一致。
	for _, i := range []int{0, 5} {
		plain := stripANSI(block[i])
		want := stripANSI(pureLogo[i])
		if strings.TrimSpace(plain) != strings.TrimSpace(want) {
			t.Errorf("顶点行 %d 应与纯 Logo 一致: %q vs %q", i, plain, want)
		}
	}
	// 中间行（1-4）应含 sextant 纹样字符。
	mid := stripANSI(block[2])
	hasSextant := false
	for _, r := range mid {
		if r >= sextantBlockBase && r <= sextantBlockBase+63 {
			hasSextant = true
		}
	}
	if !hasSextant {
		t.Error("sextant 模式下中间行应含 sextant 纹样")
	}

	// 空间不足（88 列）：退回纯 Logo（87 列）。
	block = welcomeBrandBlock(88)
	for i, l := range block {
		if w := lipgloss.Width(l); w > 88 {
			t.Errorf("窄宽下不应溢出：行 %d 宽 %d", i, w)
		}
	}
}

func TestOrnamentModeFallback(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	old := ornamentMode()
	t.Setenv("SCISCOPE_TUI_ORNAMENT", "block")
	if ornamentMode() != "block" {
		t.Fatal("block 模式未生效")
	}
	lines := ornamentLinesForMode()
	if len(lines) != ornamentRows {
		t.Fatalf("block 行数 = %d", len(lines))
	}
	for _, l := range lines {
		plain := stripANSI(l)
		if !strings.ContainsAny(plain, "▀▄") {
			t.Errorf("block 模式应含半块字符: %q", plain)
		}
	}
	t.Setenv("SCISCOPE_TUI_ORNAMENT", "off")
	if ornamentLinesForMode() != nil {
		t.Error("off 模式应返回 nil")
	}
	t.Setenv("SCISCOPE_TUI_ORNAMENT", old)
}
