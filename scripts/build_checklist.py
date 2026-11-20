"""从各分册的「知识点清单」汇总出一份总清单 Markdown（按分册、章分组），并统计星级分布。

用法: python build_checklist.py <分册目录> <输出.md>
输出可直接粘进 00_总览 文件，或单独保存。
"""
import glob, os, re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
d, outp = sys.argv[1], sys.argv[2]
out, total, stars = [], 0, {3: 0, 2: 0, 1: 0}
for f in sorted(glob.glob(os.path.join(d, "[0-9][0-9]_*.md"))):
    name = os.path.basename(f)
    lines = open(f, encoding="utf-8").read().splitlines()
    if not any(l.startswith("### 知识点清单") for l in lines):
        continue
    title = next((l[2:] for l in lines if l.startswith("# ")), name)
    out.append(f"\n### [{title}]({name})\n")
    chap, inlist = None, False
    for l in lines:
        if l.startswith("## "):
            chap, inlist = l[3:].strip(), False
        elif l.startswith("### "):
            inlist = l.startswith("### 知识点清单")
            if inlist and chap:
                out.append(f"\n**{chap}**\n")
        elif inlist and l.startswith("- [ ]"):
            out.append(l)
            total += 1
            m = re.search(r"(★+)", l)
            if m:
                stars[min(len(m.group(1)), 3)] += 1
open(outp, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"共 {total} 个知识点：★★★ {stars[3]}，★★ {stars[2]}，★ {stars[1]} -> {outp}")
