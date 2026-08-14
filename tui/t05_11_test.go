package main

import (
	"strings"
	"sync/atomic"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// buildDemoModel 构造跑完完整 demo 事件流的 model（给定终端尺寸）。
func buildDemoModel(t *testing.T, w, h int) model {
	t.Helper()
	m := initialModel()
	m.demo = true
	next, _ := m.Update(tea.WindowSizeMsg{Width: w, Height: h})
	m = next.(model)
	for _, msg := range demoScriptMessages() {
		next, _ = m.Update(msg)
		m = next.(model)
	}
	next, _ = m.Update(doneMsg{})
	return next.(model)
}

// T05-11 宽度矩阵：56/60/80/120/160 列下 View() 输出无 panic、
// 每行显示宽 ≤ 终端宽、关键内容（研究结论）可见。
func TestWidthMatrixRenderIntegrity(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	for _, w := range []int{56, 60, 80, 120, 160} {
		t.Run(string(rune('0'+w%10))+string(rune('0'+w/10%10))+string(rune('0'+w/100)), func(t *testing.T) {
			m := buildDemoModel(t, w, 40)
			out := m.View()
			lines := strings.Split(out, "\n")
			if len(lines) == 0 {
				t.Fatal("View 输出为空")
			}
			for i, l := range lines {
				if lw := lipgloss.Width(l); lw > w {
					t.Errorf("宽度 %d：行 %d 显示宽 %d 超限", w, i, lw)
				}
			}
			if !strings.Contains(stripANSI(out), "研究结论") {
				t.Errorf("宽度 %d：缺少研究结论", w)
			}
		})
	}
}

// T05-11 resize 矩阵：120→80→160 无 panic、block 身份（ID）不丢失。
func TestResizeMatrixKeepsBlockIdentity(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	m := buildDemoModel(t, 120, 40)
	idsBefore := map[string]int{}
	for _, b := range m.blockItems {
		idsBefore[b.ID]++
	}

	next, _ := m.Update(tea.WindowSizeMsg{Width: 80, Height: 40})
	m = next.(model)
	next, _ = m.Update(tea.WindowSizeMsg{Width: 160, Height: 40})
	m = next.(model)

	for _, b := range m.blockItems {
		if _, ok := idsBefore[b.ID]; !ok {
			t.Fatalf("resize 后 block ID %s 丢失", b.ID)
		}
	}
	// 渲染仍完整
	out := m.View()
	if !strings.Contains(stripANSI(out), "研究结论") {
		t.Error("resize 后缺少研究结论")
	}
}

// T05-11 cache hit：相同宽度的第二次渲染不重跑 Glamour。
func TestCachedFinalizedBlockSkipsGlamour(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	m := buildDemoModel(t, 80, 40)
	atomic.StoreInt64(&glamourRenderCount, 0)
	m.renderBlocksContent(76)
	first := atomic.LoadInt64(&glamourRenderCount)
	m.renderBlocksContent(76) // 相同宽度：全部 cache hit
	second := atomic.LoadInt64(&glamourRenderCount)
	if second != first {
		t.Errorf("相同宽度重渲应全部命中缓存：Glamour %d → %d", first, second)
	}
	// 宽度变化才重渲
	m.renderBlocksContent(120)
	third := atomic.LoadInt64(&glamourRenderCount)
	if third <= second {
		t.Error("宽度变化应触发重渲（Glamour 计数上升）")
	}
}

// T05-11 性能预算：500 finalized blocks + 1 running block 渲染。
func BenchmarkRender500Blocks(b *testing.B) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	m := initialModel()
	next, _ := m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	m = next.(model)
	for i := 0; i < 500; i++ {
		m.appendBlock(BlockSystem, "第 "+string(rune('a'+i%26))+" 条记录内容：检索文献并给出可验证证据。")
	}
	m.appendAnswerMessage("结论：该论断获得强支持。", []string{"verify_claim"})
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		m.renderBlocksContent(116)
	}
}

// T05-11 性能预算：modal filter 100 items。
func BenchmarkFilterCmds100(b *testing.B) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = filterCmds("/res")
	}
}

// T05-11 Terminal matrix：Ascii profile（TERM=dumb / 无 truecolor）下
// View() 必须 fail gracefully——不得输出任何 ESC 控制序列。
func TestAsciiProfileViewHasNoControlSequences(t *testing.T) {
	prev := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(prev)
	applyTheme("dark")

	m := buildDemoModel(t, 80, 40)
	out := m.View()
	if strings.ContainsRune(out, '\x1b') {
		t.Fatalf("Ascii profile 下 View 输出含 ESC 控制序列（fail gracefully 门禁）")
	}
	if !strings.Contains(out, "研究结论") {
		t.Error("Ascii profile 下应保留纯文本内容")
	}
}
