"""裁 Z4-c：读法 b（每笔代领代交另须满足录 2.5 的“就近”）下问题 2–4 的完整流程（spec v2.8 其余规则不变）。
结果只进附录与第十章，不写任何主结果文件。问题 3、4 为启发式搜索（不跑证书）。
用法：python src/f_run_d2b_full.py [问题4每种子秒数=300]
输出：results/F/d2b/{summary.csv, assign_p2.csv, p3_batches.csv, p4_assign.csv, p4_batches.csv}
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_p2  # noqa: E402
import f_p3  # noqa: E402
import f_p4  # noqa: E402
import f_parse as fp  # noqa: E402
import f_run_p3  # noqa: E402
from f_run_p2 import check_routes, solve_checked  # noqa: E402

OUT = ROOT / "results" / "F" / "d2b"


def assign_rows(a, batches, blocks, cap):
    return [dict(block=k.id, batch=k.batch, owner=k.owner, w=k.w, dir=k.dir, option=a[k.id][0],
                 to_batch=(a[k.id][1] if a[k.id][0] != "own" else k.batch), case=(a[k.id][2] if a[k.id][0] != "own" else "")) for k in blocks]


def batch_rows(inst, sol, ev):
    return [dict(batch=b, unit=inst.batches[b].unit, route=sol[b][0], start=sol[b][1], tau=ev["res"][b].tau, Lbar=ev["res"][b].Lbar,
                 D=ev["res"][b].D) for b in inst.ids]


def main():
    lim = float(sys.argv[1]) if len(sys.argv) > 1 else 300
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    summ = []
    # ---- 问题 2：六级字典序（同主流程），就近对所有代办生效
    r, routes, forbid = solve_checked(batches, blocks, cap, D, near_all=True)
    rt = f_p2.solve(batches, blocks, cap, D, forbid=forbid, near_all=True, alternatives=2000)
    ties = [rt["assign"]] + rt["alts"]
    assert len(rt["alts"]) < 2000, "并列解枚举未穷尽"
    cand = []
    for k, a in enumerate(ties):
        _, tot_k, _ = f_p2.summarize(a, batches, blocks, cap)
        if all(v["cands"] for v in check_routes(a, batches, blocks, cap, D).values()):
            cand.append(((tot_k["N"], tot_k["P"]), k))
    best = min(c for c, _ in cand)
    picks = [k for c, k in cand if c == best]
    a2 = ties[picks[0]]
    _, tot2, _ = f_p2.summarize(a2, batches, blocks, cap)
    pd.DataFrame(assign_rows(a2, batches, blocks, cap)).to_csv(OUT / "assign_p2.csv", index=False, encoding="utf-8-sig")
    summ.append(dict(问题="问题2", 批次=tot2["B"], 总车数=tot2["N"], 总人数=tot2["P"], 运力合计=tot2["T"], 代领代交等效车数=tot2["A"],
                     批次仓库对=tot2["pairs"], 失衡度=tot2["E"], 四级并列数=len(ties), NP并列数=len(picks)))
    print(summ[-1], f"{time.time() - t0:.0f}s", flush=True)
    # ---- 问题 3：同主流程的搜索（全候选、多起点），标尺取本指派的孤立下界与规则基线
    inst = f_p3.Instance(a2, batches, blocks, cap, D)
    base = inst.baseline()
    evb = inst.evaluate(base)
    ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
    _, _, sol3, ev3 = f_run_p3.search(inst, ref, log=lambda *_: None)
    assert ev3["feasible"], ev3["viol"]
    pd.DataFrame(batch_rows(inst, sol3, ev3)).to_csv(OUT / "p3_batches.csv", index=False, encoding="utf-8-sig")
    summ.append(dict(问题="问题3", 执行总时间=ev3["tau"], 载货总行驶距离=ev3["L"], 开始偏离=ev3["delta"], V=ev3["V"], 调运总里程=ev3["D"],
                     合成分=inst.score(ev3, ref)[0], 下界_天=inst.lb_tau, 下界_km=inst.lb_L, 基线_天=evb["tau"], 基线_km=evb["L"], 基线_偏离=evb["delta"]))
    print(summ[-1], f"{time.time() - t0:.0f}s", flush=True)
    # ---- 问题 4：改派搜索（剪枝候选，起点为问题 3 方案），再在全候选上重做路线
    nB = tot2["B"]
    rW = f_p2.solve(batches, blocks, cap, D, fix_batches=nB, levels=("U9", "W", "A"), near_all=True)
    P = f_p4.P4(batches, blocks, cap, D, nB, ref, (0.0, tot2["E"]), (rW["stats"]["W"], tot2["pairs"]), u9_min=5, near_all=True)
    P.log = lambda *_: None
    instp = P.instance(a2)
    solp = {}
    for b in inst.ids:
        c_main = inst.cands[b][sol3[b][0]]
        j = next((i for i, c in enumerate(instp.cands[b]) if c["steps"] == c_main["steps"]), None)
        if j is None:
            instp.cands[b] = instp.cands[b] + [c_main]
            j = len(instp.cands[b]) - 1
        solp[b] = (j, sol3[b][1])
        P.cache[instp.sig[b]] = (instp.cands[b], instp.base_idx[b], instp.pareto[b])
    runs = []
    for sd in range(3):
        a4, s4, i4, sc4, hist = P.search(a2, solp, seed=sd, time_limit=lim)
        runs.append((sd, a4, s4, i4, sc4))
        print(f"  问题4 种子 {sd}: 合成分 {sc4:.4f}，接受改派 {len(hist) - 1} 步", flush=True)
    sd, a4, s4, i4, sc4 = min(runs, key=lambda x: x[4])
    instf = f_p3.Instance(a4, batches, blocks, cap, D)
    init = {}
    for b in instf.ids:
        steps = i4.cands[b][s4[b][0]]["steps"]
        idx = [i for i, c in enumerate(instf.cands[b]) if c["steps"] == steps]
        init[b] = (idx[0] if idx else instf.base_idx[b], s4[b][1])
    _, _, solf, evf = f_run_p3.search(instf, ref, log=lambda *_: None, init=init)
    assert evf["feasible"], evf["viol"]
    scf, det = P.score(a4, evf)
    sc3, d3 = P.score(a2, ev3)
    pd.DataFrame(assign_rows(a4, batches, blocks, cap)).to_csv(OUT / "p4_assign.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(batch_rows(instf, solf, evf)).to_csv(OUT / "p4_batches.csv", index=False, encoding="utf-8-sig")
    for nm, dd, s in (("问题4对照：问题3方案", d3, sc3), ("问题4", det, scf)):
        summ.append(dict(问题=nm, 合成分=s, 批次=dd["B"], 总车数=dd["N"], 总人数=dd["P"], 代领代交等效车数=dd["A"], 执行总时间=dd["tau"], 开始偏离=dd["delta"],
                         调运总里程=dd["D"], 载货总行驶距离=dd["L"], 失衡度=dd["E"], 批次仓库对=dd["pairs"], V=dd["V"]))
        print(summ[-1], flush=True)
    pd.DataFrame(summ).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(f"完成 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
