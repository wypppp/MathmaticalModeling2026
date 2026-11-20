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
import f_export  # noqa: E402
import f_p2  # noqa: E402
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


REF25 = dict(l=(124, 12566.233135, 0.0), u=(134, 14412.883927, 5))  # J1 标尺：人裁 J1 时的下界与规则基线（R25），固定不随候选集变


def search(inst, ref, log=print, multistart=True):
    """基线 → 坐标下降 → 成对邻域；multistart 时再在 δ 最小的各出发日向量上做固定出发日多起点路线搜索，最后按 (合成分, V, 总里程) 打磨。"""
    t1 = time.time()
    base = inst.baseline()
    sol, best = inst.improve(base, ref)
    for rnd in range(5):
        sol, best, imp = inst.improve_pairs(sol, ref)
        log(f"  成对邻域第 {rnd + 1} 轮 合成分 {best[0]:.6f} V={best[1]} 改进={imp} {time.time() - t1:.1f}s")
        if not imp:
            break
        sol, best = inst.improve(sol, ref)
    ev1 = inst.evaluate(sol)
    if not multistart:
        return base, ev1, sol, ev1
    import f_p3_cert2 as c2
    vecs, complete, _ = c2.day_vectors(inst, dmax=ev1["delta"])
    pool = [(f_p3.key3(inst, ev1, ref), sol)]
    for vi, v in enumerate(vecs):
        s2, k2 = f_p3.fixed_day_search(inst, ref, v, 30, seed=vi, init=sol)
        log(f"  出发日向量 {vi}（δ≤{ev1['delta']}，共 {len(vecs)} 个，完整={complete}）多起点最好 {k2}  {time.time() - t1:.1f}s")
        if s2 is not None:
            pool.append((k2, s2))
    sol = min(pool, key=lambda x: x[0])[1]
    sol, k = f_p3.polish(inst, sol, ref)
    log(f"  打磨后 {k}  {time.time() - t1:.1f}s")
    return base, ev1, sol, inst.evaluate(sol)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    assign = load_assign(ROOT / "results" / "F" / "p2" / "assign_main.csv", blocks)
    t0 = time.time()
    inst = f_p3.Instance(assign, batches, blocks, cap, D)
    print(f"实例：{len(inst.ids)} 批，全部候选路线 {sum(len(v) for v in inst.cands.values())} 条（帕累托子集 {sum(len(v) for v in inst.pareto.values())} 条），"
          f"下界 tau≥{inst.lb_tau} L≥{inst.lb_L:.3f}，建模 {time.time() - t0:.1f}s")
    base0 = inst.baseline()
    evb = inst.evaluate(base0)
    print("基线", evb["feasible"], evb["viol"], dict(tau=evb["tau"], L=round(evb["L"], 3), delta=evb["delta"], V=evb["V"], D=evb["D"]))
    calc = (inst.lb_tau, inst.lb_L, evb["tau"], evb["L"], evb["delta"])
    pin = (REF25["l"][0], REF25["l"][1], REF25["u"][0], REF25["u"][1], REF25["u"][2])
    if any(abs(a - b) > 1e-5 for a, b in zip(calc, pin)):
        print(f"【报警】本次下界/基线 {calc} 与 J1 标尺 {pin} 不同；标尺仍用 R25 的值")
    ref = REF25
    base, ev1, sol, ev = search(inst, ref)
    print("主路线", ev["feasible"], ev["viol"], dict(tau=ev["tau"], L=round(ev["L"], 3), delta=ev["delta"], V=ev["V"], D=ev["D"]), f"{time.time() - t0:.1f}s")
    # 消融：R25 的做法（帕累托剪枝候选、不做多起点）
    instp = f_p3.Instance(assign, batches, blocks, cap, D, prune=True)
    _, _, solp, evp = search(instp, ref, log=lambda *_: None, multistart=False)
    print("消融（剪枝候选，R25 做法）", dict(tau=evp["tau"], L=round(evp["L"], 3), delta=evp["delta"], V=evp["V"], D=evp["D"]))
    dump("baseline", inst, base, evb)
    dump("main", inst, sol, ev)
    summ = [dict(name="下界（各批孤立最优）", tau=inst.lb_tau, L=inst.lb_L, delta=0, V=None, D=None, veh_km=None, score=0.0)]
    for name, e in (("基线", evb), ("坐标下降+成对邻域", ev1), ("主路线（加多起点与打磨）", ev), ("消融：剪枝候选（R25 做法）", evp)):
        summ.append(dict(name=name, tau=e["tau"], L=e["L"], delta=e["delta"], V=e["V"], D=e["D"], veh_km=e["veh_km"], score=inst.score(e, ref)[0], feasible=e["feasible"]))
    pd.DataFrame(summ).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    # 结果表：附件 6（问题 2）与附件 7（问题 3）用同一套新批次号
    new_id = f_export.renumber(inst.ids, {b: sol[b][1] for b in inst.ids})
    pd.DataFrame([dict(new_batch=new_id[b], orig_batch=b, unit=batches[b].unit) for b in sorted(inst.ids, key=lambda x: new_id[x])]).to_csv(
        OUT / "batch_id_map.csv", index=False, encoding="utf-8-sig")
    rows, tot, _ = f_p2.summarize(assign, batches, blocks, cap)
    tnp = {x["batch"]: (x["T"], x["N"], x["P"]) for x in rows}
    f_export.write_p2(ROOT / "results" / "F" / "问题2_results.xlsx", assign, batches, blocks, cap, new_id, tnp)
    f_export.write_p3(ROOT / "results" / "F" / "问题3_results.xlsx", 7, inst, sol, ev, new_id)
    print("附表2:", dict(批次=tot["B"], 总车数=tot["N"], 总人数=tot["P"], 代领代交等效车数=round(tot["A"], 3)))
    print("附表3:", dict(执行总时间=ev["tau"], 开始偏离=ev["delta"], 总里程=ev["D"], 载货总行驶距离=round(ev["L"], 3)))
    print(pd.DataFrame(summ).to_string(index=False))


if __name__ == "__main__":
    main()
