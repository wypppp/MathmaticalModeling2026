"""问题 4 运行：以问题 3 的方案为基线，做联合邻域搜索；导出附件 8、台账和对比表。

用法：python src/f_run_p4.py [时间上限秒，默认 1500]
输出：results/F/p4/{summary.csv, history_*.csv, assign_main.csv, batches_main.csv, steps_main.csv, flow_main.csv}，results/F/问题4_results.xlsx、问题4_附件6格式.xlsx
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_export  # noqa: E402
import f_p2  # noqa: E402
import f_p3  # noqa: E402
import f_p4  # noqa: E402
import f_parse as fp  # noqa: E402
from f_run_p3 import dump as dump3, load_assign  # noqa: E402
import f_run_p3  # noqa: E402

OUT = ROOT / "results" / "F" / "p4"


def main():
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else 1500
    OUT.mkdir(parents=True, exist_ok=True)
    f_run_p3.OUT = OUT
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    a3 = load_assign(ROOT / "results" / "F" / "p2" / "assign_main.csv", blocks)
    # 问题 3 的方案（重建以得到与缓存一致的路线编号）
    inst3 = f_p3.Instance(a3, batches, blocks, cap, D)
    base = inst3.baseline()
    evb = inst3.evaluate(base)
    ref3 = dict(l=(inst3.lb_tau, inst3.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
    sol3, _ = inst3.improve(base, ref3)
    ev3 = inst3.evaluate(sol3)
    _, tot3, _ = f_p2.summarize(a3, batches, blocks, cap)
    nB = tot3["B"]
    rW = f_p2.solve(batches, blocks, cap, D, fix_batches=nB, levels=("U9", "W", "A"))
    Wmin = rW["stats"]["W"]
    print(f"问题 3 方案：批次 {nB} 天 {ev3['tau']} L {ev3['L']:.3f} 偏离 {ev3['delta']} E {tot3['E']:.4f} 仓库对 {tot3['pairs']}；{nB} 批下仓库对最小 {Wmin}")
    P = f_p4.P4(batches, blocks, cap, D, nB, ref3, (0.0, tot3["E"]), (Wmin, tot3["pairs"]), u9_min=5)
    P.cache.update(inst3.__dict__.get("_dummy", {}))
    runs = []
    # 起点一：问题 3 的方案
    SEEDS = range(6)
    quiet = lambda *x: None
    for sd in SEEDS:
        P.log = print if sd == 0 else quiet
        a, sol, inst, sc, hist = P.search(a3, sol3, seed=sd, time_limit=limit)
        pd.DataFrame(hist).to_csv(OUT / f"history_from_p3_seed{sd}.csv", index=False, encoding="utf-8-sig")
        runs.append((f"自问题3出发/种子{sd}", a, sol, inst, sc))
        print(f"  种子 {sd}: 合成分 {sc:.4f}，接受改派 {len(hist) - 1} 步")
    # 起点二：仓库对最少的整数规划解
    aW = rW["assign"]
    instW = P.instance(aW)
    if instW.routable:
        sW = instW.baseline()
        if instW.evaluate(sW)["feasible"]:
            sW, _ = instW.improve(sW, ref3)
            for sd in SEEDS:
                P.log = print if sd == 0 else quiet
                a2, sol2, inst2, sc2, hist2 = P.search(aW, sW, seed=sd, time_limit=limit)
                pd.DataFrame(hist2).to_csv(OUT / f"history_from_minW_seed{sd}.csv", index=False, encoding="utf-8-sig")
                runs.append((f"自仓库对最少解出发/种子{sd}", a2, sol2, inst2, sc2))
                print(f"  种子 {sd}: 合成分 {sc2:.4f}，接受改派 {len(hist2) - 1} 步")
        else:
            print("仓库对最少解：基线排不出，跳过该起点")
    name, a, sol, inst, sc = min(runs, key=lambda r: r[4])
    # 收尾：对最终指派做一次完整的坐标下降
    sol, _ = inst.improve(sol, ref3)
    ev = inst.evaluate(sol)
    sc, det = P.score(a, ev)
    assert ev["feasible"] and P.static_ok(a)
    summ = []
    s3, d3 = P.score(a3, ev3)
    for nm, dd, s in (("问题3方案", d3, s3), ("问题4方案（" + name + "）", det, sc)):
        summ.append(dict(方案=nm, 合成分=s, 调运总批次=dd["B"], 调运总车数=dd["N"], 出动总人数=dd["P"], 代领代交等效车数=dd["A"], 人员调动执行总时间=dd["tau"],
                         开始偏离=dd["delta"], 调运总里程=dd["D"], 载货车辆总行驶距离=dd["L"], 失衡度=dd["E"], 批次仓库对=dd["pairs"], 车公里=dd["veh_km"], V=dd["V"]))
    for nm, a_, sol_, inst_, s_ in runs:
        e_ = inst_.evaluate(sol_)
        _, dd = P.score(a_, e_)
        summ.append(dict(方案="搜索终点：" + nm, 合成分=s_, 调运总批次=dd["B"], 调运总车数=dd["N"], 出动总人数=dd["P"], 代领代交等效车数=dd["A"],
                         人员调动执行总时间=dd["tau"], 开始偏离=dd["delta"], 调运总里程=dd["D"], 载货车辆总行驶距离=dd["L"], 失衡度=dd["E"],
                         批次仓库对=dd["pairs"], 车公里=dd["veh_km"], V=dd["V"]))
    sdf = pd.DataFrame(summ)
    sdf.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(sdf.T.to_string())
    # 台账与结果表
    dump3("main", inst, sol, ev)
    rows = []
    for k in blocks:
        o = a[k.id]
        rows.append(dict(block=k.id, batch=k.batch, owner=k.owner, w=k.w, dir=k.dir, h=k.h, inner=k.inner, s_owner=k.s(cap, k.owner), option=o[0],
                         to_batch=(o[1] if o[0] != "own" else k.batch), to_unit=(batches[o[1]].unit if o[0] != "own" else k.owner),
                         case=(o[2] if o[0] != "own" else ""), aux=(str(o[3]) if o[0] == "T" and o[3] else ""),
                         s_exec=k.s(cap, batches[o[1]].unit if o[0] != "own" else k.owner), changed_vs_p3=(o != a3[k.id])))
    pd.DataFrame(rows).to_csv(OUT / "assign_main.csv", index=False, encoding="utf-8-sig")
    rws, tot, flow = f_p2.summarize(a, batches, blocks, cap)
    pd.DataFrame([dict(executor=x, owner=y, s=v) for (x, y), v in sorted(flow.items())]).to_csv(OUT / "flow_main.csv", index=False, encoding="utf-8-sig")
    new_id = f_export.renumber(inst.ids, {b: sol[b][1] for b in inst.ids})
    pd.DataFrame([dict(new_batch=new_id[b], orig_batch=b, unit=batches[b].unit) for b in sorted(inst.ids, key=lambda x: new_id[x])]).to_csv(
        OUT / "batch_id_map.csv", index=False, encoding="utf-8-sig")
    tnp = {x["batch"]: (x["T"], x["N"], x["P"]) for x in rws}
    f_export.write_p2(ROOT / "results" / "F" / "问题4_附件6格式.xlsx", a, batches, blocks, cap, new_id, tnp)
    f_export.write_p3(ROOT / "results" / "F" / "问题4_results.xlsx", 8, inst, sol, ev, new_id)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"总用时 {time.time() - t0:.0f}s")
