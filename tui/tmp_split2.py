import re

main_lines = open("main.go").read().split("\n")
render_lines = open("render.go").read().split("\n")

def decl_index(lines):
    idx = {}
    for i, l in enumerate(lines):
        m = re.match(r"^(func|type|var|const) ", l)
        if m:
            if m.group(1) == "func":
                m2 = re.match(r"^func (?:\([^)]*\) )?([A-Za-z_][A-Za-z0-9_]*)", l)
                if m2:
                    idx[m2.group(1)] = i + 1
            elif not l.rstrip().endswith("("):
                idx[l.split()[1]] = i + 1
    return idx

mi = decl_index(main_lines)
ri = decl_index(render_lines)

main_targets = ["metaDetail", "metaEmpty", "nodeLabel", "eventPhase", "metaPhase",
                "streamKindLabel", "kaomojiForState", "renderWorkflowStatus",
                "appendUniqueNode", "renderStreamRail", "renderThinkingShelf", "panelRow"]
render_targets = ["durationText", "permissionNotice", "toolResultLabel", "timelineMarkdownBody",
                  "renderTimelineMarkdown", "renderTimelineBlock", "renderPlanBlock",
                  "renderToolCallBlock", "renderReflectBlock"]

def ranges_of(lines, idx, targets):
    decls = sorted(ln for ln in idx.values())
    out = []
    for t in targets:
        s = idx[t]
        e = None
        for ln in decls:
            if ln > s:
                e = ln - 1
                break
        out.append((s, e or len(lines)))
    return out

m_ranges = ranges_of(main_lines, mi, main_targets)
r_ranges = ranges_of(render_lines, ri, render_targets)

body_parts = []
for (s, e) in m_ranges:
    body_parts.extend(main_lines[s - 1:e])
body_parts.append("// ---- 以下从 render.go 搬移 ----")
for (s, e) in r_ranges:
    body_parts.extend(render_lines[s - 1:e])
body = "\n".join(body_parts)

needs = []
pairs = [
    (r"lipgloss\.", '"github.com/charmbracelet/lipgloss"'),
    (r"strings\.", '"strings"'),
    (r"fmt\.", '"fmt"'),
    (r"time\.", '"time"'),
    (r"sort\.", '"sort"'),
    (r"rand\.", '"math/rand"'),
]
for pat, imp in pairs:
    if re.search(pat, body):
        needs.append(imp)

header = """// view_trace.go — T05-10 文件职责收敛：科研轨迹/工作流渲染（单一视觉职责）。
//
// 从 main.go / render.go 搬移（行为零变化，纯文件拆分）：
//   - workflow 状态：renderWorkflowStatus / streamKindLabel / kaomojiForState
//   - 轨迹块：renderTimelineBlock / renderPlanBlock / renderToolCallBlock / renderReflectBlock
//   - 工具结果标签：toolResultLabel / permissionNotice / durationText
//   - 内部线语法：panelRow
package main

import (
%s
)
""" % "\n".join("\t" + n for n in sorted(set(needs)))

open("view_trace.go", "w").write(header + "\n" + body + "\n")

mk = [i for i in range(len(main_lines)) if not any(s - 1 <= i <= e - 1 for s, e in m_ranges)]
rk = [i for i in range(len(render_lines)) if not any(s - 1 <= i <= e - 1 for s, e in r_ranges)]
open("main.go", "w").write("\n".join(main_lines[i] for i in mk))
open("render.go", "w").write("\n".join(render_lines[i] for i in rk))
print("view_trace.go written")
