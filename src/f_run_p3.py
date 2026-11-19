"""问题 3 运行：读取问题 2 主方案的指派，做基线与主路线，导出逐批、逐站台账。

用法：python src/f_run_p3.py
输出：results/F/p3/summary.csv、batches_{baseline,main}.csv、steps_{baseline,main}.csv、wh_load_main.csv
"""
from __future__ import annotations

import ast
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_engine as fe  # noqa: E402
import f_p3  # noqa: E402
import f_parse as fp  # noqa: E402

OUT = ROOT / "results" / "F" / "p3"


def load_assign(path, blocks):
    df = pd.read_csv(path)
    assign = {}
    for r in df.itertuples():
        if r.option == "own":
            assign[r.block] = ("own",)
        elif r.option == "REV":
            assign[r.block] = ("REV", int(r.to_batch), r.case)
        else:
            aux = ast.literal_eval(r.aux) if isinstance(r.aux, str) and r.aux.startswith("(") else (r.aux if isinstance(r.aux, str) and r.aux else None)
            assign[r.block] = ("T", int(r.to_batch), r.case, aux)
    return assign


def dump(tag, inst, sol, ev):
    rows, steps = [], []
    for b in inst.ids:
        r = ev["res"][b]
        ri, day = sol[b]
        bt = inst.batches[b]
        c = inst.cands[b][ri]
        rows.append(dict(batch=b, unit=bt.unit, T=inst.T[b], a=bt.a, e=bt.e, start=day, end=r.end_day, tau=r.tau, delta=abs(day - bt.a),
                         D=r.D, Lbar=r.Lbar, veh_km=r.veh_km, route=ri, n_cands=len(inst.cands[b]), is_base_route=(ri == inst.base_idx[b]),
                         n_leave=c["n_leave"], n_pass=c["n_pass"], iso_tau=c["tau"],
                         min_iso_tau=min(x["tau"] for x in inst.cands[b]), min_Lbar=min(x["Lbar"] for x in inst.cands[b])))
        for i, (st, lg) in enumerate(zip(c["steps"], r.logs)):
            steps.append(dict(batch=b, unit=bt.unit, seq=i, node=st.node, arrive_day=lg.arrive[0], arrive_h=lg.arrive[1],
                              start_day=lg.start[0], start_h=lg.start[1], end_day=lg.end[0], end_h=lg.end[1],
                              depart_day=lg.depart[0], depart_h=lg.depart[1], arrive=fe.fmt(lg.arrive), depart=fe.fmt(lg.depart),
                              unload=";".join(f"{g}:{v:.6f}" for g, v in st.unload.items()), load=";".join(f"{g}:{v:.6f}" for g, v in st.load.items()),
                              leave=";".join(st.leave), rejoin=st.rejoin, c_unload=lg.c_unload, c_load=lg.c_load,
                              onboard_after=lg.onboard_after, moving_T=lg.moving_T))
    pd.DataFrame(rows).to_csv(OUT / f"batches_{tag}.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(steps).to_csv(OUT / f"steps_{tag}.csv", index=False, encoding="utf-8-sig")
    wl = [dict(wh=w, day=d, veh=v, units=len(wh.units.get(d, ()))) for w, wh in ev["whs"].items() for d, v in sorted(wh.veh.items())]
    pd.DataFrame(wl).to_csv(OUT / f"wh_load_{tag}.csv", index=False, encoding="utf-8-sig")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    assign = load_assign(ROOT / "results" / "F" / "p2" / "assign_main.csv", blocks)
    t0 = time.time()
    inst = f_p3.Instance(assign, batches, blocks, cap, D)
    print(f"实例：{len(inst.ids)} 批，候选路线 {sum(len(v) for v in inst.cands.values())} 条，下界 tau≥{inst.lb_tau} L≥{inst.lb_L:.3f}，建模 {time.time() - t0:.1f}s")
    base = inst.baseline()
    evb = inst.evaluate(base)
    print("基线", evb["feasible"], evb["viol"], dict(tau=evb["tau"], L=round(evb["L"], 3), delta=evb["delta"], V=evb["V"], D=evb["D"]))
    ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
    t1 = time.time()
    sol, best = inst.improve(base, ref, log=lambda s, b: print(f"  第 {s + 1} 轮 合成分 {b[0]:.6f} V={b[1]}"))
    ev1 = inst.evaluate(sol)
    print("坐标下降后", dict(tau=ev1["tau"], L=round(ev1["L"], 3), delta=ev1["delta"], V=ev1["V"]), f"{time.time() - t1:.1f}s")
    for rnd in range(5):
        sol, best, imp = inst.improve_pairs(sol, ref)
        print(f"  成对邻域第 {rnd + 1} 轮 合成分 {best[0]:.6f} V={best[1]} 改进={imp} {time.time() - t1:.1f}s")
        if not imp:
            break
        sol, best = inst.improve(sol, ref)
    ev = inst.evaluate(sol)
    print("主路线", ev["feasible"], ev["viol"], dict(tau=ev["tau"], L=round(ev["L"], 3), delta=ev["delta"], V=ev["V"], D=ev["D"]), f"{time.time() - t1:.1f}s")
    dump("baseline", inst, base, evb)
    dump("main", inst, sol, ev)
    summ = [dict(name="下界（各批孤立最优）", tau=inst.lb_tau, L=inst.lb_L, delta=0, V=None, D=None, veh_km=None, score=0.0)]
    for name, e in (("基线", evb), ("坐标下降", ev1), ("主路线（加成对邻域）", ev)):
        summ.append(dict(name=name, tau=e["tau"], L=e["L"], delta=e["delta"], V=e["V"], D=e["D"], veh_km=e["veh_km"], score=inst.score(e, ref)[0], feasible=e["feasible"]))
    pd.DataFrame(summ).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(summ).to_string(index=False))


if __name__ == "__main__":
    main()
