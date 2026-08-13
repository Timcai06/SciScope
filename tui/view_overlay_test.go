// view_overlay_test.go — T05-08 Overlay / Picker / Command Palette 单元测试。
//
// 覆盖计划验收点：分组正确、Query 过滤正确、fuzzy 高亮、选中态（AccentSoft
// 背景 + ❯ marker）、Esc 层级状态机（子 → 父 → close）、80 列渲染每行显示
// 宽度不越界、footer 含 ↑↓/Enter/Esc 提示、渲染源码无散落 hex。
package main

import (
	"os"
	"regexp"
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

// fixtureItems 返回覆盖「常用/会话/系统」三组 + 无分类条目的命令条目。
func fixtureItems() []PickerItem {
	return []PickerItem{
		{Label: "/demo", Category: "常用", Title: "黄金演示", Desc: "播放可验证证据流", Shortcut: "demo", Command: "/demo"},
		{Label: "/verify", Category: "常用", Title: "Verify claim", Desc: "把论断展开为证据核查任务", Shortcut: "verify <claim>", Command: "/verify"},
		{Label: "/sessions", Category: "会话", Title: "最近会话", Desc: "列出最近研究会话", Shortcut: "sessions", Command: "/sessions"},
		{Label: "/theme", Category: "系统", Title: "视觉主题", Desc: "查看或切换 TUI 主题", Shortcut: "theme", Command: "/theme"},
		{Label: "/misc", Title: "无分类条目", Desc: "", Shortcut: "", Command: "/misc"},
	}
}

func TestOverlaySectionsGroupByCategory(t *testing.T) {
	sections := buildOverlaySections(OverlayCommand, fixtureItems())
	if len(sections) != 4 {
		t.Fatalf("section count = %d, want 4: %#v", len(sections), sections)
	}
	// overlayCategoryOrder(OverlayCommand) = 常用/会话/证据/系统；无分类条目归入
	// "其他" 并排在最后。
	wantTitles := []string{"常用", "会话", "系统", "其他"}
	wantCounts := []int{2, 1, 1, 1}
	for i, want := range wantTitles {
		if sections[i].Title != want {
			t.Fatalf("section[%d] title = %q, want %q", i, sections[i].Title, want)
		}
		if len(sections[i].Items) != wantCounts[i] {
			t.Fatalf("section[%d] %q items = %d, want %d", i, want, len(sections[i].Items), wantCounts[i])
		}
	}
	// 组内保持输入顺序稳定。
	if sections[0].Items[0].Command != "/demo" || sections[0].Items[1].Command != "/verify" {
		t.Fatalf("常用 group order changed: %#v", sections[0].Items)
	}
}

func TestOverlaySectionsKeepFirstSeenOrderWithoutPreference(t *testing.T) {
	items := []PickerItem{
		{Title: "b", Category: "B组"},
		{Title: "a", Category: "A组"},
		{Title: "c", Category: "B组"},
	}
	sections := buildOverlaySections(OverlayTheme, items)
	if len(sections) != 2 || sections[0].Title != "B组" || sections[1].Title != "A组" {
		t.Fatalf("unpreferred order should stay first-seen, got %#v", sections)
	}
}

func TestOverlayFilterSectionsByQuery(t *testing.T) {
	sections := buildOverlaySections(OverlayCommand, fixtureItems())

	// 命中 Title（忽略大小写）。
	got := filterOverlaySections("verify", sections)
	if len(got) != 1 || len(got[0].Items) != 1 || got[0].Items[0].Command != "/verify" {
		t.Fatalf("filter verify = %#v, want only /verify", got)
	}

	// "/" 前缀剥掉后按中文 description 命中（/demo 与 /verify 的 desc 均含「证据」）。
	got = filterOverlaySections("/证据", sections)
	if len(got) != 1 || len(got[0].Items) != 2 ||
		got[0].Items[0].Command != "/demo" || got[0].Items[1].Command != "/verify" {
		t.Fatalf("filter /证据 = %#v, want 常用组 /demo + /verify via desc", got)
	}

	// 空 Query 原样返回（含分组结构）。
	if got := filterOverlaySections("", sections); len(got) != len(sections) {
		t.Fatalf("empty query changed sections: %#v", got)
	}

	// 无命中返回空。
	if got := filterOverlaySections("zzz-no-match", sections); len(got) != 0 {
		t.Fatalf("no-match filter = %#v, want empty", got)
	}
}

func TestPickerOverlayHighlightsFuzzyMatch(t *testing.T) {
	restoreDarkTheme(t)
	sections := buildOverlaySections(OverlayCommand, fixtureItems())
	state := OverlayState{Kind: OverlayCommand, Query: "ver", Selection: 0, Sections: sections, Footer: FooterNavigable}
	out := renderPickerOverlay(state, 80, 24)

	// Title "Verify claim" 中命中片段 "Ver" 被 stAccent 包裹（大小写不敏感、保留原文大小写）。
	if !strings.Contains(out, stAccent.Render("Ver")) {
		t.Fatalf("overlay missing highlighted fragment %q:\n%s", stAccent.Render("Ver"), out)
	}
	// 搜索框中的 Query 也用 stAccent 显示。
	if !strings.Contains(out, stAccent.Render("ver")) {
		t.Fatalf("overlay search line missing accent query:\n%s", out)
	}
	// 未命中的条目被过滤掉。
	if strings.Contains(out, "黄金演示") {
		t.Fatalf("overlay should filter non-matching items:\n%s", out)
	}
}

func TestPickerOverlaySelectedRowUsesAccentSoftAndMarker(t *testing.T) {
	restoreDarkTheme(t)
	sections := buildOverlaySections(OverlayCommand, fixtureItems())
	state := OverlayState{Kind: OverlayCommand, Selection: 1, Sections: sections, Footer: FooterNavigable}
	out := renderPickerOverlay(state, 80, 24)

	if !strings.Contains(out, "❯") {
		t.Fatalf("overlay missing ❯ marker:\n%s", out)
	}
	if strings.Count(out, "❯") != 1 {
		t.Fatalf("exactly one row should carry the marker, got %d:\n%s", strings.Count(out, "❯"), out)
	}
	if !strings.Contains(out, "Verify claim") {
		t.Fatalf("selected row lost title:\n%s", out)
	}

	// selectedRow 使用 AccentSoft 背景（非全反色）：与 theme_test 同款 probe，
	// 从同一颜色的样式渲染输出中提取背景色 SGR 序列后断言包含关系。
	probe := lipgloss.NewStyle().Background(activeTheme().AccentSoft).Render("p")
	start := strings.Index(probe, "48;2;")
	end := strings.Index(probe[start:], "m") + start + 1
	bgSeq := probe[start:end]
	if !strings.Contains(out, bgSeq) {
		t.Fatalf("selected row background = %q not found in overlay:\n%s", bgSeq, out)
	}
}

func TestPickerOverlayFooterHints(t *testing.T) {
	restoreDarkTheme(t)
	sections := buildOverlaySections(OverlayCommand, fixtureItems())
	state := OverlayState{Kind: OverlayCommand, Sections: sections, Footer: FooterNavigable}
	out := renderPickerOverlay(state, 80, 24)
	for _, want := range []string{"↑↓", "Enter", "Esc", "导航", "选择", "关闭"} {
		if !strings.Contains(out, want) {
			t.Fatalf("footer missing %q:\n%s", want, out)
		}
	}

	confirm := OverlayState{Kind: OverlayConfirm, Sections: buildOverlaySections(OverlayConfirm, []PickerItem{
		{Title: "清空", Command: "/clear yes"}, {Title: "取消", Command: "/clear no"},
	}), Footer: FooterConfirm}
	confirmOut := renderPickerOverlay(confirm, 80, 24)
	for _, want := range []string{"Enter", "Esc", "确认", "返回"} {
		if !strings.Contains(confirmOut, want) {
			t.Fatalf("confirm footer missing %q:\n%s", want, confirmOut)
		}
	}
	if strings.Contains(confirmOut, "导航") {
		t.Fatalf("confirm footer should not offer navigation:\n%s", confirmOut)
	}
}

func TestPickerOverlayDescRendersFaintSecondLine(t *testing.T) {
	restoreDarkTheme(t)
	sections := buildOverlaySections(OverlayCommand, fixtureItems())
	state := OverlayState{Kind: OverlayCommand, Sections: sections, Footer: FooterNavigable}
	out := renderPickerOverlay(state, 80, 24)
	if !strings.Contains(out, stFaint.Render("    播放可验证证据流")) {
		t.Fatalf("overlay missing faint desc second line:\n%s", out)
	}
}

func TestPickerOverlayFitsWidthOnResize(t *testing.T) {
	restoreDarkTheme(t)
	sections := buildOverlaySections(OverlayCommand, fixtureItems())
	for _, w := range []int{80, 60, 40, 24} {
		out := renderPickerOverlay(OverlayState{Kind: OverlayCommand, Selection: 1, Sections: sections, Footer: FooterNavigable}, w, 24)
		for i, ln := range strings.Split(out, "\n") {
			if got := lipgloss.Width(ln); got > w {
				t.Fatalf("width=%d line %d display width %d > %d:\n%q", w, i, got, w, ln)
			}
		}
		if got := lipgloss.Width(out); got != w {
			t.Fatalf("width=%d overlay width = %d, want exactly %d:\n%s", w, got, w, out)
		}
	}
}

func TestPickerOverlayLongFieldsStayInBounds(t *testing.T) {
	restoreDarkTheme(t)
	longTitle := strings.Repeat("非常长的条目标题", 8)
	longDesc := strings.Repeat("非常长的描述文本", 16)
	sections := buildOverlaySections(OverlayTools, []PickerItem{
		{Title: longTitle, Desc: longDesc, Shortcut: "long-shortcut-name", Category: "工具"},
	})
	out := renderPickerOverlay(OverlayState{Kind: OverlayTools, Sections: sections, Footer: FooterNavigable}, 80, 24)
	for i, ln := range strings.Split(out, "\n") {
		if got := lipgloss.Width(ln); got > 80 {
			t.Fatalf("long-field line %d display width %d > 80:\n%q", i, got, ln)
		}
	}
	if !strings.Contains(out, "…") {
		t.Fatalf("long fields should be truncated with ellipsis:\n%s", out)
	}
}

func TestPickerOverlayScrollsWindowToSelection(t *testing.T) {
	restoreDarkTheme(t)
	items := make([]PickerItem, 40)
	for i := range items {
		items[i] = PickerItem{Title: "条目", Desc: "", Shortcut: "/item", Category: "列表"}
	}
	sections := buildOverlaySections(OverlaySessions, items)
	state := OverlayState{Kind: OverlaySessions, Selection: 39, Sections: sections, Footer: FooterNavigable}
	out := renderPickerOverlay(state, 80, 12)
	// 总高 = chrome 9 + 可见窗口 3；选中行必须滚入窗口（❯ 可见）。
	if got := strings.Count(out, "\n") + 1; got != 12 {
		t.Fatalf("overlay height = %d lines, want 12:\n%s", got, out)
	}
	if !strings.Contains(out, "❯") {
		t.Fatalf("selection at tail should scroll into view:\n%s", out)
	}
}

func TestPickerOverlayEmptySectionsShowsHint(t *testing.T) {
	restoreDarkTheme(t)
	out := renderPickerOverlay(OverlayState{Kind: OverlayCommand, Footer: FooterNavigable}, 80, 24)
	if !strings.Contains(out, "没有匹配项") {
		t.Fatalf("empty overlay missing hint:\n%s", out)
	}
	if strings.Contains(out, "❯") {
		t.Fatalf("empty overlay should not carry a marker:\n%s", out)
	}
}

func TestOverlayEscBehaviorHierarchy(t *testing.T) {
	parent := OverlayState{Kind: OverlayCommand}
	child := OverlayState{Kind: OverlayTheme, Parent: &parent}

	// 子 picker → 父 picker。
	if got := escBehavior(child); got != EscPop {
		t.Fatalf("escBehavior(child) = %v, want EscPop", got)
	}
	// 父 picker → close。
	if got := escBehavior(parent); got != EscClose {
		t.Fatalf("escBehavior(parent) = %v, want EscClose", got)
	}
	// 顶层（无父）直接 close。
	if got := escBehavior(OverlayState{}); got != EscClose {
		t.Fatalf("escBehavior(top-level) = %v, want EscClose", got)
	}
	// 三层链：grandchild → child → parent → close，每层语义一致。
	grandchild := OverlayState{Kind: OverlayTools, Parent: &child}
	if got := escBehavior(grandchild); got != EscPop {
		t.Fatalf("escBehavior(grandchild) = %v, want EscPop", got)
	}
}

func TestOverlayKindTitlesCoverAllCarriers(t *testing.T) {
	titles := map[OverlayKind]string{
		OverlayCommand:  "命令启动器",
		OverlayTheme:    "选择主题",
		OverlaySessions: "恢复会话",
		OverlayTools:    "选择工具",
		OverlayDoctor:   "查看检查项",
		OverlayConfirm:  "确认操作",
	}
	for kind, want := range titles {
		if got := overlayKindTitle(kind); got != want {
			t.Fatalf("overlayKindTitle(%s) = %q, want %q", kind, got, want)
		}
	}
}

func TestOverlaySourceHasNoRawHexColors(t *testing.T) {
	src, err := os.ReadFile("view_overlay.go")
	if err != nil {
		t.Fatalf("read view_overlay.go: %v", err)
	}
	// 颜色纪律（T05-01 / T05-08）：渲染代码不得出现散落 hex，一律走 theme token。
	if re := regexp.MustCompile(`#[0-9A-Fa-f]{3,8}`); re.Match(src) {
		t.Fatalf("view_overlay.go contains raw hex colors:\n%s", re.FindAllString(string(src), -1))
	}
}
