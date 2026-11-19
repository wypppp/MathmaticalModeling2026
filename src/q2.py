"""Q2 基线（H1/H8 的基线配置）：P0 预测 + C0 确定性计划 + X0 规则执行，全年因果回放。

运行：python -m src.q2
- P0 预测：上周同一天的实际 L、G（1 月 1–7 日没有上周数据，用附件 1 代表日）。
- C0 计划：用预测值求确定性 LP；初值 = 当天 0:00 的实际 SOC；日末 SOC = Q1 稳态值（锚点 T1）。
- X0 执行：储能按计划净输出运行，实际偏差先用"高于计划轨迹的富余电量"弥补；
  若要动用低于计划轨迹的电量，只有当前电价不低于今天剩余计划放电时段的最高电价时才放电（保电惜放，H3），
  否则紧急购电。富余电量由回测器自动充入储能。
- 神谕下界：当天实际值已知、同一初值与同一日末 SOC 下的确定性最优（evidence P8）。
"""
from __future__ import annotations

import datetime as dt
import json
import shutil

import numpy as np
import openpyxl

from . import checker, data, lp
from .q1 import BLOCKS, SAMPLE_SLOTS, git_rev
from .sim import EMERG, execute_day

OUT = data.ROOT / "results" / "q2"
S_INIT = 6000.0
REPORT_DAYS = [dt.date(2025, 3, 20), dt.date(2025, 6, 21), dt.date(2025, 9, 23), dt.date(2025, 12, 21)]


def q1_anchor() -> float:
    sol = np.load(data.ROOT / "results" / "q1" / "q1_solution.npz")
    return float(sol["S"][0])


class P0Forecaster:
    """上周同一天。只使用 d 之前的数据。"""

    def __init__(self, L, G):
        self.L, self.G = L, G
        _, self.L1, self.G1 = data.load_a1()

    def forecast(self, di):
        if di >= 7:
            return self.L[di - 7].copy(), self.G[di - 7].copy()
        return self.L1.copy(), self.G1.copy()


class X0Policy:
    """规则执行：跟随计划，偏差用富余电量吸收，动用计划内电量时保电惜放。"""

    def __init__(self, plan: lp.LPResult, Lf, Gf, price):
        self.plan, self.price = plan, price
        self.u_plan = plan.d - plan.c
        self.need_plan = Lf - Gf - plan.q
        # 剩余计划放电时段的最高电价（从 t 往后，含 t）
        dis_price = np.where(plan.d > 1e-6, price, 0.0)
        self.future_max = np.maximum.accumulate(dis_price[::-1])[::-1]

    def __call__(self, t, S, b_t, L_t, G_t):
        need = L_t - G_t - b_t
        u = self.u_plan[t] + (need - self.need_plan[t])  # 完全弥补偏差所需的净输出
        if u <= self.u_plan[t]:
            return u  # 需求比计划少：多充或少放，回测器会裁剪
        # 需要额外放电：先用高于计划轨迹的富余电量
        headroom = max(0.0, (S - self.plan.S[t]) * 0.9)
        extra = u - self.u_plan[t]
        if extra <= headroom:
            return u
        later = self.future_max[t + 1] if t + 1 < len(self.price) else 0.0
        if self.price[t] >= later:
            return u  # 当前电价不低于之后的计划放电电价：现在放电更划算
        return self.u_plan[t] + headroom  # 保电惜放：剩余缺口紧急购电


def run_year(forecaster_cls=P0Forecaster, policy_cls=X0Policy, anchor=None):
    dates, L, G = data.load_a2()
    price, _, _ = data.load_a1()  # Q2 电价每天相同
    anchor = q1_anchor() if anchor is None else anchor
    fc = forecaster_cls(L, G)
    S0 = S_INIT
    days = []
    for di, d in enumerate(dates):
        Lf, Gf = fc.forecast(di)
        plan = lp.solve_day(price, Lf, Gf, S0=S0, S_end=anchor)
        pol = policy_cls(plan, Lf, Gf, price)
        led = execute_day(plan.q, L[di], G[di], S0, pol)
        cost = led.cost(price)
        errs = checker.check_ledger(led.b, led.L, led.G, led.c, led.d, led.e, led.w, led.S, price, cost)
        orc = lp.solve_day(price, L[di], G[di], S0=S0, S_end=float(led.S[-1]), lexicographic=False)
        days.append(dict(date=d, led=led, plan=plan, cost=cost, oracle=orc.cost, errs=errs))
        S0 = float(led.S[-1])
    return days, price


def merge_emergency(e, tol=1e-6):
    """连续的紧急购电时段合并为一行：[(标签, kWh)]。"""
    out, i, n = [], 0, len(e)
    while i < n:
        if e[i] > tol:
            j = i
            while j + 1 < n and e[j + 1] > tol:
                j += 1
            a, b = i * 10, (j + 1) * 10
            out.append((f"{a // 60}:{a % 60:02d}-{b // 60}:{b % 60:02d}", float(e[i:j + 1].sum())))
            i = j + 1
        else:
            i += 1
    return out


def write_result_multi(days, price, template, path, adjust=None):
    """写 result2/4-2 类工作簿（2.1–12.31）。adjust 预留给 Q3 的调整表。"""
    shutil.copy(template, path)
    wb = openpyxl.load_workbook(path)
    rep = [x for x in days if x["date"] >= dt.date(2025, 2, 1)]
    ws = wb["计划购电量"]
    for i in range(data.NSLOT):
        ws.cell(row=1, column=2 + i, value=data.slot_label(i))
    for r, x in enumerate(rep):
        ws.cell(row=2 + r, column=1, value=dt.datetime.combine(x["date"], dt.time()))
        q = x["led"].b
        for i in range(data.NSLOT):
            ws.cell(row=2 + r, column=2 + i, value=round(float(q[i]), 4))
        ws.cell(row=2 + r, column=2 + data.NSLOT, value=round(float(q.sum()), 4))
        ws.cell(row=2 + r, column=3 + data.NSLOT, value=round(float((price * q).sum()), 4))
    ws = wb["充放电量"]
    ws.delete_rows(2, ws.max_row)
    row = 2
    for x in rep:
        led = x["led"]
        for k, (a, b) in enumerate(BLOCKS):
            ws.cell(row=row, column=1, value=dt.datetime.combine(x["date"], dt.time()) if k == 0 else None)
            ws.cell(row=row, column=2, value=f"{a // 6}:00-{b // 6}:00")
            ws.cell(row=row, column=3, value=round(float(led.c[a:b].sum()), 4))
            ws.cell(row=row, column=4, value=round(float(led.d[a:b].sum()), 4))
            if k == 0:
                ws.cell(row=row, column=5, value="0:00"); ws.cell(row=row, column=6, value=round(float(led.S[0]), 4))
            if k == 1:
                ws.cell(row=row, column=5, value="24:00"); ws.cell(row=row, column=6, value=round(float(led.S[-1]), 4))
            row += 1
    ws = wb["紧急购电量"]
    ws.delete_rows(2, ws.max_row)
    row = 2
    for x in rep:
        blocks = merge_emergency(x["led"].e)
        if not blocks:
            ws.cell(row=row, column=1, value=dt.datetime.combine(x["date"], dt.time()))
            ws.cell(row=row, column=2, value="无"); ws.cell(row=row, column=3, value=0)
            row += 1
            continue
        for k, (lab, kwh) in enumerate(blocks):
            ws.cell(row=row, column=1, value=dt.datetime.combine(x["date"], dt.time()) if k == 0 else None)
            ws.cell(row=row, column=2, value=lab); ws.cell(row=row, column=3, value=round(kwh, 4))
            row += 1
    wb.save(path)


def summarize(days, price, tag):
    rep = [x for x in days if x["date"] >= dt.date(2025, 2, 1)]
    allerrs = [(str(x["date"]), x["errs"]) for x in days if x["errs"]]
    cost = sum(x["cost"] for x in rep); orc = sum(x["oracle"] for x in rep)
    plan_cost = sum(float((price * x["led"].b).sum()) for x in rep)
    em_cost = sum(float(EMERG * (price * x["led"].e).sum()) for x in rep)
    em_kwh = sum(float(x["led"].e.sum()) for x in rep)
    w_kwh = sum(float(x["led"].w.sum()) for x in rep)
    oracle_viol = [str(x["date"]) for x in days if x["oracle"] > x["cost"] + 1e-6]
    # 紧急购电按小时分布
    e_by_hour = np.zeros(24)
    for x in rep:
        e_by_hour += x["led"].e.reshape(24, 6).sum(1)
    wd = {}
    for x in rep:
        k = x["date"].strftime("%a"); wd.setdefault(k, []).append(float(x["led"].b.sum()))
    tables = {}
    for d in REPORT_DAYS:
        x = next(y for y in days if y["date"] == d); led = x["led"]
        tables[str(d)] = {
            "表1": {**{data.slot_label(i): round(float(led.b[i]), 4) for i in SAMPLE_SLOTS},
                    "全天购电量": round(float(led.b.sum()), 4), "全天购电费": round(float((price * led.b).sum()), 4)},
            "表2": {**{f"{a//6}:00-{b//6}:00": [round(float(led.c[a:b].sum()), 4), round(float(led.d[a:b].sum()), 4)] for a, b in BLOCKS},
                    "0:00储电量": round(float(led.S[0]), 4), "24:00储电量": round(float(led.S[-1]), 4)},
            "表3_紧急购电": [(lab, round(k, 4)) for lab, k in merge_emergency(led.e)],
            "当日总费用": round(x["cost"], 4), "当日神谕下界": round(x["oracle"], 4),
        }
    return {
        "配置": tag, "代码版本": git_rev(),
        "检查器": allerrs or "全部通过（365 天）",
        "神谕下界违例天数": oracle_viol,
        "2.1-12.31 总费用": round(cost, 2), "其中计划购电费": round(plan_cost, 2), "其中紧急购电费": round(em_cost, 2),
        "神谕下界": round(orc, 2), "相对神谕的差距%": round(100 * (cost - orc) / orc, 2),
        "紧急购电量kWh": round(em_kwh, 1), "富余消纳kWh": round(w_kwh, 1),
        "2.1 的 0:00 SOC": round(float(next(x for x in days if x["date"] == dt.date(2025, 2, 1))["led"].S[0]), 2),
        "紧急购电量按小时": [round(v, 1) for v in e_by_hour],
        "日均计划量按星期": {k: round(float(np.mean(v)), 1) for k, v in wd.items()},
        "指定日表格": tables,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    days, price = run_year()
    s = summarize(days, price, "Q2 基线：P0 + C0（锚点 T1）+ X0")
    (OUT / "q2_baseline_summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    write_result_multi(days, price, data.TPL / "result2.xlsx", OUT / "result2_baseline.xlsx")
    print(json.dumps({k: v for k, v in s.items() if k != "指定日表格"}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
