"""把 paper/初稿/00–08 的 Markdown 转成竞赛格式的 Word：paper/build/论文.docx（每次重新生成，人在 Word/WPS 里改终稿）。

格式依据《论文格式规范 2026》：第一页为摘要页（页码从 1 起，页脚居中），正文从新页开始、无目录，
附录含支撑材料列表与全部源程序；页边距 2.5 cm。字体字号规范未作要求，取宋体/Times 小四、标题黑体。
- 行内公式 $…$ 转成带上下标的原生文字（可编辑）；独立公式 $$…$$ 用 matplotlib 渲染成图片。
- HTML 注释（数字键、内部说明）全部删除；【】待补标记保留并标黄，便于定稿前查找。
用法：python tools/md2docx.py [--title 题目]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_SECTION  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "paper" / "初稿"
OUT = ROOT / "paper" / "build"
EQ = OUT / "eq"
CHAPTERS = ["00_摘要.md", "01_问题重述与分析.md", "02_假设与符号.md", "03_共用模块.md", "04_问题1.md",
            "05_问题2.md", "06_问题3.md", "07_问题4.md", "08_灵敏度与评价.md"]
CODE_FILES = (sorted((ROOT / "src").glob("f_*.py")) +
              [ROOT / "tools" / n for n in ("f_check.py", "tri_check.py", "paper_numbers.py", "make_figures.py", "make_tables.py")])
DEFAULT_TITLE = "基于需求块的货物调运统筹与实施方案三层优化模型"

BODY_PT, SMALL_PT = 12, 10.5
LINE = [1.25]  # 摘要页用 1.1，正文 1.25


# ---------------- 字体 ----------------
def set_font(run, east="宋体", west="Times New Roman", size=None, bold=None, italic=None):
    run.font.name = west
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    rf.set(qn("w:eastAsia"), east)
    rf.set(qn("w:ascii"), west)
    rf.set(qn("w:hAnsi"), west)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic


def para_fmt(p, indent=True, align=None, size=BODY_PT, spacing=None, before=0, after=0):
    f = p.paragraph_format
    f.line_spacing = spacing or LINE[0]
    f.space_before, f.space_after = Pt(before), Pt(after)
    f.first_line_indent = Pt(2 * size) if indent else None
    if align:
        p.alignment = align


# ---------------- 行内公式 → 原生文字 ----------------
SYM = {"beta": "β", "tau": "τ", "delta": "δ", "in": "∈", "le": "≤", "ge": "≥", "sum": "∑", "quad": " ", "qquad": "  ",
       "{": "{", "}": "}", " ": " ", ",": " ", "lceil": "⌈", "rceil": "⌉", "max": "max", "min": "min", "times": "×",
       "cdot": "·", "alpha": "α", "lambda": "λ", "infty": "∞", "neq": "≠", "approx": "≈", "ldots": "…"}


def _group(s, i):
    """s[i] 起读一个记号或 {…} 组，返回 (内容, 新位置)。"""
    if s[i] == "{":
        depth, j = 1, i + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        return s[i + 1:j - 1], j
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        return m.group(0), i + len(m.group(0))
    return s[i], i + 1


def math_runs(s, sub=False, sup=False):
    """返回 [(文字, 斜体, 下标, 上标)]。"""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c in "_^":
            g, i = _group(s, i + 1)
            out += math_runs(g, sub=(c == "_") or sub, sup=(c == "^") or sup)
            continue
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            name, i = m.group(1), i + len(m.group(0))
            if name == "bar":
                g, i = _group(s, i)
                for t, it, sb, sp in math_runs(g, sub, sup):
                    out.append((t + "\u0304", it, sb, sp))
            elif name in ("text", "mathrm", "operatorname"):
                g, i = _group(s, i)
                out.append((g, False, sub, sup))
            elif name in ("big", "Big", "left", "right", "bigl", "bigr"):
                continue
            else:
                out.append((SYM.get(name, name), False, sub, sup))
            continue
        if c in "{}":
            i += 1
            continue
        if c == " ":
            i += 1
            continue
        if c.isalpha():
            out.append((c, True, sub, sup))
        else:
            out.append(({"-": "−", "*": "×"}.get(c, c), False, sub, sup))
        i += 1
    return out


# ---------------- 独立公式 → 图片 ----------------
plt.rcParams.update({"mathtext.fontset": "custom", "mathtext.rm": "Times New Roman", "mathtext.it": "Times New Roman:italic",
                     "mathtext.bf": "Times New Roman:bold", "mathtext.sf": "SimSun"})
_eq_n = [0]


def render_eq(tex):
    t = tex.strip().rstrip(",.;，。")
    t = re.sub(r"\\text\{([^}]*)\}", lambda m: r"\mathsf{" + m.group(1) + "}" if re.search(r"[\u4e00-\u9fff]", m.group(1))
               else r"\mathrm{" + m.group(1) + "}", t)
    t = t.replace("\\frac", "\\dfrac")
    t = re.sub(r"\\(Big|big|bigl|bigr|Bigl|Bigr)(?=[()\[\]|]|\\l|\\r)", "", t)
    t = t.replace("\\qquad", "\\quad\\quad")
    _eq_n[0] += 1
    EQ.mkdir(parents=True, exist_ok=True)
    path = EQ / f"eq{_eq_n[0]:02d}.png"
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, f"${t}$", fontsize=13)
    fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.03, transparent=True)
    plt.close(fig)
    return path


# ---------------- 行内 Markdown ----------------
TOKEN = re.compile(r"(\*\*.+?\*\*|\$[^$]+\$|`[^`]+`|(?<![*\w])\*[^*\s][^*]*?\*(?!\*)|【[^】]*】)")


def add_inline(p, text, size=BODY_PT, bold=False):
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            add_inline(p, part[2:-2], size, bold=True)
        elif part.startswith("$"):
            for t, it, sb, sp in math_runs(part[1:-1]):
                r = p.add_run(t)
                set_font(r, size=size, bold=bold, italic=it)
                r.font.subscript, r.font.superscript = sb and not sp, sp
        elif part.startswith("`"):
            r = p.add_run(part[1:-1])
            set_font(r, east="宋体", west="Consolas", size=size - 1.5, bold=bold)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            r = p.add_run(part[1:-1])
            set_font(r, east="楷体", size=size, bold=bold, italic=True)
        elif part.startswith("【"):
            r = p.add_run(part)
            set_font(r, size=size, bold=bold)
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else:
            r = p.add_run(part)
            set_font(r, size=size, bold=bold)


# ---------------- 块级 ----------------
def heading(doc, text, level):
    p = doc.add_paragraph()
    size = {1: 14, 2: 12, 3: 12}[level]
    para_fmt(p, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER if level == 1 else None, size=size,
             before=12 if level == 1 else 6, after=6 if level == 1 else 3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_font(r, east="黑体", west="Times New Roman", size=size, bold=True)
    return p


def table(doc, rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
    ncol = max(len(r) for r in cells)
    t = doc.add_table(rows=len(cells), cols=ncol)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, r in enumerate(cells):
        for j in range(ncol):
            cell = t.cell(i, j)
            p = cell.paragraphs[0]
            para_fmt(p, indent=False, size=SMALL_PT, spacing=1.0)
            add_inline(p, r[j] if j < len(r) else "", size=SMALL_PT, bold=(i == 0))
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def picture(doc, path, width_cm=15):
    p = doc.add_paragraph()
    para_fmt(p, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, spacing=1.0)
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    p.paragraph_format.keep_with_next = True


def equation(doc, tex):
    path = render_eq(tex)
    from PIL import Image
    w, h = Image.open(path).size
    p = doc.add_paragraph()
    para_fmt(p, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, spacing=1.0, before=3, after=3)
    p.add_run().add_picture(str(path), height=Cm(h / 300 * 2.54 * 0.85)) if w / 300 * 2.54 * 0.85 < 15.5 else \
        p.add_run().add_picture(str(path), width=Cm(15.5))


def page_number_footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        r._r.append(el)
    set_font(r, size=SMALL_PT)


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def convert(md, doc, base):
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s.startswith("$$"):
            buf = s[2:]
            while not buf.rstrip().endswith("$$"):
                i += 1
                buf += " " + lines[i].strip()
            equation(doc, buf.rstrip()[:-2])
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            table(doc, rows)
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if text == "附录":
                page_break(doc)
            heading(doc, text, level)
            i += 1
            continue
        m = re.match(r"^!\[[^\]]*\]\(([^)]+)\)", s)
        if m:
            picture(doc, (base / m.group(1)).resolve())
            i += 1
            continue
        m = re.match(r"^(\d+\.|[-*])\s+(.*)$", s)
        if m:
            p = doc.add_paragraph()
            para_fmt(p, indent=False)
            p.paragraph_format.left_indent = Pt(2 * BODY_PT)
            p.paragraph_format.first_line_indent = Pt(-1.2 * BODY_PT) if m.group(1)[0].isdigit() else Pt(-BODY_PT)
            add_inline(p, (m.group(1) + " " if m.group(1)[0].isdigit() else "• ") + m.group(2))
            i += 1
            continue
        # 普通段落：合并到空行
        buf = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||\$\$|!\[|\d+\.\s|[-*]\s)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        text = "".join(buf)
        p = doc.add_paragraph()
        caption = re.match(r"^(图 ?\d|\*\*表 ?\d|表 ?\d+-\d)", text)
        para_fmt(p, indent=not caption, align=WD_ALIGN_PARAGRAPH.CENTER if caption else None,
                 size=SMALL_PT if caption else BODY_PT, after=3 if caption else 0)
        add_inline(p, text, size=SMALL_PT if caption else BODY_PT)


def code_appendix(doc):
    for f in CODE_FILES:
        if not f.exists():
            continue
        heading(doc, f"B.{CODE_FILES.index(f) + 1} {f.relative_to(ROOT).as_posix()}", 3)
        for ln in f.read_text(encoding="utf-8").splitlines():
            p = doc.add_paragraph()
            f_ = p.paragraph_format
            f_.line_spacing, f_.space_before, f_.space_after = 1.0, Pt(0), Pt(0)
            r = p.add_run(ln.replace("\t", "    ") or " ")
            set_font(r, east="宋体", west="Consolas", size=7.5)


def main():
    title = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else DEFAULT_TITLE
    OUT.mkdir(parents=True, exist_ok=True)
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Times New Roman", Pt(BODY_PT)
    st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(sec, side, Cm(2.5))
    page_number_footer(sec)

    p = doc.add_paragraph()
    para_fmt(p, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=16, after=6)
    set_font(p.add_run(title), east="黑体", size=16, bold=True)
    for k, name in enumerate(CHAPTERS):
        md = (SRC / name).read_text(encoding="utf-8")
        LINE[0] = 1.1 if k == 0 else 1.25
        if k == 0:
            md = md.replace("# 摘要", "# 摘　要", 1)
        convert(md, doc, SRC)
        if k == 0:
            page_break(doc)
        if name.startswith("08"):
            code_appendix(doc)
    out = OUT / "论文.docx"
    doc.save(out)
    print(f"写出 {out}（独立公式 {_eq_n[0]} 个）")


if __name__ == "__main__":
    main()
