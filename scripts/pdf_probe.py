"""盘点教材 PDF：页数、是否有文字层、书签目录；可选把指定页渲染成 PNG 供看图读目录 / 校准页码偏移。

用法:
  python pdf_probe.py <PDF或目录> [--toc-depth 2] [--toc-max 60]
  python pdf_probe.py <某本.pdf> --render 1-12,30 --out <目录> [--zoom 1.5]

依赖 PyMuPDF：pip install pymupdf
页码均为 PDF 页码（从 1 开始），不是书上印的页码。
"""
import argparse, os, sys, glob, io

try:
    import pymupdf as fitz  # 新版 PyMuPDF
except ImportError:
    try:
        import fitz  # 旧版 PyMuPDF
    except ImportError:
        sys.exit("缺少 PyMuPDF，请先运行: pip install pymupdf")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def parse_pages(spec, n):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 1 <= p <= n]


def text_layer(doc):
    """抽 8 个均匀分布的页面，统计平均每页可提取字符数。< 50 基本可判定为纯扫描件。"""
    n = doc.page_count
    idx = sorted({int(n * k / 9) for k in range(1, 9)} & set(range(n)))
    chars = [len(doc[i].get_text("text").strip()) for i in idx]
    return sum(chars) / max(len(chars), 1)


def probe(path, depth, tmax):
    doc = fitz.open(path)
    avg = text_layer(doc)
    toc = doc.get_toc(simple=True)
    print(f"\n=== {os.path.basename(path)}")
    print(f"页数 {doc.page_count} | 平均每页文字 {avg:.0f} 字符 -> "
          + ("有文字层，可直接抽取文本" if avg >= 50 else "扫描件（无文字层），需看图或 OCR"))
    print(f"书签 {len(toc)} 条" + ("" if toc else "（无书签，需渲染目录页看图）"))
    shown = [t for t in toc if t[0] <= depth][:tmax]
    numeric = sum(1 for t in shown if t[1].strip().replace(" ", "").isdigit())
    for lvl, title, page in shown:
        print(f"  {'  ' * (lvl - 1)}{title}  ->PDF p{page}")
    allnum = [t for t in toc if t[1].strip().isdigit()]
    if allnum and len(allnum) > len(toc) / 2:
        first = min(allnum, key=lambda t: int(t[1]))
        print(f"  !! 书签大多只是页码，不能当目录用；但能直接看出偏移：书签 \"{first[1].strip()}\" 在 PDF p{first[2]}"
              f" -> 印刷页 ≈ PDF页 − {first[2] - int(first[1])}（渲染一页正文核实）")
        named = [t for t in toc if not t[1].strip().isdigit()]
        for lvl, title, page in named[:12]:
            print(f"     {title}  ->PDF p{page}")
        print("     目录页在上面 '目录' 书签到第一个数字书签之间，渲染后看图转写")
    elif shown and numeric > len(shown) / 2:
        print("  !! 书签标题大多只是数字，不可当目录用：渲染目录页（通常在前 5–20 页）看图转写")
    if len([t for t in toc if t[0] <= depth]) > tmax:
        print(f"  ...（只显示前 {tmax} 条，用 --toc-max 调大）")


def render(path, spec, out, zoom):
    doc = fitz.open(path)
    os.makedirs(out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0][:20]
    for p in parse_pages(spec, doc.page_count):
        pix = doc[p - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        f = os.path.join(out, f"{stem}_p{p:04d}.png")
        pix.save(f)
        print(f)


ap = argparse.ArgumentParser()
ap.add_argument("target")
ap.add_argument("--toc-depth", type=int, default=2)
ap.add_argument("--toc-max", type=int, default=60)
ap.add_argument("--recursive", action="store_true", help="连子目录一起扫（默认只扫当前目录，避免把数据手册等杂项也扫进来）")
ap.add_argument("--render")
ap.add_argument("--out", default="pdf_pages")
ap.add_argument("--zoom", type=float, default=1.5)
a = ap.parse_args()

if a.render:
    render(a.target, a.render, a.out, a.zoom)
else:
    if os.path.isdir(a.target):
        pat = os.path.join(a.target, "**", "*.[pP][dD][fF]") if a.recursive else os.path.join(a.target, "*.[pP][dD][fF]")
        files = sorted(set(glob.glob(pat, recursive=a.recursive)))
    else:
        files = [a.target]
    for f in files:
        try:
            probe(f, a.toc_depth, a.toc_max)
        except Exception as e:  # 单本坏文件不影响其他
            print(f"\n=== {os.path.basename(f)}\n  打开失败: {e}")
