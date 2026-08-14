// theme.go — T05-01 design tokens 与主题系统。
//
// 目标：先冻结「黑、灰、青、黄、红」视觉法则，再改组件；新组件不得直接引用
// 散落 hex，必须通过本文件的 token 与语义样式函数。
//
// 视觉金标准只以 dark 为准（见 T05 计划 5.1 节 token 表）；paper/light/contrast
// 继续兼容，行为等价、不要求像素同构。

package main

import (
	"os"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// ---- theme definitions (research-console palettes, à la Claude Code structure) ----

type tuiTheme struct {
	Name  string
	Title string
	Desc  string

	// T05-01 design tokens（dark 为计划 5.1 节规定值）
	Canvas       lipgloss.Color // 画布背景
	Surface      lipgloss.Color // 面板/卡片表面
	SurfaceHover lipgloss.Color // 悬停表面
	Border       lipgloss.Color // 结构边框
	AccentSoft   lipgloss.Color // 弱强调（选中行背景等）

	Accent   lipgloss.Color
	Success  lipgloss.Color // 成功状态（tool 完成等，低饱和）
	Evidence lipgloss.Color // 证据领域对象强调
	Warning  lipgloss.Color
	Error    lipgloss.Color
	Ink      lipgloss.Color
	Muted    lipgloss.Color
	Faint    lipgloss.Color
	Selected lipgloss.Color

	// 旧角色色：T05-04 起逐步淡出（颜色表达状态，不是装饰角色）；
	// paper/light/contrast 保持现状，行为不变。
	Tool lipgloss.Color
	User lipgloss.Color
	Warn lipgloss.Color
}

var (
	themes = map[string]tuiTheme{
		"dark": {
			Name: "dark", Title: "深色研究台", Desc: "默认黑色沉浸画布,青色证据流,适合深色终端和演示录屏",
			Canvas: "#000000", Surface: "#080A0A", SurfaceHover: "#111414",
			Border: "#292D2D", AccentSoft: "#214646",
			Accent: "#5FD7D7", Success: "#7FB8A6", Evidence: "#6FB8B8",
			Warning: "#D7AF5F", Error: "#FF7777",
			Ink: "#E7E7E7", Muted: "#8A8F8F", Faint: "#505555", Selected: "#1c1c1c",
			// 普通 Tool/User 不再拥有高饱和角色色：并入灰阶（计划 5.1 色彩纪律）
			Tool: "#8A8F8F", User: "#E7E7E7", Warn: "#D7AF5F",
		},
		"paper": {
			Name: "paper", Title: "报告纸面", Desc: "贴近 PDF 报告的青绿品牌色,适合答辩截图",
			Canvas: "#FFFFFF", Surface: "#F7FBFA", SurfaceHover: "#EDF3F2",
			Border: "#B8C6C4", AccentSoft: "#D3E6E3",
			Accent: "#16847D", Success: "#3E7D5C", Evidence: "#16847D",
			Warning: "#B8872B", Error: "#B55A5A",
			Ink: "#1C2326", Muted: "#667276", Faint: "#9AA8A6", Selected: "#F7FBFA",
			Tool: "#4E6F40", User: "#0B4F4A", Warn: "#B8872B",
		},
		"light": {
			Name: "light", Title: "浅色终端", Desc: "提高浅色背景可读性,减少低对比灰字",
			Canvas: "#FFFFFF", Surface: "#F4F7F7", SurfaceHover: "#E9EFEF",
			Border: "#C9D2D1", AccentSoft: "#CFE4E2",
			Accent: "#006D77", Success: "#2F7D4F", Evidence: "#006D77",
			Warning: "#8A5A00", Error: "#A23B3B",
			Ink: "#1B1F22", Muted: "#5D666A", Faint: "#8A9498", Selected: "#F4F7F7",
			Tool: "#255C99", User: "#2F6F3E", Warn: "#8A5A00",
		},
		"contrast": {
			Name: "contrast", Title: "高对比", Desc: "更亮的强调色和警告色,适合投影或低质量屏幕",
			Canvas: "#000000", Surface: "#101010", SurfaceHover: "#1F1F1F",
			Border: "#666666", AccentSoft: "#005F5F",
			Accent: "#00FFFF", Success: "#00E5A0", Evidence: "#00FFFF",
			Warning: "#FFD166", Error: "#FF5C8A",
			Ink: "#FFFFFF", Muted: "#B8B8B8", Faint: "#777777", Selected: "#000000",
			Tool: "#5FA8FF", User: "#7CFF6B", Warn: "#FFD166",
		},
	}
	themeOrder   = []string{"dark", "paper", "light", "contrast"}
	currentTheme = "dark"

	cAccent   lipgloss.Color
	cSuccess  lipgloss.Color
	cEvidence lipgloss.Color
	cTool     lipgloss.Color
	cWarn     lipgloss.Color
	cUser     lipgloss.Color
	cError    lipgloss.Color
	cMuted    lipgloss.Color
	cFaint    lipgloss.Color
	cInk      lipgloss.Color

	stAccent   lipgloss.Style
	stBullet   lipgloss.Style
	stConn     lipgloss.Style
	stTool     lipgloss.Style
	stSuccess  lipgloss.Style
	stEvidence lipgloss.Style
	stWarn     lipgloss.Style
	stError    lipgloss.Style
	stUser     lipgloss.Style
	stMuted    lipgloss.Style
	stFaint    lipgloss.Style
	stInk      lipgloss.Style
	stSelCmd   lipgloss.Style
	stCmd      lipgloss.Style
)

func init() {
	if name := strings.TrimSpace(os.Getenv("SCISCOPE_TUI_THEME")); name != "" {
		applyTheme(name)
		return
	}
	applyTheme(currentTheme)
}

func applyTheme(name string) bool {
	name = strings.ToLower(strings.TrimSpace(name))
	theme, ok := themes[name]
	if !ok {
		return false
	}
	currentTheme = name
	cAccent = theme.Accent
	cSuccess = theme.Success
	cEvidence = theme.Evidence
	cTool = theme.Tool
	cWarn = theme.Warn
	cUser = theme.User
	cError = theme.Error
	cMuted = theme.Muted
	cFaint = theme.Faint
	cInk = theme.Ink
	stAccent = lipgloss.NewStyle().Foreground(cAccent).Bold(true)
	stBullet = lipgloss.NewStyle().Foreground(cAccent).Bold(true) // ⏺
	stConn = lipgloss.NewStyle().Foreground(cFaint)               // ⎿
	stTool = lipgloss.NewStyle().Foreground(cTool)
	stSuccess = lipgloss.NewStyle().Foreground(cSuccess)
	stEvidence = lipgloss.NewStyle().Foreground(cEvidence)
	stWarn = lipgloss.NewStyle().Foreground(cWarn)
	stError = lipgloss.NewStyle().Foreground(cError)
	stUser = lipgloss.NewStyle().Foreground(cUser).Bold(true)
	stMuted = lipgloss.NewStyle().Foreground(cMuted)
	stFaint = lipgloss.NewStyle().Foreground(cFaint)
	stInk = lipgloss.NewStyle().Foreground(cInk)
	stSelCmd = lipgloss.NewStyle().Background(cAccent).Foreground(theme.Selected).Bold(true)
	stCmd = lipgloss.NewStyle().Foreground(cMuted)
	return true
}

// ---- 语义样式函数（T05-01）----
//
// 新组件一律通过这些函数取样式，禁止再按「角色」散发明颜色。
// 颜色必须表达状态，而不是装饰角色（计划 5.1 节）。

// PrimaryText 主文本：Ink，普通权重。
func PrimaryText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cInk) }

// MutedText 次级文本：Muted。
func MutedText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cMuted) }

// FaintText 弱文本：Faint（元信息、审计链等）。
func FaintText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cFaint) }

// AccentText 强调文本：Accent（focus / active / selected / trusted evidence emphasis）。
func AccentText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cAccent).Bold(true) }

// SuccessText 成功状态文本：Success（tool 完成等，低饱和）。
func SuccessText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cSuccess) }

// EvidenceText 证据对象强调文本：Evidence。
func EvidenceText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cEvidence) }

// WarningText 警告文本：Warning（evidence insufficient / uncertainty / degraded）。
func WarningText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cWarn) }

// ErrorText 错误文本：Error（真实执行失败）。
func ErrorText() lipgloss.Style { return lipgloss.NewStyle().Foreground(cError) }

// activeTheme 返回当前主题的 token（供 primitive 与测试使用）。
func activeTheme() tuiTheme { return themes[currentTheme] }
