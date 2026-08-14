// view_overlay.go — T05-08 统一 Overlay / Picker / Command Palette 层。
//
// 把原先 renderCommandPalette / renderSubmenuPalette 两条独立的多级字符串菜单
// 合并为同一套 OverlayState / PickerSection 数据模型与渲染 grammar（计划
// T05-08「所有二级菜单共享一套 navigation / focus / Esc 语义」）：
//
//   - 六类承载共用同一 grammar：Slash Commands（OverlayCommand）、Theme
//     （OverlayTheme）、Sessions/Resume（OverlaySessions）、Tools（OverlayTools）、
//     Doctor（OverlayDoctor）、Clear/Quit confirm（OverlayConfirm）；
//   - 渲染基元只复用 style_primitives.go 的 overlayBorderStyle / selectedRow /
//     separator 与 theme.go 的语义样式（stAccent / stFaint / stInk / stMuted），
//     本文件不出现任何散落 hex；
//   - 选中行用 AccentSoft 背景 + ❯ marker，不做刺眼全反色；不模拟 Web blur；
//   - Esc 层级语义由 escBehavior 确定：子 picker → 父 picker → close；
//   - 渲染输出为纯字符串（无副作用），宽度受 width 约束、每行显示宽度不越界，
//     调用方负责在屏幕上水平居中放置返回值。
package main

import (
	"fmt"
	"slices"
	"sort"
	"strings"
	"unicode"

	"github.com/charmbracelet/lipgloss"
)

// OverlayKind 标识 overlay 承载的内容类型（计划 T05-08 六类统一承载）。
type OverlayKind string

const (
	OverlayCommand  OverlayKind = "command"  // Slash 命令启动器
	OverlayTheme    OverlayKind = "theme"    // 主题选择
	OverlaySessions OverlayKind = "sessions" // 会话恢复 / Resume
	OverlayTools    OverlayKind = "tools"    // 工具目录
	OverlayDoctor   OverlayKind = "doctor"   // 体检检查项
	OverlayConfirm  OverlayKind = "confirm"  // Clear / Quit 确认
)

// EscResult 是 Esc 键的层级语义：子 picker 弹回父 picker，顶层 overlay 关闭
// （计划 T05-08：子 picker → 父 picker → close，层级确定）。
type EscResult int

const (
	EscClose EscResult = iota // 顶层 overlay：关闭
	EscPop                    // 子 picker：弹回 Parent
)

// OverlayFooter 是底部提示行的层级。navigable 提供 ↑↓/Enter/Esc 三键提示；
// confirm 面向 Clear/Quit 确认，只显示 Enter/Esc。
type OverlayFooter string

const (
	FooterNavigable OverlayFooter = "navigable"
	FooterConfirm   OverlayFooter = "confirm"
)

// PickerItem 是 picker 中的一个可选条目。
//
//   - Label：短标识（如命令名 "/verify"），Shortcut 为空时右对齐列退回 Label；
//   - Category：分组键（空归入 "其他"）；Title 是第一行主文本；
//   - Desc：第二行 faint 详情，超宽截断；Shortcut 右对齐显示；
//   - Command：选中后执行的完整命令（Enter 语义由调用方消费）。
type PickerItem struct {
	Label    string
	Category string
	Title    string
	Desc     string
	Shortcut string
	Command  string
}

// PickerSection 是一组同类条目，Title 是分组标题。
type PickerSection struct {
	Title string
	Items []PickerItem
}

// OverlayState 是 overlay/picker 的完整 UI 状态。
//
//   - Kind 决定标题行与默认分组顺序；Query 是搜索框输入（可含 "/" 前缀）；
//   - Selection 是 Sections 展平后（跳过分组头）的选中索引，越界在渲染时
//     自动收敛；Sections 一般由 buildOverlaySections + filterOverlaySections
//     构建；Query 过滤也可交由 renderPickerOverlay 内完成；
//   - Parent 非 nil 时本 overlay 是子 picker，Esc 弹回 Parent（escBehavior）；
//   - Footer 控制底部提示行（空按 navigable 处理）。
type OverlayState struct {
	Kind      OverlayKind
	Query     string
	Selection int
	Sections  []PickerSection
	Footer    OverlayFooter
	Parent    *OverlayState
}

// escBehavior 返回 Esc 键对 state 的层级语义：有父 picker 弹回父级（EscPop），
// 顶层 overlay 关闭（EscClose）。
func escBehavior(state OverlayState) EscResult {
	if state.Parent != nil {
		return EscPop
	}
	return EscClose
}

// overlayKindTitle 返回 kind 的标题行文本（对应原 submenuTitle 的六类语义）。
func overlayKindTitle(kind OverlayKind) string {
	switch kind {
	case OverlayTheme:
		return "选择主题"
	case OverlaySessions:
		return "恢复会话"
	case OverlayTools:
		return "选择工具"
	case OverlayDoctor:
		return "查看检查项"
	case OverlayConfirm:
		return "确认操作"
	default:
		return "命令启动器"
	}
}

// overlayCategoryOrder 返回 kind 的默认分组顺序；未列出的分组按首次出现顺序
// 追加在后。Slash 命令沿用既有「常用/会话/证据/系统」顺序。
func overlayCategoryOrder(kind OverlayKind) []string {
	if kind == OverlayCommand {
		return []string{"常用", "会话", "证据", "系统"}
	}
	return nil
}

// buildOverlaySections 按 Category 分组 items：分组顺序优先 overlayCategoryOrder，
// 未列出分组按首次出现顺序追加；组内保持输入顺序稳定；空 Category 归入 "其他"。
func buildOverlaySections(kind OverlayKind, items []PickerItem) []PickerSection {
	order := []string{}
	byCat := map[string][]PickerItem{}
	for _, it := range items {
		cat := it.Category
		if cat == "" {
			cat = "其他"
		}
		if _, ok := byCat[cat]; !ok {
			order = append(order, cat)
		}
		byCat[cat] = append(byCat[cat], it)
	}
	if preferred := overlayCategoryOrder(kind); len(preferred) > 0 {
		rank := make(map[string]int, len(preferred))
		for i, cat := range preferred {
			rank[cat] = i
		}
		sort.SliceStable(order, func(i, j int) bool {
			ri, iOK := rank[order[i]]
			rj, jOK := rank[order[j]]
			switch {
			case iOK && jOK:
				return ri < rj
			case iOK:
				return true
			case jOK:
				return false
			default:
				return false
			}
		})
	}
	sections := make([]PickerSection, 0, len(order))
	for _, cat := range order {
		sections = append(sections, PickerSection{Title: cat, Items: byCat[cat]})
	}
	return sections
}

// filterOverlaySections 按 Query 过滤 sections：空 Query（含纯 "/"）原样返回；
// 否则条目 Label/Category/Title/Desc/Shortcut/Command 任一包含 query（忽略
// 大小写、剥掉 "/" 前缀）即保留，条目全被滤掉的分组一并移除。
func filterOverlaySections(query string, sections []PickerSection) []PickerSection {
	query = strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(query), "/"))
	if query == "" {
		return sections
	}
	query = strings.ToLower(query)
	out := make([]PickerSection, 0, len(sections))
	for _, sec := range sections {
		kept := make([]PickerItem, 0, len(sec.Items))
		for _, it := range sec.Items {
			haystack := strings.ToLower(strings.Join(
				[]string{it.Label, it.Category, it.Title, it.Desc, it.Shortcut, it.Command}, " "))
			if strings.Contains(haystack, query) {
				kept = append(kept, it)
			}
		}
		if len(kept) > 0 {
			out = append(out, PickerSection{Title: sec.Title, Items: kept})
		}
	}
	return out
}

// highlightFuzzy 用 stAccent 包裹 text 中第一次出现的 query（忽略大小写，rune
// 对齐，Unicode 大小写折叠不改变长度）片段；query 为空或未命中时返回原文本。
// 只作用于未样式化的纯文本，调用方应先裁剪再高亮。
func highlightFuzzy(text, query string) string {
	query = strings.TrimSpace(query)
	if query == "" || text == "" {
		return text
	}
	textRunes := []rune(text)
	queryRunes := lowerRunes([]rune(query))
	haystack := lowerRunes(textRunes)
	idx := runeIndex(haystack, queryRunes)
	if idx < 0 {
		return text
	}
	return string(textRunes[:idx]) +
		stAccent.Render(string(textRunes[idx:idx+len(queryRunes)])) +
		string(textRunes[idx+len(queryRunes):])
}

// lowerRunes 逐 rune 转小写，避免 strings.ToLower 的折叠改变 rune 数量。
func lowerRunes(rs []rune) []rune {
	out := make([]rune, len(rs))
	for i, r := range rs {
		out[i] = unicode.ToLower(r)
	}
	return out
}

// runeIndex 返回 needle 在 haystack 中的首个 rune 索引（无命中返回 -1）。
func runeIndex(haystack, needle []rune) int {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if slices.Equal(haystack[i:i+len(needle)], needle) {
			return i
		}
	}
	return -1
}

// renderPickerOverlay 把 OverlayState 渲染为带边框的候选 overlay（纯函数，无副作用）。
//
// 布局（计划 T05-08 ASCII 图）：
//
//	╭─ <kind 标题> ────────────────────────────╮
//	│  search: <query>                          │
//	│  ──────────────────────────────────────── │
//	│  <category 分组头>                        │
//	│  ❯ <title>              <shortcut>       │
//	│    <desc（第二行 faint 截断）>            │
//	│  ──────────────────────────────────────── │
//	│  ↑↓ 导航 · Enter 选择 · Esc 关闭          │
//	╰───────────────────────────────────────────╯
//
// 纪律：
//   - 整体用 overlayBorderStyle()（RoundedBorder + Accent 边框 + Surface 表面），
//     总宽恰为 width（width < 18 时收缩到最小可用宽），每行显示宽度 ≤ width；
//   - height 只用于限制可见条目窗口（窗口跟随 Selection 滚动，chrome 固定 9 行：
//     边框 2 + 内边距 2 + 标题 1 + 搜索 1 + 分隔线 2 + footer 1）；
//   - 选中行用 selectedRow()（AccentSoft 背景 + ❯ marker），不模拟 Web blur；
//   - Query 非空时在内部先 filterOverlaySections，再对 Title 做 fuzzy 高亮。
//
// 调用方（View 组装）负责把返回值水平/垂直居中放置到屏幕上。
func renderPickerOverlay(state OverlayState, width, height int) string {
	const (
		minOverlayW = 18 // 最小总宽（边框 2 + 内边距 4 + 内容 12）
		chromeH     = 9  // 边框 2 + 内边距 2 + 标题 1 + 搜索 1 + 分隔 2 + footer 1
	)
	if width < minOverlayW {
		width = minOverlayW
	}
	contentW := width - 6 // 左右边框 2 + 内边距 2*CardPadX
	if contentW < 12 {
		contentW = 12
		width = contentW + 6
	}
	query := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(state.Query), "/"))

	sections := filterOverlaySections(query, state.Sections)

	itemCount := 0
	for _, sec := range sections {
		itemCount += len(sec.Items)
	}
	sel := state.Selection
	switch {
	case sel < 0 || itemCount == 0:
		sel = 0
	case sel >= itemCount:
		sel = itemCount - 1
	}

	// 展平为行（分组头 1 行 + 条目 1~2 行），跟踪每行所属条目的全局索引。
	type overlayLine struct {
		item int // -1 = 分组头
		text string
	}
	flattened := make([]overlayLine, 0, itemCount+len(sections))
	idx := 0
	for _, sec := range sections {
		if sec.Title != "" {
			// T05 样式优化：分组头醒目化——Accent 菱形 + Ink 分类名 + faint 数量，
			// 与条目行形成清晰视觉层级。
			head := stAccent.Render("◆ ") + stInk.Render(sec.Title) +
				stFaint.Render(" · "+fmt.Sprint(len(sec.Items)))
			flattened = append(flattened, overlayLine{-1, clipWidth(head, contentW-2)})
		}
		for _, it := range sec.Items {
			// T05 样式优化：单行条目（名称 + 描述同行），不再为 desc 单独开行。
			flattened = append(flattened, overlayLine{idx, renderPickerRow(it, idx == sel, query, contentW)})
			idx++
		}
	}

	// 可见窗口跟随 Selection：选中条目整条（含 desc 行）保持在窗口内。
	vis := height - chromeH
	if vis < 1 {
		vis = 1
	}
	start := 0
	if itemCount > 0 {
		selStart, selEnd := -1, -1
		for i, ln := range flattened {
			if ln.item == sel {
				if selStart < 0 {
					selStart = i
				}
				selEnd = i
			}
		}
		switch {
		case selEnd-selStart+1 >= vis:
			start = selStart
		case selStart < start:
			start = selStart
		case selEnd >= start+vis:
			start = selEnd - vis + 1
		}
	}
	end := start + vis
	if end > len(flattened) {
		end = len(flattened)
		start = end - vis
		if start < 0 {
			start = 0
		}
	}

	head := stAccent.Render(overlayKindTitle(state.Kind))
	search := stFaint.Render("search: ")
	if query == "" {
		search += stFaint.Render(clipWidth("输入关键词过滤…", contentW-8))
	} else {
		search += stAccent.Render(clipWidth(query, contentW-8))
	}
	rows := []string{head, search, separator(contentW)}
	if itemCount == 0 {
		rows = append(rows, stFaint.Render("  没有匹配项 · Esc 返回"))
	} else {
		for _, ln := range flattened[start:end] {
			rows = append(rows, ln.text)
		}
	}
	rows = append(rows, separator(contentW), overlayFooterLine(state.Footer, contentW))
	// 实测当前 lipgloss：Style.Width(W) 的总宽 = W+2（边框 2 额外计入），
	// 因此传 width-2 得到总宽恰为 width；内容区 = width-6 = contentW，
	// 与各行（renderPickerRow/separator/footer）宽度一致，不会触发软换行。
	return overlayBorderStyle().Width(width - 2).Render(strings.Join(rows, "\n"))
}

// renderPickerRow 渲染一个条目行：选中行用 ❯ marker 且整行过 selectedRow()
// （AccentSoft 背景），Title 命中 query 的片段用 stAccent 高亮，shortcut 右对齐
// 且 faint（Shortcut 为空时退回 Label）；行显示宽度恰为 contentW。
func renderPickerRow(item PickerItem, selected bool, query string, contentW int) string {
	// T05 样式优化（项目负责人反馈）：单行条目——命令名 + 名称 + 描述同行，
	// 不再为 desc 单独换行；命令名（Label）固定最前，描述 faint 尾部截断。
	title := strings.TrimSpace(item.Title)
	label := strings.TrimSpace(item.Label)
	if label == "" {
		label = strings.TrimSpace(item.Shortcut)
	}
	desc := strings.TrimSpace(item.Desc)
	labelW := lipgloss.Width(label)
	avail := contentW - 4 - labelW - 2 // marker(2) + 分隔空格 + 右侧内容
	if avail < 6 {
		avail = 6
	}
	right := title
	if desc != "" {
		right = title + " · " + desc
	}
	// 先截断（纯文本安全）再高亮（高亮在截断后的文本上做，不切 ANSI）。
	right = clipWidth(right, avail)
	right = highlightFuzzy(right, query)
	marker := "  "
	if selected {
		marker = "❯ "
	}
	line := marker + stAccent.Render(label) + " " + stInk.Render(right)
	if selected {
		return selectedRow(line)
	}
	return line
}

// overlayFooterLine 渲染底部提示行（计划 T05-08 footer 三档层级）：
// 键名 bold（Muted + Bold）、动作词 Muted、分隔符 Faint。行宽超过可用宽度时
// 退化为纯键名行（↑↓ Enter Esc，宽 12）。
func overlayFooterLine(footer OverlayFooter, width int) string {
	key := func(s string) string {
		return lipgloss.NewStyle().Foreground(cMuted).Bold(true).Render(s)
	}
	act := stFaint.Render
	sep := FaintText().Render(" · ")
	var line string
	if footer == FooterConfirm {
		line = key("Enter") + act(" 确认") + sep + key("Esc") + act(" 返回")
	} else {
		line = key("↑↓") + act(" 导航") + sep + key("Enter") + act(" 选择") + sep + key("Esc") + act(" 关闭")
	}
	if lipgloss.Width(line) <= width {
		return line
	}
	return key("↑↓") + act(" ") + key("Enter") + act(" ") + key("Esc")
}
