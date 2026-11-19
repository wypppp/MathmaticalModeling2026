"""问题 2 正式运行：整数规划 + 里程上限回查（no-good 割迭代）+ 对照方案 + 台账与附件 6。

用法：python src/f_run_p2.py
输出：results/F/p2/ 下的 assign_*.csv（逐块指派）、batches_*.csv（逐批未舍入台账）、summary.csv、问题2_results.xlsx
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
import f_parse as fp  # noqa: E402
import f_routes as fr  # noqa: E402

OUT = ROOT / "results" / "F" / "p2"


def solve_checked(batches, blocks, cap, D, **kw):
    """求解并回查每个最终批次是否存在 ≤2000 km 的合规路线；不存在则对该批次的转入集合加割后重解。"""
    forbid, it = [], 0
    while True:
        it += 1
        r = f_p2.solve(batches, blocks, cap, D, forbid=forbid, **kw)
        if r["assign"] is None:
            return r, None, forbid
        groups = fr.batch_groups(r["assign"], batches, blocks, cap)
        bad, routes = [], {}
        for b, gs in groups.items():
            T = fr.batch_T(gs, batches[b].unit)[0]
            nd, n_all = fr.candidates(b, batches[b].unit, T, gs, D)
            routes[b] = dict(T=T, cands=nd, n_all=n_all)
            if not nd:
                bad.append(b)
        if not bad:
            r["iters"] = it
            return r, routes, forbid
        for b in bad:
            S = [(kid, o) for kid, o in r["assign"].items() if o[0] != "own" and (o[1] == b or (o[0] == "T" and o[2] == "R4" and o[3][1] == b))]
            assert S, f"批 {b} 无转入却无合规路线"
            forbid.append(S)


def ledger(tag, r, routes, batches, blocks, cap):
    rows, tot, flow = f_p2.summarize(r["assign"], batches, blocks, cap)
    for x in rows:
        c = routes[x["batch"]]
        assert c["T"] == x["T"], (x["batch"], c["T"], x["T"])
        best = min(c["cands"], key=lambda e: e["D"])
        x.update(min_D=best["D"], n_routes=c["n_all"], n_nondominated=len(c["cands"]),
                 min_tau=min(e["tau"] for e in c["cands"]), min_Lbar=min(e["Lbar"] for e in c["cands"]))
    pd.DataFrame(rows).to_csv(OUT / f"batches_{tag}.csv", index=False, encoding="utf-8-sig")
    a = []
    for k in blocks:
        o = r["assign"][k.id]
        a.append(dict(block=k.id, batch=k.batch, owner=k.owner, w=k.w, dir=k.dir, h=k.h, inner=k.inner,
                      s_owner=k.s(cap, k.owner), option=o[0], to_batch=(o[1] if o[0] != "own" else k.batch),
                      to_unit=(batches[o[1]].unit if o[0] != "own" else k.owner), case=(o[2] if o[0] != "own" else ""),
                      aux=(str(o[3]) if o[0] == "T" and o[3] else ""),
                      s_exec=k.s(cap, batches[o[1]].unit if o[0] != "own" else k.owner)))
    pd.DataFrame(a).to_csv(OUT / f"assign_{tag}.csv", index=False, encoding="utf-8-sig")
    return rows, tot, flow


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    summ = []
    variants = [("main", {}), ("noR4", dict(allow_R4=False)), ("shared_only", dict(only_shared=True)),
                ("c6_literal", dict(levels=("B", "A", "V0"), c6="maximal")), ("near149", dict(near=149)),
                ("norev", dict(allow_rev=False))]
    keep = {}
    for tag, kw in variants:
        t0 = time.time()
        r, routes, forbid = solve_checked(batches, blocks, cap, D, **kw)
        rows, tot, flow = ledger(tag, r, routes, batches, blocks, cap)
        st = r["stats"]
        summ.append(dict(variant=tag, B=tot["B"], B_bound=st.get("B_bound"), N=tot["N"], P=tot["P"], T=tot["T"], A=tot["A"],
                         A_bound=st.get("A_bound"), V0=st.get("V0"), U9_to_U6=st.get("U9"), pairs=tot["pairs"], E=tot["E"],
                         max_minD=max(x["min_D"] for x in rows), sum_min_tau=sum(x["min_tau"] for x in rows),
                         sum_min_Lbar=sum(x["min_Lbar"] for x in rows), n_cuts=len(forbid), iters=r["iters"], seconds=time.time() - t0))
        keep[tag] = (r, routes, rows, tot, flow)
        print(tag, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in summ[-1].items()})
    # 折衷曲线：固定批次数，最小化代领代交量
    r0 = keep["main"][0]
    Bmin = r0["stats"]["B"]
    for nb in range(Bmin, 47):
        r = f_p2.solve(batches, blocks, cap, D, fix_batches=nb, levels=("U9", "A"))
        if r["assign"] is None:
            continue
        _, tot, _ = f_p2.summarize(r["assign"], batches, blocks, cap)
        summ.append(dict(variant=f"curve_B{nb}", B=tot["B"], A=tot["A"], N=tot["N"], P=tot["P"], T=tot["T"], pairs=tot["pairs"], E=tot["E"],
                         U9_to_U6=r["stats"].get("U9")))
        if tot["A"] < 1e-9:
            break
    pd.DataFrame(summ).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    fl = keep["main"][4]
    pd.DataFrame([dict(executor=x, owner=y, s=v) for (x, y), v in sorted(fl.items())]).to_csv(OUT / "flow_main.csv", index=False, encoding="utf-8-sig")
    print("curve:", [(s["B"], round(s["A"], 3)) for s in summ if s["variant"].startswith("curve")])


if __name__ == "__main__":
    main()
