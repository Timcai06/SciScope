// view_welcome_test.go — T05-03 沉浸式 Welcome 的单元测试。
//
// 覆盖计划 5.2/5.4 与 T05-03 验收：
//   - 80/120/160 三宽度：SciScope、命令提示（/verify /review /trend）、
//     recent 会话标题齐全，且无三栏 Dashboard 特征字符串；
//   - <60 列回落纯文本 SciScope，无 ASCII 艺术断行；
//   - 每条可见行 rune 显示宽度 ≤ width（lipgloss.Width，中文算 2 列）；
//   - hosted/local 状态只由真实派生/调用方快照表达，不伪造连通性；
//   - view_welcome.go 源文件不含散落 hex 颜色。

package main

import (
	"fmt"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/lipgloss"
)

// welcomeSessionsFixture 两条最近会话，覆盖「有问题文本」与时间戳展示。
func welcomeSessionsFixture() []sessionFile {
	return []sessionFile{
		{
			Index:        1,
			Name:         "sciscope-session-20260625-130000.md",
			LastQuestion: "核查 RAG 是否降低幻觉",
			ModTime:      time.Date(2026, 6, 25, 13, 0, 0, 0, time.Local),
			Size:         2048,
		},
		{
			Index:        2,
			Name:         "sciscope-session-20260624-100000.md",
			LastQuestion: "梳理 2025 年知识图谱趋势",
			ModTime:      time.Date(2026, 6, 24, 10, 0, 0, 0, time.Local),
			Size:         1024,
		},
	}
}

// assertWelcomeFits 断言输出每一行的显示宽度都不超过 width（ANSI 不计宽，
// 中文按 2 列计，由 lipgloss.Width 处理）。
func assertWelcomeFits(t *testing.T, out string, width int) {
	t.Helper()
	lines := strings.Split(out, "\n")
	if len(lines) == 0 {
		t.Fatalf("welcome rendered no lines")
	}
	for i, line := range lines {
		if w := lipgloss.Width(line); w > width {
			t.Fatalf("line %d overflows width %d by %d columns: %q", i, width, w-width, line)
		}
	}
}

func TestWelcomeRendersAtThreeWidths(t *testing.T) {
	sessions := welcomeSessionsFixture()
	for _, width := range []int{80, 120, 160} {
		t.Run(fmt.Sprintf("width-%d", width), func(t *testing.T) {
			out := renderWelcome(width, sessions, nil)

			for _, want := range []string{
				"SciScope",
				"/verify",
				"/review",
				"/trend",
				"/demo",
				"核查 RAG 是否降低幻觉",
				"06-25 13:00",
			} {
				if !strings.Contains(out, want) {
					t.Fatalf("width %d: welcome missing %q:\n%s", width, want, out)
				}
			}
			for _, banned := range []string{"Quick Actions", "System Status", "Golden Demo"} {
				if strings.Contains(out, banned) {
					t.Fatalf("width %d: dashboard text %q leaked into welcome:\n%s", width, banned, out)
				}
			}
			assertWelcomeFits(t, out, width)
		})
	}
}

func TestWelcomeBrandTiers(t *testing.T) {
	full := welcomeBrand(160)
	if !strings.Contains(full, "███████╗") {
		t.Fatalf("wide brand should use the full six-line logo:\n%s", full)
	}

	compact := welcomeBrand(80)
	if !strings.Contains(compact, "█████") {
		t.Fatalf("60-85 cols brand should use the compact wordmark:\n%s", compact)
	}
	if strings.Contains(compact, "██╔════╝") {
		t.Fatalf("80 cols must not fall back to the full logo:\n%s", compact)
	}
	if !strings.Contains(compact, "SciScope") {
		t.Fatalf("compact wordmark must keep the SciScope name:\n%s", compact)
	}
	assertWelcomeFits(t, compact, 80)

	plain := welcomeBrand(40)
	if !strings.Contains(plain, "SciScope") {
		t.Fatalf("narrow brand should render the plain SciScope text:\n%s", plain)
	}
	if strings.Contains(plain, "█") {
		t.Fatalf("narrow brand must not render ASCII art:\n%s", plain)
	}
	assertWelcomeFits(t, plain, 40)
}

func TestWelcomeNarrowFallbackIsPlainText(t *testing.T) {
	for _, width := range []int{40, 24} {
		t.Run(fmt.Sprintf("width-%d", width), func(t *testing.T) {
			out := renderWelcome(width, nil, nil)
			if !strings.Contains(out, "SciScope") {
				t.Fatalf("narrow welcome missing SciScope:\n%s", out)
			}
			if strings.Contains(out, "█") {
				t.Fatalf("narrow welcome must not render ASCII art lines:\n%s", out)
			}
			assertWelcomeFits(t, out, width)
		})
	}
}

func TestWelcomeEmptyRecentKeepsDemoDiscoverable(t *testing.T) {
	out := renderWelcome(100, nil, nil)
	for _, want := range []string{"/demo", "暂无本地会话"} {
		if !strings.Contains(out, want) {
			t.Fatalf("empty-recent welcome missing %q:\n%s", want, out)
		}
	}
	assertWelcomeFits(t, out, 100)
}

func TestWelcomeBackendLineIsHonest(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "https://api.sciscope.test")
	out := renderWelcome(120, nil, nil)
	if !strings.Contains(out, "backend hosted") {
		t.Fatalf("welcome should report the real derived mode:\n%s", out)
	}
	if !strings.Contains(out, "/doctor") {
		t.Fatalf("welcome should point status checks at /doctor:\n%s", out)
	}
	for _, fake := range []string{"connected", "ready", "healthy"} {
		if strings.Contains(out, fake) {
			t.Fatalf("welcome must not fabricate %q status:\n%s", fake, out)
		}
	}
	assertWelcomeFits(t, out, 120)

	t.Setenv("SCISCOPE_BACKEND", "http://127.0.0.1:8000")
	if out := renderWelcome(120, nil, nil); !strings.Contains(out, "backend local") {
		t.Fatalf("welcome should report local mode from the URL:\n%s", out)
	}
}

func TestWelcomeHostsSnapshotReportedVerbatim(t *testing.T) {
	hosts := map[string]bool{
		"localhost:8000":    true,
		"api.sciscope.test": false,
	}
	out := renderWelcome(120, nil, hosts)
	plain := plainANSI(out)
	if !strings.Contains(plain, "api.sciscope.test unreachable") {
		t.Fatalf("welcome should report the given unreachable host:\n%s", out)
	}
	if !strings.Contains(plain, "localhost:8000 ok") {
		t.Fatalf("welcome should report the given reachable host:\n%s", out)
	}
	// 输出必须确定性：host 名排序。
	if strings.Index(plain, "api.sciscope.test") > strings.Index(plain, "localhost:8000") {
		t.Fatalf("host lines should be deterministically sorted:\n%s", out)
	}
	assertWelcomeFits(t, out, 120)
}

// TestWelcomeSourceHasNoScatteredHex 保证颜色纪律落地：实现文件不引用散落 hex，
// 一律走 theme.go 的语义样式（测试本身允许含 hex 模式）。
func TestWelcomeSourceHasNoScatteredHex(t *testing.T) {
	src, err := os.ReadFile("view_welcome.go")
	if err != nil {
		t.Fatalf("read view_welcome.go: %v", err)
	}
	re := regexp.MustCompile(`#[0-9a-fA-F]{6}`)
	if re.Match(src) {
		t.Fatalf("view_welcome.go must not contain scattered hex colors, found %q",
			re.FindString(string(src)))
	}
}
