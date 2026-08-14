// scrollback.go — T05-02 typed scrollback 状态层。
//
// 核心原则（T05 计划 T05-02）：
//
//	transcript 是持久/导出事实；scrollback block 是 UI 投影；
//	两者不得互相成为第二事实源。
//
// 本文件提供 typed block 模型（BlockKind / BlockStatus / ScrollbackBlock）与
// 状态机（running→finished、fold/unfold、渲染缓存失效），使后续 T05-04/05/06
// 不再靠解析 ANSI/标题文本判断块类型。
//
// 渲染语法迁移（无框 block grammar）属 T05-04 范围；T05-02 只建立状态 seam，
// 保持现有渲染行为等价。

package main

import (
	"regexp"
	"sync/atomic"
	"time"
)

// BlockKind 是 scrollback 块的类型身份。至少表达计划 T05-02 要求：
// user / research_plan / tool_group / tool_result / research_trace / evidence /
// answer / contract / recovery / system。
type BlockKind string

const (
	BlockMessage       BlockKind = "message"        // 未归类兜底（旧 appendBlock 语义）
	BlockUser          BlockKind = "user"           // 用户问题
	BlockResearchPlan  BlockKind = "research_plan"  // 研究计划
	BlockToolCall      BlockKind = "tool_call"      // 工具调用
	BlockToolResult    BlockKind = "tool_result"    // 工具结果（含 Evidence 卡）
	BlockResearchTrace BlockKind = "research_trace" // 研究轨迹（自检修正、/timeline）
	BlockEvidence      BlockKind = "evidence"       // 独立 Evidence 卡（T05-06 启用）
	BlockAnswer        BlockKind = "answer"         // 助手最终回答
	BlockContract      BlockKind = "contract"       // answer-contract sidecar
	BlockRecovery      BlockKind = "recovery"       // 错误恢复/阻断面板
	BlockSystem        BlockKind = "system"         // 系统提示（会话保存、命令反馈等）
)

// BlockStatus 是块的生命周期状态。finished 块可缓存；running 块随 streaming
// 更新同一实例而非无限 append（计划 T05-02「必须证明」）。
type BlockStatus string

const (
	BlockRunning  BlockStatus = "running"
	BlockFinished BlockStatus = "finished"
)

// ScrollbackBlock 是 UI 投影单元。Raw 保存源文本（含现有 ANSI 渲染字符串，
// 渲染语法迁移属 T05-04），Rendered 是宽度相关的渲染缓存。
type ScrollbackBlock struct {
	ID            string      // 单调递增块身份
	Kind          BlockKind   // 类型身份（不再靠解析标题文本判断）
	Status        BlockStatus // running / finished
	Expanded      bool        // 折叠投影态（fold/unfold 不修改 transcript）
	Pinned        bool        // 用户手动折叠/展开过：自动折叠不覆盖（display_mode_pinned 语义）
	StartedAt     time.Time   // 块创建时间
	EndedAt       time.Time   // finished 时间（running 时为零值）
	Raw           string      // 源文本
	Retry         bool        // user 块的 retry 标记
	Tools         []string    // answer 块使用的工具列表
	Rendered      string      // 渲染缓存（宽度/主题相关）
	RenderWidth   int
	RenderVersion int
}

var scrollbackIDSeq atomic.Int64

// nextBlockID 生成单调递增的块 ID。
func nextBlockID() string {
	return "b" + itoa(scrollbackIDSeq.Add(1))
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}

// newScrollbackBlock 构造 finished 块（append 语义）。
func newScrollbackBlock(kind BlockKind, raw string) ScrollbackBlock {
	now := time.Now()
	return ScrollbackBlock{
		ID:        nextBlockID(),
		Kind:      kind,
		Status:    BlockFinished,
		Expanded:  true,
		StartedAt: now,
		EndedAt:   now,
		Raw:       raw,
	}
}

// startRunningBlock 创建 running 块并返回其 ID。streaming 期间对同一 ID 调用
// updateRunningBlock 更新内容，而非每 chunk append 一个新块（计划 T05-02）。
// 块同步写入 blocks（事实行），保持 syncBlockItems 的对齐不变量。
func (m *model) startRunningBlock(kind BlockKind) string {
	b := ScrollbackBlock{
		ID:        nextBlockID(),
		Kind:      kind,
		Status:    BlockRunning,
		Expanded:  true, // running 块默认展开
		StartedAt: time.Now(),
	}
	m.blocks = append(m.blocks, b.Raw)
	m.blockItems = append(m.blockItems, b)
	m.blocksVersion++
	m.refresh()
	return b.ID
}

// updateRunningBlock 更新 running 块的源文本并失效其渲染缓存。
// 若 ID 不存在或无块处于该 ID 的 running 状态，返回 false。
func (m *model) updateRunningBlock(id, raw string) bool {
	for i := range m.blockItems {
		b := &m.blockItems[i]
		if b.ID == id {
			if b.Status != BlockRunning {
				return false
			}
			if b.Raw != raw {
				b.Raw = raw
				if i < len(m.blocks) {
					m.blocks[i] = raw // 事实行同步，保持 blocks/blockItems 对齐
				}
				b.Rendered = ""
				b.RenderWidth = 0
				b.RenderVersion++
				m.blocksVersion++
				m.refresh()
			}
			return true
		}
	}
	return false
}

// finishRunningBlock 把 running 块标记为 finished（记录 EndedAt），使其可缓存。
func (m *model) finishRunningBlock(id string) bool {
	for i := range m.blockItems {
		b := &m.blockItems[i]
		if b.ID == id {
			if b.Status != BlockRunning {
				return false
			}
			b.Status = BlockFinished
			b.EndedAt = time.Now()
			m.blocksVersion++
			m.refresh()
			return true
		}
	}
	return false
}

// setBlockContent 更新块的源文本与工具列表（running 块转正、theme 切换重渲染等），
// 同步 blocks 事实行并失效该块渲染缓存。
func (m *model) setBlockContent(id, raw string, tools []string) bool {
	for i := range m.blockItems {
		b := &m.blockItems[i]
		if b.ID == id {
			if b.Raw != raw {
				b.Raw = raw
				if i < len(m.blocks) {
					m.blocks[i] = raw
				}
				b.Rendered = ""
				b.RenderWidth = 0
				b.RenderVersion++
				m.blocksVersion++
			}
			if tools != nil {
				b.Tools = append([]string(nil), tools...)
			}
			m.refresh()
			return true
		}
	}
	return false
}

// runningBlock 返回指定 ID 的块（不存在返回 nil）。
func (m *model) runningBlock(id string) *ScrollbackBlock {
	for i := range m.blockItems {
		if m.blockItems[i].ID == id {
			return &m.blockItems[i]
		}
	}
	return nil
}

// setExpanded 折叠/展开投影态。只改 UI 投影，不修改 blocks/transcript 事实
// （计划 T05-02「必须证明 fold/unfold 不修改 transcript」）。手动操作设置
// Pinned，使后续自动折叠不覆盖用户选择（计划 T05-05）。
func (m *model) setExpanded(id string, expanded bool) bool {
	for i := range m.blockItems {
		b := &m.blockItems[i]
		if b.ID == id {
			if b.Expanded != expanded {
				b.Expanded = expanded
				b.Pinned = true
				m.blocksVersion++
				m.refresh()
			}
			return true
		}
	}
	return false
}

// autoFoldTraces T05-05：turn 结束时把未 Pinned 的 finished 轨迹块（研究计划/
// 自检修正）默认折叠为一行，让首屏优先看到结论而非 workflow engine。
func (m *model) autoFoldTraces() {
	changed := false
	for i := range m.blockItems {
		b := &m.blockItems[i]
		if (b.Kind == BlockResearchPlan || b.Kind == BlockResearchTrace || b.Kind == BlockEvidence) &&
			b.Status == BlockFinished && !b.Pinned && b.Expanded {
			b.Expanded = false
			changed = true
		}
	}
	if changed {
		m.blocksVersion++
	}
}

// toggleLatestTrace T05-05：Enter（输入为空时）切换最后一个可折叠轨迹块。
func (m *model) toggleLatestTrace() bool {
	for i := len(m.blockItems) - 1; i >= 0; i-- {
		b := &m.blockItems[i]
		if (b.Kind == BlockResearchPlan || b.Kind == BlockResearchTrace || b.Kind == BlockEvidence) && b.Status == BlockFinished {
			b.Expanded = !b.Expanded
			b.Pinned = true
			m.blocksVersion++
			m.refresh()
			return true
		}
	}
	return false
}

// invalidateRenderCache 清空全部块的渲染缓存（主题切换等全局失效场景）。
func (m *model) invalidateRenderCache() {
	for i := range m.blockItems {
		m.blockItems[i].Rendered = ""
		m.blockItems[i].RenderWidth = 0
	}
	m.transcriptCache = ""
	m.transcriptCacheWidth = 0
	m.transcriptCacheBlockVersion = -1
	m.blocksVersion++
}

// invalidateRenderCacheForWidth 宽度变化时只失效宽度不匹配的块缓存。
// 现有 renderBlocksContent 本身逐块比较 RenderWidth（lazy 失效）；本方法用于
// 测试与后续 T05-09 resize 纪律的显式入口。
func (m *model) invalidateRenderCacheForWidth(newWidth int) {
	changed := false
	for i := range m.blockItems {
		b := &m.blockItems[i]
		if b.RenderWidth != 0 && b.RenderWidth != newWidth {
			b.Rendered = ""
			b.RenderWidth = 0
			changed = true
		}
	}
	if changed {
		m.transcriptCache = ""
		m.transcriptCacheWidth = 0
		m.transcriptCacheBlockVersion = -1
		m.blocksVersion++
	}
}

// finishedBlocks 返回已 finished 的块（供缓存/导出投影审计）。
func (m *model) finishedBlocks() []ScrollbackBlock {
	out := make([]ScrollbackBlock, 0, len(m.blockItems))
	for _, b := range m.blockItems {
		if b.Status == BlockFinished {
			out = append(out, b)
		}
	}
	return out
}

// blockByKind 返回指定类型的全部块（供 T05-04/05/06 迁移与测试）。
func (m *model) blockByKind(kind BlockKind) []ScrollbackBlock {
	out := make([]ScrollbackBlock, 0)
	for _, b := range m.blockItems {
		if b.Kind == kind {
			out = append(out, b)
		}
	}
	return out
}

// literalSGRResidueRe 匹配无 ESC 前缀的字面 SGR 残骸（[0m、[38;5;252m 等）。
// 前缀用捕获组保留（RE2 不支持 lookbehind）。
var literalSGRResidueRe = regexp.MustCompile(`(^|[^\x1b])\[\d+(?:;\d+)*m`)

// stripLiteralSGRResidue 清洗 LLM 输出中的字面 ANSI 残骸：训练数据含终端日志，
// LLM 有时输出脱掉 ESC 的序列文本（[0m[38;5;252m），终端会原样显示成乱码。
// 只匹配数字参数形态（[0m / [38;5;252m），不会误伤 markdown 链接与列表语法。
// 连续残骸（[0m[38;5;252m）需循环替换：前一个序列的结束字符被消费后，
// 后一个序列才会在下一轮暴露为串首。
func stripLiteralSGRResidue(s string) string {
	for {
		next := literalSGRResidueRe.ReplaceAllString(s, "$1")
		if next == s {
			return next
		}
		s = next
	}
}
