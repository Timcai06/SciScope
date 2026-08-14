// model.go — T05-10 文件职责收敛：顶层 model 定义与组装（composition root 配套）。
//
// 从 main.go 搬移（行为零变化，纯文件拆分）。
package main

import (
	"context"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

type model struct {
	ti                          textinput.Model
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
	ready                       bool
	demo                        bool
}

type conversationBlock = ScrollbackBlock

func initialModel() model {
	ti := textinput.New()
	ti.Placeholder = "输入研究问题 / 待核查论断,或输入 / 调用命令"
	ti.Prompt = stAccent.Render("❯ ")
	ti.Focus()
	ti.CharLimit = 2000

	sp := spinner.New()
	sp.Spinner = spinner.Spinner{
		Frames: []string{"✻", "✢", "✳", "∗", "✦", "✶"},
		FPS:    spinnerFrameInterval,
	}
	sp.Style = stAccent
	m := model{ti: ti, spin: sp, sub: make(chan tea.Msg, 64), demo: demoMode(), sessionID: newSessionID()}
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

func (m *model) syncThemeStyles() {
	m.ti.Prompt = stAccent.Render("❯ ")
	m.spin.Style = stAccent
}

func (m *model) loadRecentSessions() {
	sessions, err := listSessionFiles(sessionDir(), 3)
	if err == nil {
		m.recentSessions = sessions
	}
}
