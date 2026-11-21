"""问题 3 最优性证书（spec v2.8）。在 f_p3_cert4（任务池、离线可跑）的基础上：
- 每次整簇回放同时判两种留置端点：主口径（S10 等待 <= 24 小时，留置算到重新开工/离开）与敏感性口径（留置算到车队回站），各存一份前沿；
- 每个簇、每个超额 tau 记录最小超额 Lbar，以及达到该 Lbar（容差 1e-6 km）的组合中的最短总里程 D，用于 J1 第三级（同分同 V 比总里程）；
- 预算按主口径 z*。敏感性口径更宽，其最优值 <= z*，故同一预算内给出的也是该口径的精确最优。
判定：某向量存在 Z < z* - 1e-9，或 |Z - z*| <= 1e-9 且（V < V* 或 V = V* 且 D < D*）=> 更优。|Z - z*| <= 1e-6 的近同分单独报告。
用法：
  python src/f_p3_cert5.py prep 0 1 2           # 指定偏离的向量；写 bundle.pkl、tasks.csv
  python src/f_p3_cert5.py work 18 [目录]
  python src/f_p3_cert5.py merge
环境变量：CERT5_OUT（目录）、CERT5_TARGET（每任务回放数）、CERT5_VECS（只做指定 t:vi）
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
OUT = Path(os.environ.get("CERT5_OUT", ROOT / "results" / "F" / "p3_cert5"))
TARGET = int(os.environ.get("CERT5_TARGET", 1_000_000))  # 每个子任务约 100 万次回放（本机单进程约 50 分钟）
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
    skip = set()
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
            if os.environ.get("CERT5_VECS") and f"{t}:{vi}" not in os.environ["CERT5_VECS"].split(","):
                continue
            if f"{t}:{vi}" in skip:  # 已由 f_p3_cert3 判定的向量
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
    bundle = dict(R=R, z=z, V=V, D=ev["D"], pick=pick, WT=WT, WL=WL, WD=WD, insts={t: insts[t] for t in {k[0] for k in vecdata}},
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


def _upd(front, tex, lex, D):
    """前沿更新：每个超额 tau 保留最小超额 Lbar；Lbar 在 1e-6 km 内相同时保留较短的总里程 D。"""
    cur = front.get(tex)
    if cur is None or lex < cur[0] - 1e-6:
        front[tex] = (lex, D)
    elif abs(lex - cur[0]) <= 1e-6:
        front[tex] = (min(lex, cur[0]), min(D, cur[1]))


def cluster_front(inst, cl, days, cand, iv, mt, mL, E, budget, WT, WL, sub, nsub, depth2):
    """簇内 DFS（同 f_p3_cert4），返回 ({"main": 前沿, "ret": 前沿}, 回放次数)。"""
    import f_p3
    opts = {b: sorted(((inst.cands[b][i]["tau"] - mt[b], inst.cands[b][i]["Lbar"] - mL[b], i) for i in cand[b])) for b in cl}
    d2 = min(depth2, len(cl))
    fronts, n_sim, counter2, sol = {"main": {}, "ret": {}}, 0, [0], {}

    def dfs(k, te, le):
        nonlocal n_sim
        if nsub > 1 and k == d2:
            counter2[0] += 1
            if (counter2[0] - 1) % nsub != sub:
                return
        if k == len(cl):
            n_sim += 1
            ev = f_p3._Sub(inst, sol).evaluate(sol)
            if any(ev["res"][b].end_day > iv[b][1] for b in cl):
                return
            tex = ev["tau"] - sum(mt[b] for b in cl)
            if tex > E:
                return
            lex = ev["L"] - sum(mL[b] for b in cl)
            if ev["feasible"]:
                _upd(fronts["main"], tex, lex, ev["D"])
            if ev.get("feasible_ret", ev["feasible"]):
                _upd(fronts["ret"], tex, lex, ev["D"])
            return
        b = cl[k]
        for dt, dl, i in opts[b]:
            if te + dt > E or (te + dt) * WT + (le + dl) * WL > budget + EPS:
                continue
            sol[b] = (i, days[b])
            dfs(k + 1, te + dt, le + dl)
        sol.pop(b, None)

    dfs(0, 0, 0.0)
    return fronts, n_sim


def run_task(row):
    t, vi, ci, s, ns, name, outdir = row
    d = _B["vecdata"][t, vi]
    t0 = time.time()
    frs, n = cluster_front(_B["insts"][t], d["cls"][ci], d["days"], d["cand"], d["iv"], d["mt"], d["mL"], d["E"], d["budget"],
                           _B["WT"], _B["WL"], s, ns, _B["depth2"])
    lines = ["task,mode,tex,lex,D,n_sim,seconds", f"{name},,,,,{n},{time.time() - t0:.1f}"]
    for mode, fr_ in frs.items():
        lines += [f"{name},{mode},{int(k)},{float(v[0])!r},{float(v[1])!r},0," for k, v in sorted(fr_.items())]
    fr = frs["main"]
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
    fr = {m: defaultdict(dict) for m in ("main", "ret")}
    nsim = defaultdict(int)
    for r in tasks.itertuples():
        p = OUT / "out" / f"{r.task}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        nsim[r.tie, r.vec] += int(df.n_sim.fillna(0).sum())
        for x in df[df.tex.notna()].itertuples():
            _upd(fr[x.mode][r.tie, r.vec, r.cluster], int(x.tex), float(x.lex), float(x.D))
    missv = {(int(a), int(b)) for a, b in tasks[tasks.task.isin(miss)][["tie", "vec"]].values}
    rows = []
    for (t, vi), d in B["vecdata"].items():
        row = dict(tie=t, vec=vi, delta=d["delta"], V=d["V"], E=d["E"], n_sim=nsim[t, vi])
        if (t, vi) in missv:
            rows.append(dict(row, status="未完成"))
            continue
        for mode in ("main", "ret"):
            tot = {0: (0.0, 0.0)}
            for ci in range(len(d["cls"])):
                new = {}
                for t1, (l1, D1) in tot.items():
                    for t2, (l2, D2) in fr[mode][t, vi, ci].items():
                        if t1 + t2 <= d["E"]:
                            _upd(new, t1 + t2, l1 + l2, D1 + D2)
                tot = new
                if not tot:
                    break
            sc = sorted((tt * B["WT"] + ll * B["WL"] + d["delta"] * B["WD"] + d["off"], DD, tt) for tt, (ll, DD) in tot.items())
            best = sc[0] if sc else (float("inf"), None, None)
            row[f"best_{mode}"], row[f"D_{mode}"] = best[0], best[1]
            row[f"near_{mode}"] = max(0, sum(1 for x in sc if abs(x[0] - best[0]) <= 1e-6) - 1)
        z, Vs, Ds = B["z"], B["V"], B["D"]
        bm, Dm = row["best_main"], row["D_main"]
        row["better"] = bool(bm < z - 1e-9 or (abs(bm - z) <= 1e-9 and (d["V"] < Vs or (d["V"] == Vs and Dm is not None and Dm < Ds - 1e-9))))
        row["tie_score"] = bool(abs(bm - z) <= 1e-9)
        row["status"] = "已判定"
        rows.append(row)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "vectors.csv", index=False, encoding="utf-8-sig")
    dec = res[res.status == "已判定"]
    summ = dict(z_star=B["z"], V_star=B["V"], D_star=B["D"], deltas=str(B["deltas"]), n_vectors=len(res), n_decided=len(dec), n_tasks=len(tasks),
                n_tasks_missing=len(miss), n_sim=int(res.n_sim.sum()), est_sum=float(tasks.est.sum()),
                better_found=bool(dec.better.any()) if len(dec) else False, n_equal=int(dec.tie_score.sum()) if len(dec) else 0,
                best_main=pd.to_numeric(dec.best_main).min() if len(dec) else None, best_ret=pd.to_numeric(dec.best_ret).min() if len(dec) else None,
                near_ties=int(dec[["near_main", "near_ret"]].sum().sum()) if len(dec) else 0)
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
