package main

import (
	"fmt"
	"path/filepath"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

type slashCommandKind string

const (
	commandLocal  slashCommandKind = "local"
	commandPrompt slashCommandKind = "prompt"
	commandUI     slashCommandKind = "ui"
)

type slashExecutor func(model, []string) (model, tea.Cmd)

type slashCmd struct {
	cmd       string
	title     string
	desc      string
	category  string
	key       string
	kind      slashCommandKind
	submenu   string
	suggested bool
	run       slashExecutor
}

var slashCmds = []slashCmd{
	{cmd: "/demo", title: "黄金演示", desc: "播放可验证证据流", category: "常用", key: "demo", kind: commandLocal, suggested: true},
	{cmd: "/verify", title: "论断核查", desc: "把论断展开为证据核查任务", category: "常用", key: "verify <claim>", kind: commandPrompt, suggested: true},
	{cmd: "/review", title: "文献综述", desc: "把主题展开为研究现状与证据综述", category: "常用", key: "review <topic>", kind: commandPrompt, suggested: true},
	{cmd: "/trend", title: "趋势分析", desc: "把主题展开为描述性趋势任务", category: "常用", key: "trend <topic>", kind: commandPrompt, suggested: true},
	{cmd: "/recommend", title: "论文推荐", desc: "把主题或种子论文展开为推荐线索任务", category: "常用", key: "recommend <topic|paper_id>", kind: commandPrompt, suggested: true},
	{cmd: "/doctor", title: "状态体检", desc: "检查后端、LLM、会话与图谱", category: "常用", key: "doctor", kind: commandUI, submenu: "doctor", suggested: true},
	{cmd: "/retry", title: "重试上一问", desc: "同一 LangGraph 会话线程恢复上一问", category: "常用", key: "retry", kind: commandLocal, suggested: true},
	{cmd: "/export", title: "导出报告", desc: "导出 Markdown 会话与证据", category: "常用", key: "export", kind: commandLocal, suggested: true},
	{cmd: "/sessions", title: "最近会话", desc: "列出最近研究会话", category: "会话", key: "sessions", kind: commandUI, submenu: "resume"},
	{cmd: "/resume", title: "恢复会话", desc: "恢复会话: /resume 1", category: "会话", key: "resume N", kind: commandUI, submenu: "resume"},
	{cmd: "/timeline", title: "执行时间线", desc: "查看本轮 LangGraph 与工具轨迹", category: "证据", key: "timeline", kind: commandLocal},
	{cmd: "/tools", title: "智能体工具", desc: "列出 LLM 可自主调用的科研工具", category: "证据", key: "tools", kind: commandUI, submenu: "tools"},
	{cmd: "/theme", title: "视觉主题", desc: "查看或切换 TUI 主题: /theme paper", category: "系统", key: "theme", kind: commandUI, submenu: "theme"},
	{cmd: "/help", title: "帮助", desc: "显示命令与快捷键", category: "系统", key: "?", kind: commandLocal},
	{cmd: "/clear", title: "清空视图", desc: "清空当前对话视图", category: "系统", key: "clear", kind: commandUI, submenu: "clear"},
	{cmd: "/quit", title: "退出", desc: "退出 SciScope TUI", category: "系统", key: "ctrl+c", kind: commandUI, submenu: "quit"},
}

var slashExecutors = map[string]slashExecutor{
	"/clear":     runClearCommand,
	"/demo":      runDemoCommand,
	"/doctor":    runDoctorCommand,
	"/export":    runExportCommand,
	"/help":      runHelpCommand,
	"/quit":      runQuitCommand,
	"/recommend": runRecommendCommand,
	"/resume":    runResumeCommand,
	"/review":    runReviewCommand,
	"/retry":     runRetryCommand,
	"/sessions":  runSessionsCommand,
	"/theme":     runThemeCommand,
	"/timeline":  runTimelineCommand,
	"/tools":     runToolsCommand,
	"/trend":     runTrendCommand,
	"/verify":    runVerifyCommand,
}
var slashRegistry = buildSlashRegistry(slashCmds)

func buildSlashRegistry(commands []slashCmd) map[string]slashCmd {
	registry := map[string]slashCmd{}
	for _, command := range commands {
		command.run = slashExecutors[command.cmd]
		registry[command.cmd] = command
	}
	return registry
}

func filterCmds(prefix string) []slashCmd {
	query := strings.TrimSpace(strings.TrimPrefix(prefix, "/"))
	query = strings.ToLower(query)
	matches := []slashCmd{}
	for _, c := range slashCmds {
		haystack := strings.ToLower(strings.Join([]string{c.cmd, c.title, c.desc, c.category}, " "))
		if query == "" || strings.Contains(haystack, query) {
			matches = append(matches, c)
		}
	}
	if query != "" {
		return matches
	}
	out := []slashCmd{}
	for _, c := range matches {
		if c.suggested {
			out = append(out, c)
		}
	}
	for _, c := range matches {
		if !c.suggested {
			out = append(out, c)
		}
	}
	return out
}

// ---- stream messages ----

// ---- 以下从 main.go 搬移（T05-10）----

type submenuItem struct {
	label   string
	desc    string
	command string
}

func commandSubmenu(cmd string) string {
	fields := strings.Fields(cmd)
	if len(fields) == 0 {
		return ""
	}
	if command, ok := slashRegistry[fields[0]]; ok {
		return command.submenu
	}
	return ""
}

type toolInfo struct {
	name string
	desc string
	when string
}

func toolCatalog() []toolInfo {
	return []toolInfo{
		{"search_literature", "混合检索论文证据", "文献问答、查新、证据补充"},
		{"get_trends", "查看关键词趋势与生命周期", "趋势预测、热点监测"},
		{"recommend_papers", "按种子论文推荐相似研究", "延伸阅读、相关工作"},
		{"get_paper", "读取单篇论文详情", "已知 paper_id 后深读"},
		{"summarize_field", "生成领域综述证据", "主题综述、背景整理"},
		{"compare_papers", "对比两篇论文", "方法差异、贡献比较"},
		{"export_bibliography", "导出引用文本", "写报告、整理参考文献"},
		{"query_knowledge_graph", "查询作者/关键词/主题图谱", "合作网络、主题关系"},
		{"list_disputes", "读取同一论断的正反证据前线", "争议地图、正反证据对照"},
		{"verify_claim", "核查论断并返回证据", "事实核查、降低幻觉"},
	}
}

func toolInfoByName(name string) (toolInfo, bool) {
	for _, tool := range toolCatalog() {
		if tool.name == name || toolPlainLabel(tool.name) == name {
			return tool, true
		}
	}
	return toolInfo{}, false
}

func submenuTitle(name string) string {
	switch name {
	case "theme":
		return "选择主题"
	case "resume":
		return "恢复会话"
	case "tools":
		return "选择工具"
	case "doctor":
		return "查看检查项"
	case "clear":
		return "确认清空"
	case "quit":
		return "确认退出"
	default:
		return "二级选择"
	}
}

func (m model) submenuItems() []submenuItem {
	switch m.submenu {
	case "theme":
		items := []submenuItem{}
		for _, name := range themeOrder {
			theme := themes[name]
			items = append(items, submenuItem{label: theme.Name, desc: theme.Title + " · " + theme.Desc, command: "/theme " + theme.Name})
		}
		return items
	case "resume":
		items := []submenuItem{}
		for _, session := range m.recentSessions {
			question := session.LastQuestion
			if question == "" {
				question = strings.TrimSuffix(session.Name, filepath.Ext(session.Name))
			}
			items = append(items, submenuItem{
				label:   fmt.Sprintf("%d", session.Index),
				desc:    clip(question, 58) + " · " + session.ModTime.Format("01-02 15:04"),
				command: fmt.Sprintf("/resume %d", session.Index),
			})
		}
		return items
	case "tools":
		items := []submenuItem{}
		for _, tool := range toolCatalog() {
			items = append(items, submenuItem{label: toolPlainLabel(tool.name), desc: tool.desc + " · " + tool.when, command: "/tools " + tool.name})
		}
		return items
	case "doctor":
		items := []submenuItem{}
		for _, check := range collectDoctorChecks() {
			items = append(items, submenuItem{label: check.Name, desc: check.Status + " · " + check.Detail, command: "/doctor " + check.Name})
		}
		return items
	case "clear":
		return []submenuItem{{label: "取消", desc: "保留当前对话", command: "/clear no"}, {label: "清空", desc: "清空当前视图、历史和时间线", command: "/clear yes"}}
	case "quit":
		return []submenuItem{{label: "取消", desc: "继续当前会话", command: "/quit no"}, {label: "退出", desc: "关闭 SciScope TUI", command: "/quit yes"}}
	default:
		return nil
	}
}

// overlayKindForSubmenu 把 submenu 名映射为统一 Overlay kind（T05-08）。

func overlayKindForSubmenu(name string) (OverlayKind, OverlayFooter) {
	switch name {
	case "theme":
		return OverlayTheme, FooterNavigable
	case "resume":
		return OverlaySessions, FooterNavigable
	case "tools":
		return OverlayTools, FooterNavigable
	case "doctor":
		return OverlayDoctor, FooterNavigable
	case "clear", "quit":
		return OverlayConfirm, FooterConfirm
	default:
		return OverlayCommand, FooterNavigable
	}
}

func (m model) renderSubmenuPalette(width int) string {
	items := m.submenuItems()
	if len(items) == 0 {
		return panelRow("launcher", submenuTitle(m.submenu), "empty", []string{"暂无可选项。Esc 返回。"})
	}
	// T05-08 接线：二级菜单走统一 Overlay/Picker grammar。
	kind, footer := overlayKindForSubmenu(m.submenu)
	pickerItems := make([]PickerItem, 0, len(items))
	for _, it := range items {
		pickerItems = append(pickerItems, PickerItem{
			Title:    it.label,
			Desc:     it.desc,
			Shortcut: it.command,
			Command:  it.command,
		})
	}
	state := OverlayState{
		Kind:      kind,
		Selection: m.submenuIdx % len(items),
		Sections:  buildOverlaySections(kind, pickerItems),
		Footer:    footer,
	}
	return renderPickerOverlay(state, width, 26)
}

func (m *model) openSubmenu(name string) {
	m.submenu = name
	m.submenuIdx = 0
	switch name {
	case "theme":
		m.ti.SetValue("/theme ")
	case "resume":
		sessions, err := listSessionFiles(sessionDir(), 8)
		if err == nil {
			m.recentSessions = sessions
		}
		m.ti.SetValue("/resume ")
	case "tools":
		m.ti.SetValue("/tools ")
	case "doctor":
		m.ti.SetValue("/doctor ")
	case "clear":
		m.ti.SetValue("/clear ")
	case "quit":
		m.ti.SetValue("/quit ")
	}
}

func renderSlashHelpBlock() string {
	groups := map[string][]slashCmd{}
	for _, cmd := range slashCmds {
		groups[cmd.category] = append(groups[cmd.category], cmd)
	}
	order := []string{"常用", "会话", "证据", "系统"}
	body := []string{"使用 / 打开命令启动器; Enter 执行, Esc 返回。"}
	body = append(body, stFaint.Render("服务或数据不可用时, 按错误面板提示操作: /doctor 查看状态, /retry 重试, 失败原因会随会话保存。"))
	body = append(body, "")
	body = append(body, stAccent.Render("评委黄金任务"))
	for _, task := range goldenJudgeTasks() {
		body = append(body, "  "+task.Command)
		body = append(body, stFaint.Render("    "+task.Goal))
		body = append(body, stFaint.Render("    边界: "+task.Boundary))
	}
	body = append(body, "")
	body = append(body, stAccent.Render("能力边界"))
	body = append(body, stFaint.Render("  /trend 当前只展示描述性趋势, 不把统计外推写成预测结论。"))
	body = append(body, stFaint.Render("  /recommend 依赖 paper embeddings; 资产未就绪时必须显示 unavailable。"))
	for _, group := range order {
		cmds := groups[group]
		if len(cmds) == 0 {
			continue
		}
		body = append(body, "")
		body = append(body, stAccent.Render(group))
		for _, cmd := range cmds {
			body = append(body, fmt.Sprintf("  %-10s %s", cmd.cmd, cmd.desc))
		}
	}
	return panelRow("launcher", "命令启动器", "slash", body)
}

func renderToolsBlock() string {
	type toolInfo struct {
		name string
		desc string
	}
	tools := []toolInfo{
		{"search_literature", "混合检索论文证据"},
		{"get_trends", "查看关键词趋势与生命周期"},
		{"recommend_papers", "按种子论文推荐相似研究"},
		{"get_paper", "读取单篇论文详情"},
		{"summarize_field", "生成领域综述证据"},
		{"compare_papers", "对比两篇论文"},
		{"export_bibliography", "导出引用文本"},
		{"query_knowledge_graph", "查询作者/关键词/主题图谱"},
		{"list_disputes", "读取可核验证据支撑的争议前线"},
		{"verify_claim", "核查论断并返回证据"},
	}
	body := []string{"这些工具由 LLM 按问题自主调用; /timeline 查看每次调用过程。"}
	for _, tool := range tools {
		body = append(body, fmt.Sprintf("  %-18s %s", toolPlainLabel(tool.name), tool.desc))
	}
	return panelRow("tools", "智能体工具", "read-only", body)
}

func renderInlineDoctorBlock() string {
	body := []string{}
	for _, check := range collectDoctorChecks() {
		line := fmt.Sprintf("%s  %s", check.Status, check.Name)
		if check.Detail != "" {
			line += " · " + check.Detail
		}
		body = append(body, line)
	}
	return panelRow("doctor", "系统状态", "live", body)
}
