"""F 题结果表导出：按附件 6、7、8 的模板填表（保留表头与说明，删除样例行）。

批次重新编号：按出发日、原批次号排序后从 1 连续编号；新旧批次号对照另存 csv。
"""
from __future__ import annotations

import datetime as dt
import glob
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment

import f_blocks as fb
import f_engine as fe
import f_routes as fr

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "problem" / "F" / "original" / "附件"
YEAR = 2026


def _tpl(k):
    return glob.glob(str(TPL / f"附件{k} *.xlsx"))[0]


def _to_dt(t):
    d, h = t
    m, dd = (4, d) if d <= 30 else ((5, d - 30) if d <= 61 else (6, d - 61))
    mins = int(round(h * 60))
    return dt.datetime(YEAR, m, dd, 8, 0) + dt.timedelta(minutes=mins)


def _md(d):
    m, dd = (4, d) if d <= 30 else ((5, d - 30) if d <= 61 else (6, d - 61))
    return f"{m}月{dd}日"


def _clear(ws, ncol):
    for rg in list(ws.merged_cells.ranges):
        if rg.min_col <= ncol and rg.min_row >= 2:
            ws.unmerge_cells(str(rg))
    for row in ws.iter_rows(min_row=2, max_col=ncol):
        for c in row:
            c.value = None


def _merge(ws, col, r0, r1):
    if r1 > r0:
        ws.merge_cells(start_row=r0, start_column=col, end_row=r1, end_column=col)
    ws.cell(r0, col).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def role_flag(role, owner):
    """(代领交标记, 被代单位)。"""
    return {"own": (0, None), "领回": (0, None), "代领": (1, owner), "代交": (-1, owner)}[role]


def renumber(ids, start_day):
    order = sorted(ids, key=lambda b: (start_day[b], b))
    return {b: i + 1 for i, b in enumerate(order)}


def write_p2(path, assign, batches, blocks, cap, new_id, tnp):
    """附件 6。tnp: {原批次: (T, N, P)}。"""
    wb = openpyxl.load_workbook(_tpl(6))
    ws = wb.worksheets[0]
    _clear(ws, 11)
    groups = fr.batch_groups(assign, batches, blocks, cap)
    r = 2
    for b in sorted(groups, key=lambda x: new_id[x]):
        x = batches[b].unit
        own = set(fb.H[x])
        r0 = r
        segs = {}
        for g in groups[b].values():
            for kid, role in g.parts:
                k = blocks[kid]
                if g.load in own and g.unload not in own or role == "代交":
                    wh, io = g.unload, "收"  # 货送进仓库
                else:
                    wh, io = g.load, "发"
                flag, who = role_flag(role, k.owner)
                segs.setdefault((wh, io, flag, who), []).extend(k.items.items())
        for (wh, io, flag, who), items in sorted(segs.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[0][2], kv[0][3] or "")):
            s0 = r
            for it, q in items:
                ws.cell(r, 5, it)
                ws.cell(r, 6, int(q) if float(q).is_integer() else q)
                r += 1
            ws.cell(s0, 3, wh); ws.cell(s0, 4, io); ws.cell(s0, 7, flag); ws.cell(s0, 8, who)
            for col in (3, 4, 7, 8):
                _merge(ws, col, s0, r - 1)
        T, N, P = tnp[b]
        ws.cell(r0, 1, new_id[b]); ws.cell(r0, 2, x); ws.cell(r0, 9, T); ws.cell(r0, 10, N); ws.cell(r0, 11, P)
        for col in (1, 2, 9, 10, 11):
            _merge(ws, col, r0, r - 1)
    wb.save(path)


def write_p3(path, tpl_k, inst, sol, ev, new_id):
    """附件 7 / 8。inst：f_p3.Instance；sol：{原批次: (路线, 出发日)}；ev：inst.evaluate(sol)。"""
    wb = openpyxl.load_workbook(_tpl(tpl_k))
    ws = wb.worksheets[0]
    _clear(ws, 14)
    blocks, batches = inst.blocks, inst.batches
    r = 2
    for b in sorted(inst.ids, key=lambda x: new_id[x]):
        x = batches[b].unit
        res = ev["res"][b]
        steps = inst.cands[b][sol[b][0]]["steps"]
        gs = inst.groups[b]
        r0 = r
        for st, lg in zip(steps, res.logs):
            s0 = r
            is_base = st.node == x and st is steps[-1]
            segs = []  # (收发, 标记, 被代单位, 货物行, 等效车数, 是否随行, 备注)
            for gid, sgn in [(g, -1) for g in st.unload] + [(g, 1) for g in st.load]:
                g = gs[gid]
                by = {}
                for kid, role in g.parts:
                    k = blocks[kid]
                    flag, who = role_flag(role, k.owner)
                    key = (flag, who, role)
                    by.setdefault(key, [0.0, []])
                    by[key][0] += k.s(inst.cap, x)
                    by[key][1].extend(k.items.items())
                for (flag, who, role), (sv, items) in by.items():
                    note = {"own": "", "代领": f"代{who}领", "代交": f"代{who}交", "领回": "领回暂存货物"}[role]
                    if sgn > 0 and gid in st.leave:
                        note = (note + "；" if note else "") + "装车后留置等待"
                    if sgn < 0 and g.unload in fb.H[x]:
                        note = (note + "；" if note else "") + "卸载进入队属货物仓库"
                    if sgn > 0 and g.load in fb.H[x]:
                        note = (note + "；" if note else "") + "队属货物仓库装车"
                    if sgn < 0 and role == "代领" and g.unload not in fb.H[who]:
                        note += "；暂存，由货主领回"
                    segs.append(("收" if sgn < 0 else "发", flag, who, items, sgn * sv, "否" if (sgn > 0 and gid in st.leave) else "是", note))
            if not segs:
                note = "回到驻地" if is_base else ("返回汇合" if st.rejoin else "途经，不作业")
                ws.cell(r, 14, note)
                r += 1
            for io, flag, who, items, sv, follow, note in segs:
                g0 = r
                for it, q in items:
                    ws.cell(r, 7, it)
                    ws.cell(r, 8, int(q) if float(q).is_integer() else q)
                    r += 1
                ws.cell(g0, 6, io); ws.cell(g0, 9, flag); ws.cell(g0, 10, who); ws.cell(g0, 11, round(sv, 6)); ws.cell(g0, 12, follow)
                ws.cell(g0, 14, (note + ("；返回汇合" if st.rejoin and g0 == s0 else "")) or None)
                for col in (6, 9, 10, 11, 12, 14):
                    _merge(ws, col, g0, r - 1)
            ws.cell(s0, 4, st.node)
            c = ws.cell(s0, 5, _to_dt(lg.arrive)); c.number_format = "m/d h:mm"
            if not is_base:
                c = ws.cell(s0, 13, _to_dt(lg.depart)); c.number_format = "m/d h:mm"
            for col in (4, 5, 13):
                _merge(ws, col, s0, r - 1)
        ws.cell(r0, 1, new_id[b])
        ws.cell(r0, 2, f"{_md(res.start_day)}至{_md(res.end_day)}")
        ws.cell(r0, 3, x)
        for col in (1, 2, 3):
            _merge(ws, col, r0, r - 1)
    wb.save(path)
