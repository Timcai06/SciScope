package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// restoreDarkTheme 把全局主题状态恢复到 dark，避免测试间串扰；并固定 TrueColor
// profile，使颜色断言在非 TTY 的 go test 环境同样成立。
func restoreDarkTheme(t *testing.T) {
	t.Helper()
	lipgloss.SetColorProfile(termenv.TrueColor)
	applyTheme("dark")
	useIcons = iconMode()
}

func TestDarkThemeMatchesPlanTokens(t *testing.T) {
	restoreDarkTheme(t)
	d := themes["dark"]
	want := map[string]lipgloss.Color{
		"Canvas":       "#000000",
		"Surface":      "#080A0A",
		"SurfaceHover": "#111414",
		"Ink":          "#E7E7E7",
		"Muted":        "#8A8F8F",
		"Faint":        "#505555",
		"Border":       "#292D2D",
		"Accent":       "#5FD7D7",
		"AccentSoft":   "#214646",
		"Warning":      "#D7AF5F",
		"Error":        "#FF7777",
	}
	got := map[string]lipgloss.Color{
		"Canvas": d.Canvas, "Surface": d.Surface, "SurfaceHover": d.SurfaceHover,
		"Ink": d.Ink, "Muted": d.Muted, "Faint": d.Faint, "Border": d.Border,
		"Accent": d.Accent, "AccentSoft": d.AccentSoft, "Warning": d.Warning,
		"Error": d.Error,
	}
	for k, w := range want {
		if got[k] != w {
			t.Errorf("dark token %s = %q, want %q (T05 计划 5.1)", k, got[k], w)
		}
	}
}

func TestDarkRoleColorsAreDesaturated(t *testing.T) {
	restoreDarkTheme(t)
	d := themes["dark"]
	// 计划 5.1 色彩纪律：普通 Tool/User 不再拥有高饱和角色色。
	if d.Tool != d.Muted {
		t.Errorf("dark Tool = %q, want Muted %q（工具块并入灰阶）", d.Tool, d.Muted)
	}
	if d.User != d.Ink {
		t.Errorf("dark User = %q, want Ink %q（用户块并入主文本）", d.User, d.Ink)
	}
}

func TestAllThemesPresentAndSwitchable(t *testing.T) {
	restoreDarkTheme(t)
	for _, name := range themeOrder {
		if !applyTheme(name) {
			t.Errorf("theme %q should apply", name)
		}
	}
	if applyTheme("not-a-theme") {
		t.Error("unknown theme should be rejected")
	}
	if currentTheme != "contrast" {
		t.Errorf("after loop currentTheme = %q, want contrast", currentTheme)
	}
	restoreDarkTheme(t)
}

func TestSemanticStyleFunctions(t *testing.T) {
	restoreDarkTheme(t)
	checks := map[string]lipgloss.Color{
		"PrimaryText": "#E7E7E7", "MutedText": "#8A8F8F", "FaintText": "#505555",
		"AccentText": "#5FD7D7", "WarningText": "#D7AF5F", "ErrorText": "#FF7777",
	}
	styles := map[string]lipgloss.Style{
		"PrimaryText": PrimaryText(), "MutedText": MutedText(), "FaintText": FaintText(),
		"AccentText": AccentText(), "WarningText": WarningText(), "ErrorText": ErrorText(),
	}
	for name, want := range checks {
		if got := styles[name].GetForeground(); got != want {
			t.Errorf("%s color = %v, want %v", name, got, want)
		}
	}
}

func TestIconModeUnicodeIsDefault(t *testing.T) {
	restoreDarkTheme(t)
	t.Setenv("SCISCOPE_TUI_ICONS", "")
	useIcons = iconMode()
	if useIcons != "unicode" {
		t.Fatalf("default icon mode = %q, want unicode", useIcons)
	}
	// Unicode 模式不得输出 PUA（U+E000–U+F8FF）图形。
	for name := range toolLabels {
		ic := toolIcon(name)
		if ic == "" {
			t.Errorf("unicode mode: tool %q icon empty", name)
		}
		for _, r := range ic {
			if r >= 0xE000 && r <= 0xF8FF {
				t.Errorf("unicode mode: tool %q icon %q contains PUA rune", name, ic)
			}
		}
	}
}

func TestIconModeNerdIsOptIn(t *testing.T) {
	restoreDarkTheme(t)
	t.Setenv("SCISCOPE_TUI_ICONS", "nerd")
	useIcons = iconMode()
	if useIcons != "nerd" {
		t.Fatalf("nerd mode = %q", useIcons)
	}
	ic := toolIcon("verify_claim")
	if ic != "\uf058" {
		t.Errorf("nerd verify_claim icon = %q, want U+F058", ic)
	}
	restoreDarkTheme(t)
}

func TestIconModeOffDropsIcons(t *testing.T) {
	restoreDarkTheme(t)
	t.Setenv("SCISCOPE_TUI_ICONS", "off")
	useIcons = iconMode()
	if got := toolLabel("verify_claim"); got != "论断核查" {
		t.Errorf("off mode toolLabel = %q, want plain label", got)
	}
	restoreDarkTheme(t)
}

func TestDomainCardHasBorderAndInlineBlockDoesNot(t *testing.T) {
	restoreDarkTheme(t)
	card := domainCard("evidence", "证据卡", []string{"line one", "line two"})
	for _, want := range []string{"╭─", "╰─", "│"} {
		if !strings.Contains(card, want) {
			t.Errorf("DomainCard missing %q:\n%s", want, card)
		}
	}
	block := inlineBlock([]string{"user question", "another line"})
	if strings.ContainsAny(block, "╭╰│┌└─") {
		t.Errorf("InlineBlock must be borderless, got:\n%s", block)
	}
	lines := strings.Split(block, "\n")
	for _, ln := range lines {
		if !strings.HasPrefix(ln, strings.Repeat(" ", IndentStep)) {
			t.Errorf("InlineBlock line %q missing indent", ln)
		}
	}
}

func TestSeparatorAndSelectedRow(t *testing.T) {
	restoreDarkTheme(t)
	s := separator(10)
	// 渲染输出含 ANSI 转义，按可见字符统计宽度。
	if got := strings.Count(s, "─"); got != 10 {
		t.Errorf("separator(10) visible width = %d, want 10: %q", got, s)
	}
	row := selectedRow("选中项")
	if !strings.Contains(row, "选中项") {
		t.Errorf("selectedRow lost content: %q", row)
	}
	// selectedRow 使用 AccentSoft 背景，不是全反色。lipgloss 对暗色 hex 的渲染
	// 存在 -1 偏移（上游行为，T05-01 已记录），因此用同一颜色的 probe 输出对比。
	probe := lipgloss.NewStyle().Background(activeTheme().AccentSoft).Render("p")
	start := strings.Index(probe, "48;2;")
	end := strings.Index(probe[start:], "m") + start + 1
	bgSeq := probe[start:end]
	if !strings.Contains(row, bgSeq) {
		t.Errorf("selectedRow background = %q, want AccentSoft sequence %q", row, bgSeq)
	}
}

func TestOverlayBorderStyleUsesSurfaceAndAccent(t *testing.T) {
	restoreDarkTheme(t)
	st := overlayBorderStyle()
	if !st.GetBorderTop() {
		t.Error("overlayBorderStyle missing top border")
	}
	if got := st.GetBackground(); got != themes["dark"].Surface {
		t.Errorf("overlay background = %v, want Surface %v", got, themes["dark"].Surface)
	}
}
