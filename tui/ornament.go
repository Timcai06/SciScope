// ornament.go — T05-07 修订（项目负责人要求）：欢迎页 Logo 两侧装饰纹样。
//
// 参考桌面截图的对称菱形编织纹，用 Unicode Symbols for Legacy Computing 块的
// 六分块字符（sextant，U+1FB00–U+1FB3B）重绘。sextant 每字符承载 2 行 × 3 列
// 点阵（64 种组合），位布局按 Unicode 标准：
//
//	bit0  bit3
//	bit1  bit4
//	bit2  bit5
//
// 字符编码 = U+1FB00 + bits（bit n 对应二进制第 n-1 位）。
//
// 渲染手段开关（终端字体对 sextant 支持参差）：
//
//	SCISCOPE_TUI_ORNAMENT=sextant  默认：六分块菱形纹
//	SCISCOPE_TUI_ORNAMENT=block    降级：半块字符 ▀▄ 交错
//	SCISCOPE_TUI_ORNAMENT=off      关闭（纯 Logo，无装饰）
//
// 颜色纪律：主纹 Accent、副纹 Muted，全部走 theme token，不引用散落 hex。

package main

import (
	"os"
	"strings"
)

const (
	// sextantBlockBase Unicode 13.0 Symbols for Legacy Computing 六分块首字符。
	sextantBlockBase = 0x1FB00
	// ornamentWidth 单侧纹样条的字符列宽（每单元 3 列）。
	ornamentWidth = 12
	// ornamentRows 纹样条行数（6 行 Logo 中第 1–4 行两侧展示）。
	ornamentRows = 4
)

// ornamentMode 返回当前纹样渲染模式（sextant / block / off）。
//
// 默认 off：sextant 六分块字符（U+1FB00–U+1FB3B）在多数终端字体
// （macOS Terminal 默认字体等）中不支持，会渲染为乱码/豆腐块并破坏 Logo
// 两侧的纯黑画面（项目负责人真机反馈）。需要装饰时显式开启：
//
//	SCISCOPE_TUI_ORNAMENT=sextant  六分块菱形纹（需终端字体支持）
//	SCISCOPE_TUI_ORNAMENT=block    半块字符 ▀▄ 交错（兼容性较好）
func ornamentMode() string {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("SCISCOPE_TUI_ORNAMENT")))
	switch v {
	case "sextant":
		return "sextant"
	case "block":
		return "block"
	default:
		return "off"
	}
}

// sextant 由 6 位点阵生成六分块字符。bits 为 6 位掩码。
func sextant(bits int) string {
	return string(rune(sextantBlockBase + bits))
}

// sext 便捷别名：生成六分块字符。
func sext(bits int) string {
	return sextant(bits)
}

// reverseString 按 rune 反转（保持多字节字符完整）。
func reverseString(s string) string {
	runes := []rune(s)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes)
}

// 菱形单元（每字符 1 列 × 2 行点阵，3 列点阵内取中心列与全宽）：
//
//	可见形态：
//	  字符行0（菱上）: .X. / XXX   → 位4 + 位2,5,6 → bits 0b111010 = 58
//	  字符行1（菱下）: XXX / .X.   → 位1,4,3 + 位5  → bits 0b011101 = 29
//	  空心菱上      : .X. / X.X   → 位4 + 位2,6    → bits 0b100011 = 35
//	  空心菱下      : X.X / .X.   → 位1,3 + 位5    → bits 0b010101 = 21
//
// 连续菱形链（实心 ◆ 与空心 ◇ 逐列交替）构成编织纹样。
const (
	sextDiamondTop          = 58
	sextDiamondBottom       = 29
	sextDiamondHollow       = 35
	sextDiamondHollowBottom = 21
)

// ornamentCells 返回单侧纹样条的单元矩阵（4 行 × ornamentWidth 列）。
// 实心菱形（◆）与空心菱形（◇）逐列交替；行 2/3 与行 0/1 相位相反形成编织链。
func ornamentCells() [][]string {
	const cells = ornamentWidth
	rows := make([][]string, ornamentRows)
	for i := range rows {
		rows[i] = make([]string, cells)
	}
	for c := 0; c < cells; c++ {
		solid := c%2 == 0 // 实心单元
		var a, b string
		if solid {
			a, b = sext(sextDiamondTop), sext(sextDiamondBottom)
		} else {
			a, b = sext(sextDiamondHollow), sext(sextDiamondHollowBottom)
		}
		rows[0][c], rows[1][c] = a, b
		rows[2][c], rows[3][c] = b, a
	}
	return rows
}

// ornamentLines 渲染单侧纹样条（4 行字符串，含样式）。
func ornamentLines() []string {
	rows := ornamentCells()
	lines := make([]string, ornamentRows)
	for i := range rows {
		// 偶数行实心为主（Accent 主导），奇数行 Muted 主导制造编织层次。
		st := stAccent
		if i == 2 || i == 3 {
			st = stMuted
		}
		lines[i] = st.Render(strings.Join(rows[i], ""))
	}
	return lines
}

// ornamentBlockLines 半块字符降级版（Terminal.app 等不支持 sextant 时）：
// ▀▄ 交错模拟菱形链。
func ornamentBlockLines() []string {
	return []string{
		stAccent.Render("▀▄▀▄▀▄▀▄▀▄▀▄"),
		stMuted.Render("▀▄▀▄▀▄▀▄▀▄▀▄"),
		stMuted.Render("▄▀▄▀▄▀▄▀▄▀▄▀"),
		stAccent.Render("▄▀▄▀▄▀▄▀▄▀▄▀"),
	}
}

// ornamentLinesForMode 按渲染模式返回单侧纹样条；off 返回 nil。
func ornamentLinesForMode() []string {
	switch ornamentMode() {
	case "off":
		return nil
	case "block":
		return ornamentBlockLines()
	default:
		return ornamentLines()
	}
}

// ornamentBlankLine 与纹样条等宽的空白行（用于 Logo 第 0/5 行的两侧留白，
// 保持 Logo 块整体宽度一致以便居中计算）。
func ornamentBlankLine() string {
	return strings.Repeat(" ", ornamentWidth)
}

// mirrorOrnamentLine 水平镜像单侧纹样行：提取「样式前缀 + 核心字符 + 后缀」，
// 反转核心字符顺序（菱形单元自身左右对称，反转顺序即可）。样式包裹整体保留。
func mirrorOrnamentLine(line string) string {
	plain := stripANSI(line)
	if plain == "" {
		return line
	}
	core := reverseString(plain)
	// 重建：取原行的样式序列（去掉核心字符）。stripANSI 后的长度按 rune 计，
	// 因此用 rune 数在「去 ANSI 的行」上定位核心，再与原行前缀拼接。
	prefix := ansiPrefixOf(line, plain)
	suffix := ""
	if strings.HasSuffix(line, "\x1b[0m") {
		suffix = "\x1b[0m"
	}
	return prefix + core + suffix
}

// ansiPrefixOf 返回 line 中核心文本之前的所有字节（ANSI 样式序列）。
func ansiPrefixOf(line, plain string) string {
	// 用 plain 的首字符在 line 中定位：跳过 ANSI 序列找第一个可见字符。
	first := []rune(plain)[0]
	idx := strings.IndexRune(line, first)
	// 若首字符之前有非 ANSI 字节（理论不存在），退回简单前缀 0。
	if idx < 0 {
		return ""
	}
	return line[:idx]
}
