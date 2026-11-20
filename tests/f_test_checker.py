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


def seg_rows(ws):
    """[(行, 批次, 单位, 节点, 收发, 代领交, 被代单位, 备注列)]，节点沿用所属的站。"""
    out, b, u, n, io = [], None, None, None, None
    for r in ws.iter_rows(min_row=2, max_col=14):
        if r[0].value is not None:
            b, u = r[0].value, r[2].value
        if r[3].value is not None:
            n = r[3].value
        if r[5].value is not None:
            io = r[5].value
            out.append(dict(row=r[5].row, b=b, u=u, node=n, io=io, flag=r[8].value, who=r[9].value, note=r[13]))
    return out


def t_nonote(ws):
    n = 0
    for r in ws.iter_rows(min_row=2, max_col=14):
        if isinstance(r[13].value, str) and ("暂存" in r[13].value or "领回" in r[13].value):
            r[13].value = None
            n += 1
    return f"删去 {n} 处“暂存/领回”备注（R4 判定不应依赖备注）"


def t_r4_pick(ws):
    for g in seg_rows(ws):
        if g["flag"] == 0 and g["io"] == "发" and isinstance(g["note"].value, str) and "领回" in g["note"].value:
            q = ws.cell(g["row"], 8)
            if isinstance(q.value, (int, float)):
                q.value = q.value + 1
                return f"批 {g['b']} 在 {g['node']} 领回暂存货的数量 +1（找不到对应的暂存，且货主驻地 > 150 km）"
    raise RuntimeError("没有领回")


def t_r5(ws):
    for g in seg_rows(ws):
        if g["flag"] == -1 and g["io"] == "发" and g["node"] not in H[g["u"]]:
            other = next(u for u in ("U9", "U7", "U1") if u not in (g["who"], g["u"]))
            ws.cell(g["row"], 10).value = other
            return f"批 {g['b']} 在 {g['node']} 替 {g['who']} 装的代交货改记为替 {other}（R5 失去同一货主的配对代交）"
    raise RuntimeError("没有外部代交")


def case0(name, mutate):
    """篡改后检查器应仍报 0 条（稳健性）。"""
    tmp = Path(tempfile.mkdtemp()) / "p3.xlsx"
    shutil.copy(P3, tmp)
    wb = openpyxl.load_workbook(tmp)
    desc = mutate(wb.worksheets[0])
    wb.save(tmp)
    ok = "违例 0 条" in run(tmp)
    print(("通过" if ok else "失败"), name, "|", desc)
    return ok


def t_leave_partial(ws):
    """在一个装了两行以上货的站，只把其中一行改为“留置”：件 7 注 7 要求当前已装车的全部车辆留下（【裁X2】），部分留置应报 S11。"""
    rows = seg_rows(ws)
    by = {}
    for g in rows:
        if g["io"] == "发":
            by.setdefault((g["b"], g["node"], g["row"] // 1000), []).append(g)
    for (b, n, _), gs in by.items():
        if len(gs) >= 2 and all(ws.cell(g["row"], 12).value != "否" for g in gs):
            ws.cell(gs[0]["row"], 12).value = "否"
            return f"批 {b} 在 {n} 装的 {len(gs)} 行货中只把第 1 行改为留置"
    raise RuntimeError("没有装两行以上货的站")

if __name__ == "__main__":
    base = run(P3)
    assert "违例 0 条" in base, base
    print("原表：违例 0 条")
    res = [case("到达时刻 +10 分钟", "时刻", t_time), case("货量 +1", "守恒", t_qty), case("整批推迟 30 天", "S2", t_shift),
           case("代领改自领", "守恒", t_flag), case("S15 无关节点", "S15", t_s15), case("S10 留置 16:00 边界", "S10", t_s10),
           case0("删去暂存/领回备注", t_nonote), case("R4 领回量对不上", "R3/R4", t_r4_pick), case("R5 代交改记他人", "R5", t_r5), case("留置改为部分随行", "S11", t_leave_partial)]
    print("未做篡改自检的新规则：S11 逆序汇合（现方案没有多站留置）、R5 先后（篡改需要挪动跨站的作业段）；"
          "包 3 第 1、3 条（代交晚装、留置+排队）在现方案上构造不出单点篡改，由 tools/pack3_probe.py 对每次结果探测。"
          "S12 前后两半、R4 整批先后已在旧方案（提交 928738d、2276c9b）的真实违例上被检查器报出。")
    sys.exit(0 if all(res) else 1)
