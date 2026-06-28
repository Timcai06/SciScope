package main

import (
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
	{cmd: "/review", title: "文献综述", desc: "把主题展开为综述/研究现状任务", category: "常用", key: "review <topic>", kind: commandPrompt, suggested: true},
	{cmd: "/trend", title: "趋势分析", desc: "把主题展开为趋势预测任务", category: "常用", key: "trend <topic>", kind: commandPrompt, suggested: true},
	{cmd: "/recommend", title: "论文推荐", desc: "把主题或种子论文展开为推荐任务", category: "常用", key: "recommend <topic|paper_id>", kind: commandPrompt, suggested: true},
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
