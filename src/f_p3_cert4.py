"""问题 3 证书的离线任务池版（spec v2.6）。判定与 f_p3_cert3 完全相同，只是把工作拆成可在另一台机器上跑的小任务。

- prep（本机，需 Gurobi）：沿用 f_p3_cert3 的 setup / plan / vec_params 与 f_p3_cert2.clusters，得到指定偏离的全部出发日向量、
  各向量的簇、候选与时间窗；每个簇用 (超额 τ, 离散化预算) 的 DP 精确计数叶子（回放）数，按 TARGET 拆成子任务
  （第 depth2 层节点轮流分）。写出 bundle.pkl（实例、标尺、各向量数据）与 tasks.csv。
- work（任意机器，只需 pandas/openpyxl，不需 Gurobi）：多进程按任务规模从大到小执行，每个任务完成即写 out/<task>.csv（原子改名），可中断续跑。
- merge（本机）：检查任务齐全，按簇合并前沿、跨簇组合，判定每个向量的最好合成分；输出 vectors.csv、summary.csv。
用法：
  python src/f_p3_cert4.py prep 1            # 偏离 1 的向量（指派 1、2）
  python src/f_p3_cert4.py work 30 [目录]     # 30 个进程；目录缺省为 results/F/p3_cert4
  python src/f_p3_cert4.py merge
"""
from __future__ import annotations

import math
import os
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(os.environ.get("CERT4_OUT", ROOT / "results" / "F" / "p3_cert4"))  # 测试时可改目录
TARGET = int(os.environ.get("CERT4_TARGET", 1_000_000))  # 每个子任务约 100 万次回放（本机单进程约 50 分钟）
DEPTH2 = 13
SC = 1e-4
EPS = 1e-9


# ---------------------------------------------------------------- prep（本机）
def leaf_count(inst, cl, cand, mt, mL, E, budget, WT, WL):
    cnt = {(0, 0): 1}
    for b in cl:
        nxt = defaultdict(int)
        for (e_, s_), nn in cnt.items():
            for i in cand[b]:
                x = inst.cands[b][i]
                ee = e_ + x["tau"] - mt[b]
                ss = s_ + int(((x["tau"] - mt[b]) * WT + (x["Lbar"] - mL[b]) * WL) / SC)
                if ee <= E and ss * SC <= budget + EPS:
                    nxt[ee, ss] += nn
        cnt = nxt
    return sum(cnt.values())


def prep(deltas):
    import pandas as pd
    import f_p3_cert2 as c2
    import f_p3_cert3 as c3
    R, insts, pick, inc, ev, z, V = c3.setup()
    WT, WL, WD = c2.WT, c2.WL, c2.WD
    vecdata, tasks, excluded = {}, [], []
    for t in sorted(insts):
        inst = insts[t]
        p = c3.plan(inst, z)
        if not p["vecs"]:
            continue
        reps, _ = c2.collapse(inst)
        for vi, v in enumerate(p["vecs"]):
            dlt, budget, E, Vv = c3.vec_params(inst, v, z, p["off"])
            if dlt not in deltas:
                continue
            if os.environ.get("CERT4_VECS") and f"{t}:{vi}" not in os.environ["CERT4_VECS"].split(","):
                continue
            if E < 0:
                excluded.append(dict(tie=t, vec=vi, delta=dlt, why="预算为负"))
                continue
            cls, cand, iv, ok = c2.clusters(inst, v, E, p["mt"], reps)
            if not ok:
                excluded.append(dict(tie=t, vec=vi, delta=dlt, why="R4 算术不可行"))
                continue
            vecdata[t, vi] = dict(days=dict(v), E=E, budget=budget, V=Vv, delta=dlt, off=p["off"], cls=cls,
                                  cand={b: list(cand[b]) for b in inst.ids}, iv=dict(iv), mt=dict(p["mt"]), mL=dict(p["mL"]))
            for ci, c in enumerate(cls):
                n = leaf_count(inst, c, cand, p["mt"], p["mL"], E, budget, WT, WL)
                nsub = max(1, math.ceil(n / TARGET)) if len(c) > DEPTH2 else 1
                for s in range(nsub):
                    tasks.append(dict(task=f"t{t}_v{vi}_c{ci}_s{s}of{nsub}", tie=t, vec=vi, delta=dlt, cluster=ci,
                                      sub=s, nsub=nsub, n_batches=len(c), est=n / nsub))
        print(f"指派 {t}：向量 {sum(1 for k in vecdata if k[0] == t)} 个，任务累计 {len(tasks)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    bundle = dict(R=R, z=z, V=V, pick=pick, WT=WT, WL=WL, WD=WD, insts={t: insts[t] for t in {k[0] for k in vecdata}},
                  vecdata=vecdata, deltas=sorted(deltas), target=TARGET, depth2=DEPTH2)
    with open(OUT / "bundle.pkl", "wb") as f:
        pickle.dump(bundle, f, protocol=5)
    pd.DataFrame(tasks).to_csv(OUT / "tasks.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(excluded, columns=["tie", "vec", "delta", "why"]).to_csv(OUT / "excluded.csv", index=False, encoding="utf-8-sig")
    tot = sum(x["est"] for x in tasks)
    print(f"任务 {len(tasks)} 个，预计回放 {tot:.3e} 次；直接排除 {len(excluded)} 个向量；z* = {z:.12f}，V* = {V}")


# ---------------------------------------------------------------- work（任意机器）
_B = None


def _init(path):
    global _B
    with open(path, "rb") as f:
        _B = pickle.load(f)


def cluster_front(inst, cl, days, cand, iv, mt, mL, E, budget, WT, WL, sub, nsub, depth2):
    """与 f_p3_cert3.cluster_front 相同的簇内 DFS（part=0、nparts=1），子任务在第 depth2 层节点轮流分。"""
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
            if tex <= E and (tex not in front or lex < front[tex] - EPS):
                front[tex] = lex
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
    t, vi, ci, s, ns, name, outdir = row
    d = _B["vecdata"][t, vi]
    t0 = time.time()
    fr, n = cluster_front(_B["insts"][t], d["cls"][ci], d["days"], d["cand"], d["iv"], d["mt"], d["mL"], d["E"], d["budget"],
                          _B["WT"], _B["WL"], s, ns, _B["depth2"])
    lines = ["task,tex,lex,n_sim,seconds"] + [f"{name},,,{n},{time.time() - t0:.1f}"] + [f"{name},{int(k)},{float(v)!r},0," for k, v in sorted(fr.items())]
    tmp = Path(outdir) / f"{name}.tmp"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, Path(outdir) / f"{name}.csv")
    return name, n, time.time() - t0, len(fr)


def work(nproc, base=None):
    import csv
    from multiprocessing import Pool
    base = Path(base) if base else OUT
    out = base / "out"
    out.mkdir(parents=True, exist_ok=True)
    with open(base / "tasks.csv", encoding="utf-8-sig") as f:
        tasks = list(csv.DictReader(f))
    done = {p.stem for p in out.glob("*.csv")}
    todo = sorted((r for r in tasks if r["task"] not in done), key=lambda r: -float(r["est"]))
    tot = sum(float(r["est"]) for r in todo)
    print(f"{time.strftime('%m-%d %H:%M:%S')} 任务 {len(tasks)}，已完成 {len(done)}，待做 {len(todo)}（预计回放 {tot:.3e}），进程 {nproc}", flush=True)
    rows = [(int(r["tie"]), int(r["vec"]), int(r["cluster"]), int(r["sub"]), int(r["nsub"]), r["task"], str(out)) for r in todo]
    t0, k, sims = time.time(), 0, 0
    with Pool(nproc, initializer=_init, initargs=(str(base / "bundle.pkl"),)) as pool:
        for name, n, sec, nf in pool.imap_unordered(run_task, rows):
            k += 1
            sims += n
            el = time.time() - t0
            eta = (tot - sims) / (sims / el) / 3600 if sims else float("nan")
            print(f"{time.strftime('%m-%d %H:%M:%S')} [{k}/{len(rows)}] {name} 回放 {n} 用时 {sec:.0f}s 前沿 {nf}｜累计 {sims:.3e}，剩余约 {eta:.1f} h", flush=True)
    print(f"{time.strftime('%m-%d %H:%M:%S')} 全部完成", flush=True)


# ---------------------------------------------------------------- merge（本机）
def merge():
    import pandas as pd
    with open(OUT / "bundle.pkl", "rb") as f:
        B = pickle.load(f)
    tasks = pd.read_csv(OUT / "tasks.csv")
    miss = [n for n in tasks.task if not (OUT / "out" / f"{n}.csv").exists()]
    fr = defaultdict(dict)
    nsim = defaultdict(int)
    for r in tasks.itertuples():
        p = OUT / "out" / f"{r.task}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        nsim[r.tie, r.vec] += int(df.n_sim.sum())
        for x in df[df.tex.notna()].itertuples():
            k = int(x.tex)
            fr[r.tie, r.vec, r.cluster][k] = min(fr[r.tie, r.vec, r.cluster].get(k, float("inf")), float(x.lex))
    missv = {(int(a), int(b)) for a, b in tasks[tasks.task.isin(miss)][["tie", "vec"]].values}
    rows = []
    for (t, vi), d in B["vecdata"].items():
        if (t, vi) in missv:
            rows.append(dict(tie=t, vec=vi, delta=d["delta"], V=d["V"], E=d["E"], best=None, n_sim=nsim[t, vi], status="未完成"))
            continue
        tot = {0: 0.0}
        for ci in range(len(d["cls"])):
            new = {}
            for t1, l1 in tot.items():
                for t2, l2 in fr[t, vi, ci].items():
                    if t1 + t2 <= d["E"] and l1 + l2 < new.get(t1 + t2, float("inf")):
                        new[t1 + t2] = l1 + l2
            tot = new
            if not tot:
                break
        best = min((tt * B["WT"] + ll * B["WL"] + d["delta"] * B["WD"] + d["off"] for tt, ll in tot.items()), default=float("inf"))
        rows.append(dict(tie=t, vec=vi, delta=d["delta"], V=d["V"], E=d["E"], best=best, n_sim=nsim[t, vi], status="已判定",
                         better=best < B["z"] - EPS or (abs(best - B["z"]) <= EPS and d["V"] < B["V"]), tie_score=abs(best - B["z"]) <= EPS))
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "vectors.csv", index=False, encoding="utf-8-sig")
    dec = res[res.status == "已判定"]
    summ = dict(z_star=B["z"], V_star=B["V"], deltas=str(B["deltas"]), n_vectors=len(res), n_decided=len(dec), n_tasks=len(tasks),
                n_tasks_missing=len(miss), n_sim=int(res.n_sim.sum()), better_found=bool(dec.better.any()) if len(dec) else False,
                n_equal=int(dec.tie_score.sum()) if len(dec) else 0, best_decided=pd.to_numeric(dec.best).min() if len(dec) else None)
    pd.DataFrame([summ]).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(res.groupby(["tie", "delta", "status"]).size().to_string())
    print(summ)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prep":
        prep({int(x) for x in sys.argv[2:]})
    elif cmd == "work":
        work(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "merge":
        merge()
