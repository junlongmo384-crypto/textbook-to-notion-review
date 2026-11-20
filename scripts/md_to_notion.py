"""把复习分册（NN_标题.md）转换成可直接交给 Notion MCP 的页面内容，并生成知识点数据库的行数据。

用法:
  python md_to_notion.py <分册目录> <输出目录> [--split-chars 10000]
        [--intro-regex "^(导言|附：)|符号对照"] [--single 09]
        [--vol-label "01=01 半导体物理·刘恩科1–5" ...]

输出（都在 <输出目录>）:
  vNN_page.md          分册页正文（册首说明 + 导言/附录类章节 + 本册章节说明）
  vNN_cMM.md           每章子页面正文；超过 --split-chars 时拆成 vNN_cMM_a.md / _b.md …
  plan.json            上传计划：分册标题、页面文件、各章标题与分段文件、答案折叠数
  db_rows_K.json       知识点数据库行，每批 90 行（notion-create-pages 一次的安全量）
  db_schema.sql        notion-create-database 用的 schema（分册选项已按实际分册填好）

转换规则（都是踩过坑后的做法）:
  - 标题整体上移一级：分册里的 "### 小节" 在章页面里变成 "## 小节"。
  - "典型题" 小节中每道题的答案（从以 "答案" 开头的行起）放进绿色折叠块 <toggle>，先做题再展开。
  - 正文里 "<字母" 转义为 "\\<"，避免被 Notion 当作标签吞掉（代码块内不转义）。
  - 去掉引用块里的表格前缀 "> |"（Notion 引用块里放不了表格）。
  - 章标题末尾的括号说明（如 "（教材 p37）"）移到页面首行引用，页面标题保持简短。
"""
import argparse, glob, io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

Q = re.compile(r"^\*\*(题)?\s*\d")
A = re.compile(r"^\s*(- )?\**答案")
ESC = re.compile(r"<(?=[A-Za-z/!])")
PAREN = re.compile(r"^(.*?)\s*[（(]([^（()）]*)[）)]\s*$")


def is_plain(l):
    s = l.lstrip()
    return bool(s) and not re.match(r"^([-*+] |\d+[.)] |\||>|#|```|<)", s)


def conv_problems(lines):
    """把一个典型题小节里的题目逐题处理：题干保留，答案段落装进折叠块。"""
    items, cur, head = [], None, []
    for l in lines:
        if Q.match(l):
            if cur is not None:
                items.append(cur)
            cur = [l]
        elif cur is None:
            head.append(l)
        else:
            cur.append(l)
    if cur is not None:
        items.append(cur)
    res, n = list(head), 0
    for it in items:
        while it and it[-1].strip() in ("", "---"):
            it.pop()
        ai = next((i for i, l in enumerate(it) if A.match(l)), None)
        q = it if ai is None else it[:ai]
        prev = False
        for l in q:  # 题干里相邻纯文本行（如选项行）拆成独立段落，避免在 Notion 里挤成一行
            if not l.strip():
                res.append("")
                prev = False
                continue
            p = is_plain(l)
            if p and prev:
                res.append("")
            res.append(l.strip() if p else l)
            prev = p
        if ai is not None:
            n += 1
            res += ["", '<toggle color="green">', "👉 答案与解析", ""]
            body = [l.strip() for l in it[ai:] if l.strip() and l.strip() != "---"]
            for l in body:
                res += [l, ""]
            if res[-1] == "":
                res.pop()
            res.append("</toggle>")
        res.append("")
    return res, n


def convert(lines):
    """标题上移一级 + 转义 + 处理典型题小节。返回 (文本, 折叠答案数)。"""
    tmp, incode = [], False
    for l in lines:
        if l.strip().startswith("```"):
            incode = not incode
            tmp.append(l)
            continue
        if not incode:
            m = re.match(r"^(#{3,6}) (.*)", l)
            if m:
                l = "#" * (len(m.group(1)) - 1) + " " + m.group(2)
            l = re.sub(r"^>\s?(?=\|)", "", l)
            l = ESC.sub(r"\\<", l)
        tmp.append(l)
    out, total, i = [], 0, 0
    while i < len(tmp):
        l = tmp[i]
        if l.startswith("## ") and "典型题" in l:
            j = i + 1
            while j < len(tmp) and not re.match(r"^#{1,2} ", tmp[j]):
                j += 1
            conv, n = conv_problems(tmp[i + 1:j])
            total += n
            out.append(l)
            out += conv
            i = j
        else:
            out.append(l)
            i += 1
    # 表格前后都补空行：表格紧跟在列表项后会被 Notion 并进该列表项（显示成一串 "\|"）；
    # 表格后紧跟的普通文字行会被吞成表格的多余一行
    fixed = []
    for l in out:
        is_t = l.lstrip().startswith("|")
        prev = fixed[-1] if fixed else ""
        prev_t = prev.lstrip().startswith("|")
        if prev.strip() and is_t != prev_t:
            fixed.append("")
        fixed.append(l)
    # 单元格里的绝对值竖线（如 |V_TP|）会把一行切成多格：换成全角 ｜ 并提示
    hdr = None
    for k, l in enumerate(fixed):
        if l.lstrip().startswith("|"):
            n = len(l.strip().strip("|").split("|"))
            if hdr is None:
                hdr = n
            elif n != hdr:
                print(f"  !! 表格某行列数 {n} ≠ 表头 {hdr}（多半是单元格里写了 |x|，请改成全角 ｜x｜）：{l.strip()[:60]}")
        else:
            hdr = None
    text = "\n".join(fixed).strip()
    text = re.sub(r"\n---\s*$", "", text).rstrip() + "\n"
    return text, total


def split_text(text, limit):
    """在折叠块之外、靠近中点的 "## 小节" 或题目开头处切开，递归直到每段 ≤ limit。"""
    if len(text) <= limit:
        return [text]
    lines = text.split("\n")
    pos, cands, depth = 0, [], 0
    for k, l in enumerate(lines):
        if l.startswith("<toggle"):
            depth += 1
        elif l.startswith("</toggle>"):
            depth -= 1
        elif depth == 0 and k > 0 and (l.startswith("## ") or l.startswith("### ") or Q.match(l)):
            cands.append((k, pos))
        pos += len(l) + 1
    if not cands:
        return [text]
    mid = len(text) / 2
    k, _ = min(cands, key=lambda c: abs(c[1] - mid))
    a, b = "\n".join(lines[:k]).rstrip() + "\n", "\n".join(lines[k:]).strip() + "\n"
    if not a.strip() or not b.strip():
        return [text]
    return split_text(a, limit) + split_text(b, limit)


ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--split-chars", type=int, default=10000)
ap.add_argument("--intro-regex", default=r"^(导言|附[：:])|符号对照|使用说明",
                help="匹配到的章并入分册页，不单独建子页面")
ap.add_argument("--single", default="", help="逗号分隔的分册号，整册做成一个页面（如公式速查）")
ap.add_argument("--vol-label", action="append", default=[], help='"01=01 半导体物理·刘恩科1–5"')
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
intro = re.compile(a.intro_regex)
singles = set(s for s in a.single.split(",") if s)
labels = dict(x.split("=", 1) for x in a.vol_label)

plan, rows = [], []
for f in sorted(glob.glob(os.path.join(a.src, "[0-9][0-9]_*.md"))):
    if os.path.basename(f).startswith("00"):
        continue  # 00_总览 单独做成总入口页
    vol = os.path.basename(f)[:2]
    lines = open(f, encoding="utf-8").read().splitlines()
    title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else os.path.basename(f)[3:-3]
    idx = [k for k, l in enumerate(lines) if l.startswith("## ")]
    short_title = re.sub(r"\s*复习资料.*$", "", PAREN.sub(r"\1", title)).strip(" ·")[:18]
    label = labels.get(vol) or f"{vol} {short_title}"
    if vol in singles or not idx:
        body, n = convert(lines[1:])
        p = os.path.join(a.out, f"v{vol}_page.md")
        open(p, "w", encoding="utf-8").write(body)
        plan.append(dict(vol=vol, title=title, label=label, page_md=p, page_chars=len(body), answers=n, chapters=[]))
        continue
    pre, _ = convert(lines[1:idx[0]])
    chapters, extra = [], []
    for c, k in enumerate(idx):
        end = idx[c + 1] if c + 1 < len(idx) else len(lines)
        raw_t = lines[k][3:].strip()
        seg = lines[k + 1:end]
        if intro.search(raw_t):
            body, _ = convert(seg)
            extra.append(f"## {raw_t}\n\n{body}")
            continue
        m = PAREN.match(raw_t)
        short, note = (m.group(1), m.group(2)) if m else (raw_t, "")
        body, n = convert(seg)
        if note:
            body = f"> {note}\n\n{body}"
        parts = split_text(body, a.split_chars)
        files = []
        for j, part in enumerate(parts):
            suf = "" if len(parts) == 1 else "_" + "abcdefgh"[j]
            p = os.path.join(a.out, f"v{vol}_c{len(chapters) + 1:02d}{suf}.md")
            open(p, "w", encoding="utf-8").write(part)
            files.append(p)
        chapters.append(dict(title=short, files=files, chars=len(body), answers=n))
        # 数据库行：取本章「知识点清单」
        inlist = False
        for l in seg:
            if l.startswith("### "):
                inlist = l.startswith("### 知识点清单")
            elif inlist and l.startswith("- [ ]"):
                s = l[5:].strip()
                mm = re.match(r"^(★+)\s*(.*)$", s)
                star, s = (mm.group(1)[:3], mm.group(2)) if mm else ("★", s)
                pg = ""
                m2 = re.search(r"[（(]\s*(p\s?\d[\d–\-、, p]*)\s*[）)]\s*$", s)
                if m2:
                    pg, s = m2.group(1), s[:m2.start()].strip()
                rows.append({"知识点": s.replace("**", "")[:300], "分册": label, "章节": short,
                             "重要程度": star, "教材页码": pg, "掌握状态": "未开始"})
    page = pre.rstrip()
    for e in extra:
        page += "\n\n" + e.rstrip()
    page += "\n\n## 本册章节\n\n各章为下方子页面：知识点清单 → 核心内容 → 易错点 → 典型题（答案折叠，先做再展开）。\n"
    p = os.path.join(a.out, f"v{vol}_page.md")
    open(p, "w", encoding="utf-8").write(page)
    plan.append(dict(vol=vol, title=title, label=label, page_md=p, page_chars=len(page), chapters=chapters))

json.dump(plan, open(os.path.join(a.out, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for i in range(0, len(rows), 90):
    json.dump(rows[i:i + 90], open(os.path.join(a.out, f"db_rows_{i // 90 + 1}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
COLORS = ["blue", "purple", "brown", "green", "orange", "pink", "yellow", "red", "gray"]
opts = ", ".join(f"'{p['label']}':{COLORS[i % len(COLORS)]}" for i, p in enumerate(x for x in plan if x["chapters"]))
schema = ('CREATE TABLE ("知识点" TITLE, "分册" SELECT(' + opts + '), "章节" RICH_TEXT, '
          "\"重要程度\" SELECT('★★★':red, '★★':orange, '★':gray), \"教材页码\" RICH_TEXT, "
          "\"掌握状态\" STATUS('未开始':gray:to_do, '学习中':blue:in_progress, '已掌握':green:complete), "
          '"复习次数" NUMBER, "备注" RICH_TEXT)')
open(os.path.join(a.out, "db_schema.sql"), "w", encoding="utf-8").write(schema + "\n")

for p in plan:
    print(f"{p['vol']} {p['title'][:40]}  分册页 {p['page_chars']} 字")
    for c in p["chapters"]:
        tag = f" -> 拆成 {len(c['files'])} 段" if len(c["files"]) > 1 else ""
        print(f"    {c['title'][:40]}  {c['chars']} 字  答案折叠 {c['answers']}{tag}")
print(f"\n知识点 {len(rows)} 行 -> {(len(rows) + 89) // 90} 个 db_rows 批次；schema 见 db_schema.sql")
