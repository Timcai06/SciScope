// model.go — T05-10 文件职责收敛：顶层 model 定义与组装（composition root 配套）。
//
// 从 main.go 搬移（行为零变化，纯文件拆分）。
package main

import (
	"context"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type model struct {
	ti                          textarea.Model // T05-12：textarea 支持换行输入（Shift+Enter）
	vp                          viewport.Model
	spin                        spinner.Model
	blocks                      []string // finalized conversation lines
	blockItems                  []ScrollbackBlock
	blocksVersion               int
	transcriptCache             string
	transcriptCacheWidth        int
	transcriptCacheBlockVersion int
	transcriptCacheVersion      int
	viewportContent             string
	viewportContentVersion      int
	answer                      string // current streaming answer
	answering                   bool
	answerRunningID             string // T05-04: streaming 期间的 running answer 块 ID
	anchorNextTurn              bool   // T05-04: 发送后锚定 prompt（feature gate）
	verb                        string
	tick                        int
	start                       time.Time // when the current turn began (for the elapsed timer)
	used                        []string  // tools called this turn (for the answer footer)
	toolStart                   map[string]time.Time
	history                     []turn
	transcript                  []transcriptEvent
	timeline                    []timelineEvent
	recentSessions              []sessionFile
	lastExport                  string
	lastQuestion                string
	sessionID                   string
	lastMeta                    eventMeta
	lastStreamKind              string
	lastTurnErr                 string // error text of the current turn; persisted on failure
	nodeSeen                    []string
	livePlan                    []string
	liveReflect                 string
	lastRefresh                 time.Time
	refreshPending              bool
	sub                         chan tea.Msg
	cancel                      context.CancelFunc
	menuIdx                     int
	submenu                     string
	submenuIdx                  int
	// T05-12 交互：transcript 搜索（ctrl+f）与 block 选择（ctrl+g）。
	searchMode      bool
	searchQuery     string
	searchMatch     int
	searchMatches   []int
	selectMode      bool
	selectIdx       int
	blockStartLines []int // renderBlocksContent 输出的每块起始行号
	// T05-12 Composer：输入历史（↑/↓ 浏览）。
	inputHistory       []string
	historyIdx         int
	draftBeforeHistory string
	ready              bool
	demo               bool
}

type conversationBlock = ScrollbackBlock

func initialModel() model {
	ti := textarea.New()
	ti.Placeholder = "输入研究问题 / 待核查论断,或输入 / 调用命令"
	ti.Prompt = stAccent.Render("❯ ")
	ti.ShowLineNumbers = false
	ti.CharLimit = 4000
	// Enter 由 updateKey 拦截发送（提示词 Composer：Enter 发送、Shift+Enter 换行）；
	// 移除 textarea 自身的 InsertNewline，避免 Enter 双触发插入换行。
	ti.KeyMap.InsertNewline.SetEnabled(false)
	ti.SetHeight(2) // 视觉紧凑：边框 + 2 行内容，多行内部滚动
	// 关键：清掉 textarea 默认样式的 ANSI 16 色背景（CursorLine 默认
	// Background(AdaptiveColor{Dark:"0"}) 会输出 \x1b[40m 黑底、反显 \x1b[7m、
	// EOB \x1b[30m 黑前景——这些非 RGB 序列会被终端主题映射为深灰/其他色，
	// 盖掉画布纯黑，导致输入框把黑背景"搞坏"）。全部改为透明样式：
	// 行首黑底由 paintCanvasLines 的 RGB 黑统一保证，光标反显保留（1 字符宽）。
	ti.FocusedStyle = textarea.Style{
		Base:        lipgloss.NewStyle(),
		CursorLine:  lipgloss.NewStyle(), // 无背景，避免 \x1b[40m
		EndOfBuffer: stFaint,             // 行尾填充用 Faint 灰前景
		Placeholder: stMuted,
		Prompt:      lipgloss.NewStyle(), // Prompt 色由 ti.Prompt 内的 ANSI 控制
		Text:        lipgloss.NewStyle(),
	}
	ti.BlurredStyle = ti.FocusedStyle
	ti.Focus()

	sp := spinner.New()
	sp.Spinner = spinner.Spinner{
		Frames: []string{"✻", "✢", "✳", "∗", "✦", "✶"},
		FPS:    spinnerFrameInterval,
	}
	sp.Style = stAccent
	m := model{ti: ti, spin: sp, sub: make(chan tea.Msg, 64), demo: demoMode(), sessionID: newSessionID(), selectIdx: -1}
	m.syncThemeStyles()
	// 首帧在 WindowSizeMsg 之前渲染：vp 必须预置合理尺寸，否则零值 viewport
	// 会让首帧输出垃圾行数（多层嵌套后尤其明显），污染渲染器行 diff。
	m.vp = newTranscriptViewport(76, 20)
	return m
}

func newTranscriptViewport(width, height int) viewport.Model {
	vp := viewport.New(width, height)
	// macOS trackpads emit many small wheel events; a larger delta keeps the
	// transcript responsive while streamed ANSI content is being redrawn.
	vp.MouseWheelDelta = 8
	return vp
}

func isVerticalWheel(msg tea.MouseMsg) bool {
	if msg.Action != tea.MouseActionPress {
		return false
	}
	return msg.Button == tea.MouseButtonWheelUp || msg.Button == tea.MouseButtonWheelDown
}

func newSessionID() string {
	return "tui-" + time.Now().UTC().Format("20060102T150405.000000000")
}

// inputCursorColumn 返回输入框当前光标列（textarea 无 Position()，用 LineInfo 计算；
// 单行场景 ColumnOffset 即总列位置）。
func (m model) inputCursorColumn() int {
	return m.ti.LineInfo().ColumnOffset
}

func (m *model) syncThemeStyles() {
	m.ti.Prompt = stAccent.Render("❯ ")
	m.spin.Style = stAccent
	// 主题切换后刷新 textarea 语义样式（Style 是值类型，applyTheme 重建的
	// stMuted/stFaint 不会自动同步到已赋值的样式）。
	m.ti.FocusedStyle.Placeholder = stMuted
	m.ti.FocusedStyle.EndOfBuffer = stFaint
	m.ti.BlurredStyle = m.ti.FocusedStyle
}

func (m *model) loadRecentSessions() {
	sessions, err := listSessionFiles(sessionDir(), 3)
	if err == nil {
		m.recentSessions = sessions
	}
}
