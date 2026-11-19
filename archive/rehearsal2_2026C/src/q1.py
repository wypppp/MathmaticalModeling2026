"""Q1：附件 1 代表日的确定性日循环调度。运行：python -m src.q1"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import openpyxl

from . import checker, data, lp
from .sim import ETA, PMAX

OUT = data.ROOT / "results" / "q1"
SAMPLE_SLOTS = [60, 72, 84, 96, 108, 120]  # 10:00、12:00、…、20:00 起始的 10 分钟（0 起计）
BLOCKS = [(i * 24, (i + 1) * 24) for i in range(6)]  # 0:00-4:00 … 20:00-24:00


def git_rev():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=data.ROOT, text=True).strip()
    except Exception:
        return "unknown"


def ledger_check(res, p, L, G):
    w = res.q + G + res.d - res.c - L
    e = np.zeros_like(L)
    return checker.check_ledger(res.q, L, G, res.c, res.d, e, np.maximum(w, 0), res.S, p, res.cost)


def write_result1(res, path: Path):
    shutil.copy(data.TPL / "result1.xlsx", path)
    wb = openpyxl.load_workbook(path)
    ws = wb["计划购电量"]
    for i in range(data.NSLOT):
        ws.cell(row=2 + i, column=1, value=data.slot_label(i))
        ws.cell(row=2 + i, column=2, value=round(float(res.q[i]), 4))
    ws2 = wb["充放电量"]
    for k, (a, b) in enumerate(BLOCKS):
        ws2.cell(row=2 + k, column=2, value=round(float(res.c[a:b].sum()), 4))
        ws2.cell(row=2 + k, column=3, value=round(float(res.d[a:b].sum()), 4))
    ws2.cell(row=2, column=5, value=round(float(res.S[0]), 4))
    ws2.cell(row=3, column=5, value=round(float(res.S[-1]), 4))
    wb.save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p, L, G = data.load_a1()
    base = lp.solve_day(p, L, G, S0=None, S_end="cyclic")
    mip = lp.solve_day_milp(p, L, G, S0=None, S_end="cyclic")
    errs = ledger_check(base, p, L, G)

    sens = {}
    for name, kw in {
        "S0固定6000": dict(S0=6000.0),
        "S0固定1200": dict(S0=1200.0),
        "S0固定10800": dict(S0=10800.0),
        "功率×0.5": dict(pmax=PMAX * 0.5),
        "功率×2": dict(pmax=PMAX * 2),
        "效率按往返90%": dict(eta=float(np.sqrt(0.9))),
        "SOC区间0-12000": dict(smin=0.0, smax=12000.0),
        "无储能": dict(pmax=0.0),
    }.items():
        r = lp.solve_day(p, L, G, S_end="cyclic", **kw)
        sens[name] = round(r.cost, 4)

    table1 = {data.slot_label(i): round(float(base.q[i]), 4) for i in SAMPLE_SLOTS}
    table2 = {f"{a//6}:00-{b//6}:00": {"充电量": round(float(base.c[a:b].sum()), 4), "放电量": round(float(base.d[a:b].sum()), 4)} for a, b in BLOCKS}
    summary = {
        "代码版本": git_rev(),
        "求解器": "scipy.optimize.linprog(method='highs') + 字典序第二阶段；校验用 scipy.optimize.milp",
        "全天购电费_LP": round(base.cost, 6),
        "全天购电费_MILP": round(mip.cost, 6),
        "MILP_gap": mip.mip_gap,
        "LP与MILP差": abs(base.cost - mip.cost),
        "全天购电量": round(float(base.q.sum()), 4),
        "S_0:00": round(float(base.S[0]), 4),
        "S_24:00": round(float(base.S[-1]), 4),
        "充电达功率上限的时段数": int((base.c > PMAX - 1e-6).sum()),
        "放电达功率上限的时段数": int((base.d > PMAX - 1e-6).sum()),
        "弃光或富余电量kWh": round(float(np.maximum(base.q + G + base.d - base.c - L, 0).sum()), 4),
        "检查器": errs or "全部通过",
        "表1_指定时段购电量": table1,
        "表2_充放电量": table2,
        "敏感性_全天购电费": sens,
        "充电时段": [data.slot_label(i) for i in np.where(base.c > 1e-6)[0]],
        "放电时段": [data.slot_label(i) for i in np.where(base.d > 1e-6)[0]],
    }
    (OUT / "q1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    np.savez(OUT / "q1_solution.npz", q=base.q, c=base.c, d=base.d, S=base.S, soc_dual=base.soc_dual)
    write_result1(base, OUT / "result1.xlsx")
    print(json.dumps({k: summary[k] for k in list(summary)[:13]}, ensure_ascii=False, indent=1))
    print("敏感性:", sens)


if __name__ == "__main__":
    main()
