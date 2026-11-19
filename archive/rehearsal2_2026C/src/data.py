"""数据层：读取附件，统一为自然日 144 个时段、每时段电量 kWh（spec §2）。

约定：附件中时刻 t 的功率读数代表区间 [t-10min, t]，所以附件第 i 列（i=0..143）
就是自然日第 i 个时段（0:00-0:10 为第 0 个）。电量 = 功率 / 6。
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
ATT = ROOT / "problem" / "2026C" / "original" / "附件"
TPL = ATT / "附件5_结果模板"

NSLOT = 144
DT_H = 1.0 / 6.0


def slot_label(i: int) -> str:
    """自然时段标签，例如 0 -> '0:00-0:10'，143 -> '23:50-24:00'。"""
    a, b = i * 10, (i + 1) * 10
    return f"{a // 60}:{a % 60:02d}-{b // 60}:{b % 60:02d}"


def _rows(path: Path, sheet: str | None = None):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    return list(ws.iter_rows(values_only=True))


@lru_cache(maxsize=None)
def load_a1():
    """附件 1：返回 price(元/kWh)、L(kWh)、G(kWh)，各 144 个。"""
    rows = _rows(ATT / "附件1.xlsx")[1:]
    assert len(rows) == NSLOT
    p = np.array([r[1] for r in rows], float)
    L = np.array([r[2] for r in rows], float) * DT_H
    G = np.array([r[3] for r in rows], float) * DT_H
    return p, L, G


def _daily_grid(path: Path, sheet: str | None = None):
    rows = _rows(path, sheet)[1:]
    dates = [r[0].date() if isinstance(r[0], dt.datetime) else r[0] for r in rows]
    arr = np.array([r[1 : 1 + NSLOT] for r in rows], float)
    assert arr.shape == (365, NSLOT), arr.shape
    return dates, arr


@lru_cache(maxsize=None)
def load_a2():
    """附件 2：dates(365)、L、G（kWh，形状 365×144）。"""
    d1, L = _daily_grid(ATT / "附件2.xlsx", "小区负载")
    d2, G = _daily_grid(ATT / "附件2.xlsx", "光伏发电实际功率")
    assert d1 == d2
    return d1, L * DT_H, G * DT_H


@lru_cache(maxsize=None)
def load_a4():
    """附件 4：dates、price（元/kWh，365×144）。"""
    return _daily_grid(ATT / "附件4.xlsx")


@lru_cache(maxsize=None)
def load_a3():
    """附件 3：{(date, issue_hour): 24 个整点预报功率 kW}；第 k 个值对应 issue_hour+k+1 时。"""
    rows = _rows(ATT / "附件3.xlsx")[1:]
    out, cur = {}, None
    for r in rows:
        if r[0] not in (None, ""):
            y, m, d = (int(x) for x in str(r[0]).split("-"))
            cur = dt.date(y, m, d)
        hh = int(str(r[1]).split(":")[0])
        out[(cur, hh)] = np.array(r[2:26], float)
    assert len(out) == 365 * 4
    return out


def day_index(d: dt.date) -> int:
    return (d - dt.date(2025, 1, 1)).days
