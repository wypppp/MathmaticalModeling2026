"""F 题附件解析：把附件 2/3/4（合并单元格的批次表）展开为长表。

输出列：src, batch, time_raw, start, end, unit, wh_col, flow, item, qty, remark, T, N, P, row
- 合并单元格按左上角值回填；未合并的空单元格保持为空。
- 运输车数/总车数/人数只在其所在合并块内有效（一个批次可能有多块，见附件2 批次4）。
- 日期：字符串“X月X日至X月X日”或 Excel 日期（单日提报），统一成 (月,日) 元组。
"""
from __future__ import annotations

import datetime as dt
import glob
import re
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ORIG = ROOT / "problem" / "F" / "original" / "附件"

OWN_WH = {"U8": ["WO"], "U11": ["WO", "WS"], "U12": ["WO"], "U6": ["WP"], "U9": ["WP"],
          "U3": ["WQ"], "U7": ["WQ", "WU"], "U4": ["WR"], "U10": ["WS"], "U2": ["WS"],
          "U5": ["WS"], "U1": ["WT"]}  # 题面附表1


def _find(k: int) -> str:
    return glob.glob(str(ORIG / f"附件{k} *.xlsx"))[0]


def _filled(ws):
    """返回 (grid, block)：grid 为回填后的值；block[(r,c)] 为该格所属合并块的左上角。"""
    grid = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row}
    block = {}
    for rg in ws.merged_cells.ranges:
        v = grid.get((rg.min_row, rg.min_col))
        for r in range(rg.min_row, rg.max_row + 1):
            for c in range(rg.min_col, rg.max_col + 1):
                grid[(r, c)] = v
                block[(r, c)] = (rg.min_row, rg.min_col)
    return grid, block


def parse_time(v):
    if v is None:
        return None, None
    if isinstance(v, (dt.datetime, dt.date)):
        return (v.month, v.day), (v.month, v.day)
    if isinstance(v, (int, float)):
        d = dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
        return (d.month, d.day), (d.month, d.day)
    m = re.findall(r"(\d+)月(\d+)日?", str(v))  # 附件 2、4 有“4月14至4月20日”这种开始日省略“日”字的写法
    if len(m) == 2:
        return (int(m[0][0]), int(m[0][1])), (int(m[1][0]), int(m[1][1]))
    if len(m) == 1:
        return (int(m[0][0]), int(m[0][1])), (int(m[0][0]), int(m[0][1]))
    raise ValueError(f"无法解析时间: {v!r}")


def load(k: int) -> pd.DataFrame:
    """k=2,4（统筹前）或 3（统筹后）。"""
    wb = openpyxl.load_workbook(_find(k))
    ws = wb.worksheets[0]
    grid, block = _filled(ws)
    if k == 3:
        col = dict(batch=1, time=2, unit=3, wh=None, flow=4, item=5, qty=6, T=7, N=8, P=9, remark=10)
    else:
        col = dict(batch=1, time=2, unit=3, wh=4, flow=5, item=6, qty=7, T=8, N=9, P=10, remark=11)
    out = []
    for r in range(2, ws.max_row + 1):
        g = lambda name: grid.get((r, col[name])) if col[name] else None
        b = g("batch")
        if not isinstance(b, (int, float)):
            continue
        item = g("item")
        if item is None:
            continue
        s, e = parse_time(g("time"))
        out.append(dict(src=k, batch=int(b), time_raw=g("time"), start=s, end=e, unit=g("unit"),
                        wh_col=g("wh"), flow=g("flow"), item=str(item).strip(), qty=g("qty"),
                        remark=g("remark"), T=g("T"), N=g("N"), P=g("P"),
                        T_block=block.get((r, col["T"]), (r, col["T"]))[0], row=r))
    df = pd.DataFrame(out)
    # 从“收发双方”解析：发方、收方
    fl = (df["flow"].astype(str).str.replace(" ", "")
          .str.replace("(", "（").str.replace(")", "）"))  # 附件4 混用半角括号
    mm = fl.str.extract(r"^(\w+?)（发）-(\w+?)（收）$")
    df["src_node"], df["dst_node"] = mm[0], mm[1]
    df["is_sub"] = df["item"].str.startswith("小计")
    return df


def load_cap() -> pd.DataFrame:
    """附件5：index=货物名，columns=U1..U12，值=单车最大装载量（发）。"""
    ws = openpyxl.load_workbook(_find(5)).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    cols = [str(h).split("\n")[0] for h in rows[0][1:13]]
    data = {str(r[0]).strip(): r[1:13] for r in rows[1:] if r[0] is not None}
    return pd.DataFrame.from_dict(data, orient="index", columns=cols)


def load_dist() -> pd.DataFrame:
    ws = openpyxl.load_workbook(_find(1)).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    names = [str(x) for x in rows[0][1:]]
    return pd.DataFrame([r[1:] for r in rows[1:]], index=[str(r[0]) for r in rows[1:]], columns=names)


if __name__ == "__main__":
    out = ROOT / "results" / "F" / "parsed"
    out.mkdir(parents=True, exist_ok=True)
    for k in (2, 3, 4):
        load(k).to_csv(out / f"附件{k}_long.csv", index=False, encoding="utf-8-sig")
    load_cap().to_csv(out / "附件5_cap.csv", encoding="utf-8-sig")
    load_dist().to_csv(out / "附件1_dist.csv", encoding="utf-8-sig")
    print("ok")
