"""独立检查器 tools/f_check.py 的篡改自检（A5 之后新增规则）。

复制问题 3 的结果表，每次只做一种篡改，确认检查器报出对应的违例代码。
用法：python tests/f_test_checker.py
"""
import datetime as dt
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
P2 = ROOT / "results/F/问题2_results.xlsx"
P3 = ROOT / "results/F/问题3_results.xlsx"
H = {"U8": ["WO"], "U11": ["WO", "WS"], "U12": ["WO"], "U6": ["WP"], "U9": ["WP"], "U3": ["WQ"], "U7": ["WQ", "WU"],
     "U4": ["WR"], "U10": ["WS"], "U2": ["WS"], "U5": ["WS"], "U1": ["WT"]}


def stops(ws):
    """[(批次, 单位, 行号, 节点, 是否有作业段, 是否随行列)]，按表中顺序。"""
    out, b, u = [], None, None
    rows = list(ws.iter_rows(min_row=2, max_col=14))
    for i, r in enumerate(rows):
        if r[0].value is not None:
            b, u = r[0].value, r[2].value
        if r[3].value is not None:
            has_seg = any(rows[j][5].value is not None for j in range(i, len(rows)) if j == i or rows[j][3].value is None and rows[j][0].value is None)
            out.append(dict(b=b, u=u, row=r[3].row, node=r[3].value, seg=r[5].value is not None, follow=r[11].value))
    return out


def run(path):
    p = subprocess.run([sys.executable, str(ROOT / "tools/f_check.py"), str(P2), str(path), "--out", str(path) + "_chk"],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout


def case(name, code, mutate):
    tmp = Path(tempfile.mkdtemp()) / "p3.xlsx"
    shutil.copy(P3, tmp)
    wb = openpyxl.load_workbook(tmp)
    ws = wb.worksheets[0]
    desc = mutate(ws)
    wb.save(tmp)
    out = run(tmp)
    ok = f"'{code}'" in out
    print(("通过" if ok else "失败"), name, "|", desc)
    return ok


def t_s15(ws):
    st = stops(ws)
    by = {}
    for s in st:
        by.setdefault(s["b"], []).append(s)
    for b, ss in by.items():
        nodes = {s["node"] for s in ss}
        for s in ss[1:-1]:
            if not s["seg"]:
                bad = next(w for w in ("WK", "WL", "WM", "WN", "WH") if w not in nodes)
                ws.cell(s["row"], 4).value = bad
                return f"批 {b} 第 {s['row']} 行的途经站 {s['node']} 改为无关节点 {bad}"
    raise RuntimeError("没有途经站")


def t_s10(ws):
    st = stops(ws)
    for i, s in enumerate(st):
        if s["follow"] == "否":
            j = next(k for k in range(i + 1, len(st)) if st[k]["b"] == s["b"] and st[k]["node"] == s["node"])
            dep = ws.cell(s["row"], 13).value
            new = dt.datetime(dep.year, dep.month, dep.day, 16, 0) + dt.timedelta(days=2)
            ws.cell(st[j]["row"], 5).value = new
            return f"批 {s['b']} 在 {s['node']} 留置，汇合到达改为 {new:%m/%d %H:%M}（中间整日闲置 1 天 + 16:00 才到）"
    raise RuntimeError("没有留置")


def t_time(ws):
    st = stops(ws)
    s = st[3]
    t = ws.cell(s["row"], 5).value
    ws.cell(s["row"], 5).value = t + dt.timedelta(minutes=10)
    return f"批 {s['b']} 第 {s['row']} 行到达时刻 +10 分钟"


def t_qty(ws):
    for r in ws.iter_rows(min_row=2, max_col=14):
        if isinstance(r[7].value, (int, float)) and r[7].value > 1:
            r[7].value = r[7].value + 1
            return f"第 {r[7].row} 行货物数量 +1"
    raise RuntimeError


def t_shift(ws):
    st = stops(ws)
    b0 = st[0]["b"]
    n = 0
    for s in st:
        if s["b"] == b0:
            for c in (5, 13):
                v = ws.cell(s["row"], c).value
                if v is not None:
                    ws.cell(s["row"], c).value = v + dt.timedelta(days=30)
            n += 1
    return f"批 {b0} 全部 {n} 站推迟 30 天"


def t_flag(ws):
    for r in ws.iter_rows(min_row=2, max_col=14):
        if r[8].value == 1:
            r[8].value = 0
            r[9].value = None
            return f"第 {r[8].row} 行代领改为自领"
    raise RuntimeError


if __name__ == "__main__":
    base = run(P3)
    assert "违例 0 条" in base, base
    print("原表：违例 0 条")
    res = [case("到达时刻 +10 分钟", "时刻", t_time), case("货量 +1", "守恒", t_qty), case("整批推迟 30 天", "S2", t_shift),
           case("代领改自领", "守恒", t_flag), case("S15 无关节点", "S15", t_s15), case("S10 留置 16:00 边界", "S10", t_s10)]
    print("未做篡改自检的新规则：S11 逆序汇合（现方案没有多站留置）、R5 先后（篡改需要挪动跨站的作业段）。"
          "S12 前后两半、R4 整批先后已在旧方案（提交 928738d、2276c9b）的真实违例上被检查器报出。")
    sys.exit(0 if all(res) else 1)
