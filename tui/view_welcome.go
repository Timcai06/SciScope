// view_welcome.go — T05-03 沉浸式 Welcome。
//
// 替代旧 renderSplash 的三栏 Dashboard + 外层大卡：垂直层级为
//
//	[ASCII Logo / 紧凑 wordmark / 纯文本 SciScope]
//
//	SciScope · Research with evidence / 证据接地的科研智能体
//
//	/verify   /review   /trend   /demo
//
//	Recent
//	› /resume 1 · 最近问题
//
//	backend local · /doctor 检查后端与 LLM     ← faint 脚注
//
// composer 由外层 View() 渲染，是第二个视觉锚点；本函数只输出 viewport 内容区，
// 不产生任何边框（边框代表领域对象，不是启动页装饰）。
//
// 颜色纪律：Logo 与命令/focus 点用 stAccent，其余一律灰阶（stInk/stMuted/stFaint），
// 不引用任何散落 hex，一律走 theme.go 的语义样式。

package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

const (
	// welcomeFullCols 完整六行 ASCII Logo 的宽度下限。
	welcomeFullCols = 86
	// welcomeShortCols 紧凑 wordmark 的宽度下限；低于它回落纯文本品牌名。
	welcomeShortCols = 60

	// welcomeTagline 副标语；以 SciScope 开头保证任何宽度下品牌名都可见。
	welcomeTagline = "SciScope · Research with evidence / 证据接地的科研智能体"
)

// renderWelcome 渲染空会话时的沉浸式启动页（viewport 内容区，不含 composer）。
//
// 参数：
//   - width    视口宽度（列）。80/120/160 无断裂；<60 回落纯文本品牌名。
//   - sessions 最近会话（listSessionFiles 的结果，按 ModTime 倒序，最多渲染 3 条）。
//   - hosts    后端主机可达性快照（host → 是否可达）。
//
// 现有代码没有常驻的 hosts 探测状态，接线点现阶段传 nil 即可：
//   - hosts 为空时，脚注只展示由 backendMode(backendURL()) 派生的真实运行模式
//     （local/hosted，纯 URL 派生、无网络探测），详细健康状态交由 /doctor ——
//     绝不伪造 connected/ready/healthy。
//   - hosts 非空时，如实渲染调用方提供的可达性快照（排序保证确定性），
//     只有调用方明确给出的 unreachable 才使用 Warning 语义样式。
//
// 注意：backendMode(backendURL()) 读取环境变量，是确定性的派生（无网络），
// 对给定环境输出稳定。
func renderWelcome(width int, sessions []sessionFile, hosts map[string]bool) string {
	if width < 1 {
		width = 1
	}
	body := []string{
		"", // 顶部留白，Logo 是唯一大型视觉
	}
	body = append(body, strings.Split(welcomeBrand(width), "\n")...)
	body = append(body,
		"",
		stInk.Render(clipWidth(welcomeTagline, width)),
		"",
		welcomeCommandHint(width),
		"",
		stMuted.Render("Recent"),
	)
	body = append(body, welcomeRecentLines(width, sessions)...)
	body = append(body, "")
	body = append(body, welcomeStatusLines(width, hosts)...)
	return strings.Join(body, "\n")
}

// welcomeBrand 三档响应式品牌标（计划 5.2 节）：
//
//	>= 86 cols   完整六行 SciScope ASCII Logo（与 render.go asciiBrand 同源）
//	60–85 cols   紧凑块字 wordmark + 文本名 lockup
//	<  60 cols   纯文本 SciScope
func welcomeBrand(width int) string {
	if width >= welcomeFullCols {
		lines := []string{
			"███████╗ ██████╗██╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗",
			"██╔════╝██╔════╝██║██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝",
			"███████╗██║     ██║███████╗██║     ██║   ██║██████╔╝█████╗  ",
			"╚════██║██║     ██║╚════██║██║     ██║   ██║██╔═══╝ ██╔══╝  ",
			"███████║╚██████╗██║███████║╚██████╗╚██████╔╝██║     ███████╗",
			"╚══════╝ ╚═════╝╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝     ╚══════╝",
		}
		return stAccent.Render(strings.Join(lines, "\n"))
	}
	if width >= welcomeShortCols {
		// 紧凑 lockup：三行块字（每行 47 列）+ 文本名，60 列起即可完整放下。
		lines := append([]string{}, welcomeCompactMark...)
		lines = append(lines, "SciScope")
		return stAccent.Render(strings.Join(lines, "\n"))
	}
	return stAccent.Render(clipWidth("SciScope", width))
}

// welcomeCompactMark 紧凑 wordmark 的块字部分（S c i S c o p e，每行 47 列）。
var welcomeCompactMark = []string{
	"█████ █████   █   █████ █████ █████ █████ █████",
	"█     █       █   █     █     █   █ █   █ █   █",
	"█████ █████   █   █████ █████ █████ █     █████",
}

// welcomeCommandHint 可发现命令提示行：/verify /review /trend 是主推命令，
// /demo 保证黄金演示入口的可发现性（计划 T05-03 保留项）。
func welcomeCommandHint(width int) string {
	plain := "/verify   /review   /trend   /demo"
	if lipgloss.Width(plain) > width {
		// 极端窄屏：截断后整体 accent，不再分段。
		return stAccent.Render(clipWidth(plain, width))
	}
	return stAccent.Render("/verify") + stFaint.Render("   ") +
		stAccent.Render("/review") + stFaint.Render("   ") +
		stAccent.Render("/trend") + stFaint.Render("   ") +
		stAccent.Render("/demo")
}

// welcomeRecentLines 渲染 Recent 会话区：最多 3 条，问题文本按 width 截断；
// 无会话时保留 /demo 可发现性并提示自动保存。每一行都保证显示宽 ≤ width。
func welcomeRecentLines(width int, sessions []sessionFile) []string {
	if len(sessions) == 0 {
		plain := "  › 暂无本地会话 · /demo 播放黄金演示流"
		if lipgloss.Width(plain) > width {
			return []string{stMuted.Render(clipWidth(plain, width))}
		}
		return []string{
			stAccent.Render("  ›") + stMuted.Render(" 暂无本地会话 · ") +
				stAccent.Render("/demo") + stFaint.Render(" 播放黄金演示流"),
		}
	}
	lines := []string{}
	for i, s := range sessions {
		if i >= 3 {
			break
		}
		q := s.LastQuestion
		if q == "" {
			q = strings.TrimSuffix(s.Name, filepath.Ext(s.Name))
		}
		head := "  › /resume " + fmt.Sprint(s.Index) + " · "
		q = clipWidth(q, width-lipgloss.Width(head))
		row := head + q
		if lipgloss.Width(row) > width {
			// 极端窄屏：整行截断渲染，不再分段。
			lines = append(lines, stInk.Render(clipWidth(row, width)))
		} else {
			// 分段渲染必须与 row 逐列一致（"  ›" 3 列 + " /resume 1" 9 列 + " · " 3 列）。
			lines = append(lines,
				stAccent.Render("  ›")+stMuted.Render(" /resume "+fmt.Sprint(s.Index))+
					stInk.Render(" · "+q))
		}
		lines = append(lines, stFaint.Render(clipWidth("     "+s.ModTime.Format("01-02 15:04"), width)))
	}
	return lines
}

// welcomeStatusLines 渲染启动页唯一的后端状态脚注（一行 faint，降权到底部）：
//
//   - hosts 为空：只展示由 backendURL() 派生的真实运行模式（local/hosted）并
//     引导 /doctor，不伪造任何连通性结论（计划 T05-03：详细状态只由 /doctor 负责）；
//   - hosts 非空：如实渲染调用方提供的可达性快照，unreachable 是真实降级，
//     才允许 Warning 语义样式（计划 5.1 颜色纪律）。
func welcomeStatusLines(width int, hosts map[string]bool) []string {
	if len(hosts) == 0 {
		mode := backendMode(backendURL())
		return []string{stFaint.Render(clipWidth("backend "+mode+" · /doctor 检查后端与 LLM", width))}
	}
	names := make([]string, 0, len(hosts))
	for host := range hosts {
		names = append(names, host)
	}
	sort.Strings(names) // map 遍历随机，排序保证输出确定性
	lines := make([]string, 0, len(names))
	for _, host := range names {
		state := "ok"
		stateStyle := stFaint
		if !hosts[host] {
			state = "unreachable"
			stateStyle = stWarn
		}
		plain := "backend " + host + " " + state + " · /doctor"
		if lipgloss.Width(plain) > width {
			lines = append(lines, stFaint.Render(clipWidth(plain, width)))
			continue
		}
		lines = append(lines,
			stFaint.Render("backend "+host+" ")+stateStyle.Render(state)+stFaint.Render(" · /doctor"))
	}
	return lines
}
