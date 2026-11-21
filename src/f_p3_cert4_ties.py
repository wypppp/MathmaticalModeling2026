"""问题 3 证书的并列核查（spec v2.6，J1 第三级：同合成分、同 V 时取总里程小者）。

δ1 合并（f_p3_cert4 merge）发现指派 2 有两个向量达到 z*、V = V*：向量 18（主方案的出发日向量）与向量 3（批 2、13 提前 1 天）。
本脚本在这两个向量上重跑与 f_p3_cert4 相同的簇内 DFS，额外记录每个 (超额 τ, 超额 L̄) 键的最短总里程 D，
只保留“本簇贡献 + 其余各簇最小贡献 + δ·WD + off ≤ z* + 1e-7”的键（其余各簇最小贡献取自 δ1 已完成的 out/ 前沿，
不可能凑出 ≤ z* 的键对结论无影响）。合并后报告每个向量上合成分等于 z* 的方案中的最短总里程，与主方案比较。
用法：python src/f_p3_cert4_ties.py work 18 | merge
输出：results/F/p3_cert4/ties/
"""
from __future__ import annotations

import os
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
BASE = ROOT / "results" / "F" / "p3_cert4"
OUT = BASE / "ties"
VECS = [(2, 3), (2, 18)]
EPS = 1e-9
TOL = 1e-7
_B, _THR = None, None


def thresholds(B):
    """每个 (tie, vec, cluster) 的贡献阈值：z* − δ·WD − off − Σ_{其余簇} 最小贡献。"""
    import pandas as pd
    tasks = pd.read_csv(BASE / "tasks.csv")
    minc = defaultdict(lambda: float("inf"))
    for r in tasks.itertuples():
        if (r.tie, r.vec) not in VECS:
            continue
        df = pd.read_csv(BASE / "out" / f"{r.task}.csv")
        for x in df[df.tex.notna()].itertuples():
            minc[r.tie, r.vec, r.cluster] = min(minc[r.tie, r.vec, r.cluster], x.tex * B["WT"] + x.lex * B["WL"])
    thr = {}
    for t, vi in VECS:
        d = B["vecdata"][t, vi]
        nc = len(d["cls"])
        for ci in range(nc):
            others = sum(minc[t, vi, cj] for cj in range(nc) if cj != ci)
            thr[t, vi, ci] = B["z"] - d["delta"] * B["WD"] - d["off"] - others + 1e-7
    return thr, tasks[[(a, b) in VECS for a, b in zip(tasks.tie, tasks.vec)]]


def _init(path):
    global _B, _THR
    with open(path, "rb") as f:
        _B = pickle.load(f)
    _THR, _ = thresholds(_B)


def cluster_tie_front(inst, cl, days, cand, iv, mt, mL, E, budget, WT, WL, sub, nsub, depth2, thr):
    import f_p3
    opts = {b: sorted(((inst.cands[b][i]["tau"] - mt[b], inst.cands[b][i]["Lbar"] - mL[b], i) for i in cand[b])) for b in cl}
    d2 = min(depth2, len(cl))
    front, n_sim, counter2, sol = {}, 0, [0], {}

    def dfs(k, te, le):
        nonlocal n_sim
        if nsub > 1 and k == d2:
            counter2[0] += 1
            if (counter2[0] - 1) % nsub != sub:
                return
        if k == len(cl):
            n_sim += 1
            ev = f_p3._Sub(inst, sol).evaluate(sol)
            if not ev["feasible"] or any(ev["res"][b].end_day > iv[b][1] for b in cl):
                return
            tex = ev["tau"] - sum(mt[b] for b in cl)
            lex = ev["L"] - sum(mL[b] for b in cl)
            if tex > E or tex * WT + lex * WL > thr:
                return
            key = (int(tex), round(lex, 6))
            if key not in front or ev["D"] < front[key][0]:
                front[key] = (ev["D"], dict(sol))
            return
        b = cl[k]
        for dt, dl, i in opts[b]:
            if te + dt > E or (te + dt) * WT + (le + dl) * WL > budget + EPS:
                continue
            sol[b] = (i, days[b])
            dfs(k + 1, te + dt, le + dl)
        sol.pop(b, None)

    dfs(0, 0, 0.0)
    return front, n_sim


def run_task(row):
    t, vi, ci, s, ns, name = row
    d = _B["vecdata"][t, vi]
    t0 = time.time()
    fr, n = cluster_tie_front(_B["insts"][t], d["cls"][ci], d["days"], d["cand"], d["iv"], d["mt"], d["mL"], d["E"], d["budget"],
                              _B["WT"], _B["WL"], s, ns, _B["depth2"], _THR[t, vi, ci])
    lines = ["task,tex,lex,D,routes,n_sim,seconds", f"{name},,,,,{n},{time.time() - t0:.1f}"]
    for (k, l), (D, sol) in sorted(fr.items()):
        lines.append(f"{name},{int(k)},{float(l)!r},{float(D)!r},{' '.join(f'{b}:{i}' for b, (i, _) in sorted(sol.items()))},0,")
    tmp = OUT / f"{name}.tmp"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, OUT / f"{name}.csv")
    return name, n, time.time() - t0, len(fr)


def work(nproc):
    from multiprocessing import Pool
    OUT.mkdir(parents=True, exist_ok=True)
    with open(BASE / "bundle.pkl", "rb") as f:
        B = pickle.load(f)
    _, tasks = thresholds(B)
    done = {p.stem for p in OUT.glob("*.csv")}
    rows = [(int(r.tie), int(r.vec), int(r.cluster), int(r.sub), int(r.nsub), r.task) for r in tasks.itertuples() if r.task not in done]
    rows.sort(key=lambda r: -r[4])
    print(f"{time.strftime('%m-%d %H:%M:%S')} 并列核查任务 {len(tasks)}，待做 {len(rows)}，进程 {nproc}", flush=True)
    with Pool(nproc, initializer=_init, initargs=(str(BASE / "bundle.pkl"),)) as pool:
        for k, (name, n, sec, nf) in enumerate(pool.imap_unordered(run_task, rows), 1):
            print(f"{time.strftime('%m-%d %H:%M:%S')} [{k}/{len(rows)}] {name} 回放 {n} 用时 {sec:.0f}s 键 {nf}", flush=True)
    print(f"{time.strftime('%m-%d %H:%M:%S')} 全部完成", flush=True)


def merge():
    import pandas as pd
    with open(BASE / "bundle.pkl", "rb") as f:
        B = pickle.load(f)
    _, tasks = thresholds(B)
    main = pd.read_csv(ROOT / "results" / "F" / "p3" / "summary.csv")
    D_main = float(main[main.name.str.startswith("主路线")].D.iloc[0])
    rows = []
    for t, vi in VECS:
        d = B["vecdata"][t, vi]
        tv = tasks[(tasks.tie == t) & (tasks.vec == vi)]
        miss = [n for n in tv.task if not (OUT / f"{n}.csv").exists()]
        if miss:
            rows.append(dict(tie=t, vec=vi, status=f"未完成 {len(miss)}"))
            continue
        fr = defaultdict(dict)
        nsim = 0
        for r in tv.itertuples():
            df = pd.read_csv(OUT / f"{r.task}.csv")
            nsim += int(df.n_sim.sum())
            for x in df[df.tex.notna()].itertuples():
                key = (int(x.tex), round(float(x.lex), 6))
                if key not in fr[r.cluster] or x.D < fr[r.cluster][key][0]:
                    fr[r.cluster][key] = (float(x.D), x.routes)
        tot = {(0, 0.0): (0.0, "")}
        for ci in range(len(d["cls"])):
            new = {}
            for (t1, l1), (D1, r1) in tot.items():
                for (t2, l2), (D2, r2) in fr[ci].items():
                    kk = (t1 + t2, round(l1 + l2, 6))
                    if kk[0] <= d["E"] and (kk not in new or D1 + D2 < new[kk][0]):
                        new[kk] = (D1 + D2, (r1 + " " + r2).strip())
            tot = new
        sc = [(tt * B["WT"] + ll * B["WL"] + d["delta"] * B["WD"] + d["off"], D, r) for (tt, ll), (D, r) in tot.items()]
        lower = [x for x in sc if x[0] < B["z"] - TOL]  # 键把超额 L̄ 舍入到 6 位，跨簇相加后误差约 1e-9；δ1 精确合并已证无更低，同分容差放宽到 TOL
        eq = [x for x in sc if abs(x[0] - B["z"]) <= TOL]
        best = min(eq, key=lambda x: x[1]) if eq else None
        rows.append(dict(tie=t, vec=vi, delta=d["delta"], V=d["V"], status="已判定", n_sim=nsim, n_lower=len(lower), n_equal=len(eq),
                         minD_equal=best[1] if best else None, routes=best[2] if best else None, D_main=D_main))
    res = pd.DataFrame(rows)
    res.to_csv(OUT.parent / "ties_summary.csv", index=False, encoding="utf-8-sig")
    print(res.drop(columns=["routes"], errors="ignore").to_string(index=False))


if __name__ == "__main__":
    if sys.argv[1] == "work":
        work(int(sys.argv[2]))
    elif sys.argv[1] == "merge":
        merge()
