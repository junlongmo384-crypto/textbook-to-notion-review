"""检查复习分册是否符合约定格式，并统计知识点 / 题目数量。

用法: python lint_volumes.py <分册目录>
分册文件命名 NN_标题.md（NN 两位数字；00_ 是总览，不检查）。导言/附录/符号对照类章节不要求四个小节。每个 "## 章" 下应有：
  ### 知识点清单（- [ ] ★★★ 点（p页码））/ ### 核心内容 / ### 易错点 / ### 典型题…
每道题以 **N.（题型）** 或 **题N…** 开头，并有一行以 "答案" 开头。
只有一个 "#" 标题、没有 "## " 章的分册（如公式速查）跳过章节检查。
"""
import glob, os, re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REQ = ["知识点清单", "核心内容", "易错点", "典型题"]
Q = re.compile(r"^\*\*(题)?\s*\d")
A = re.compile(r"^\s*(- )?\**答案")
ITEM = re.compile(r"^- \[ \] (★{1,3})\s*(.*)$")
INTRO = re.compile(r"^(导言|附[：:])|符号对照|使用说明")
PAGE = re.compile(r"[（(]\s*p\s?\d")

d = sys.argv[1]
grand = dict(items=0, qs=0, problems=0)
for f in sorted([x for x in glob.glob(os.path.join(d, "[0-9][0-9]_*.md")) if not os.path.basename(x).startswith("00")]):
    lines = open(f, encoding="utf-8").read().splitlines()
    chaps = [i for i, l in enumerate(lines) if l.startswith("## ")]
    name = os.path.basename(f)
    if not chaps:
        print(f"{name}: 无章节（单页分册），跳过结构检查")
        continue
    issues, items, qs, noans, nopage = [], 0, 0, 0, 0
    for c, s in enumerate(chaps):
        e = chaps[c + 1] if c + 1 < len(chaps) else len(lines)
        body = lines[s + 1:e]
        title = lines[s][3:].strip()
        subs = [l[4:] for l in body if l.startswith("### ")]
        miss = [r for r in REQ if not any(x.startswith(r) for x in subs)]
        if miss and not INTRO.search(title):
            issues.append(f"  [{title[:30]}] 缺少小节: {'、'.join(miss)}")
        for l in body:
            m = ITEM.match(l)
            if m:
                items += 1
                if not PAGE.search(m.group(2)):
                    nopage += 1
        # 题目与答案配对：只看「典型题」小节（核心内容里的 **1. 小标题** 不算题）
        cur, inprob, probs = None, False, []
        for l in body:
            if l.startswith("### "):
                inprob = "典型题" in l
            elif inprob:
                probs.append(l)
        for l in probs + ["**0"]:
            if Q.match(l):
                if cur is not None and not cur:
                    noans += 1
                cur = False
                qs += 1
            elif cur is False and A.match(l):
                cur = True
        qs -= 1  # 去掉哨兵
    print(f"{name}: {len(chaps)} 章, 知识点 {items}（无页码 {nopage}）, 题目 {qs}（缺答案 {noans}）")
    for i in issues:
        print(i)
    grand["items"] += items
    grand["qs"] += qs
    grand["problems"] += len(issues) + noans
print(f"\n合计 知识点 {grand['items']}，题目 {grand['qs']}，结构问题 {grand['problems']}")
