"""问题 3 最优性证书（spec v2.6）：在问题 2 的全部并列最优指派上，证明没有方案的共用标尺合成分低于主结果 z*（同分时 V 不更小）。

推理（沿用 f_p3_cert2 的分簇枚举，前提相同：单调性、分簇独立性、每站至多 2 访、同组同处理）：
- 共用标尺 REF（p3/ref.csv）下，指派 t 的任一方案 z = (τ−l_τ)·WT + (L̄−l_L)·WL + δ·WD。
- 令 off_t = (Σ_b 最少孤立 τ − l_τ)·WT + (Σ_b 最小 L̄ − l_L)·WL ≥ 0（共用下端可能低于本指派的孤立下界）。
- 偏离上界：jt_t = Σ_b min_c(τ_c·WT + L̄_c·WL) − (l_τ·WT + l_L·WL) 是时间、距离两项之和的下界，故 δ ≤ dmax_t = ⌊(z* − jt_t)/WD⌋。
- 枚举 δ ≤ dmax_t 的全部出发日向量（S1、S2、S4、R4 以最少孤立 τ 作必要条件；向量数为 0 即该指派整体排除）。
- 每个向量：E = ⌊(z* − δ·WD − off_t)/WT⌋，预算 = z* − δ·WD − off_t；分簇枚举并整簇回放，得到各簇 (超额 τ, 超额 L̄) 前沿再组合。
- 并行：簇内深度优先搜索按第 SPLIT 层的前缀编号轮流分给各分片（同一向量内也能并行），merge 汇总。
- 已知局限（同 R41）：候选只含孤立满足 S10 的路线。
用法：python src/f_p3_cert3.py measure | run <part> <nparts> | merge
输出：results/F/p3_cert3/
"""
from __future__ import annotations

import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_p3  # noqa: E402
import f_p3_cert2 as c2  # noqa: E402
import f_parse as fp  # noqa: E402
from f_run_p3 import load_assign  # noqa: E402

OUT = ROOT / "results" / "F" / "p3_cert3"
P2 = ROOT / "results" / "F" / "p2"
P3 = ROOT / "results" / "F" / "p3"
SPLIT = 3
EPS = 1e-9


def ref():
    r = pd.read_csv(P3 / "ref.csv").iloc[0]
    R = dict(l=(r.l_tau, r.l_L, r.l_delta), u=(r.u_tau, r.u_L, r.u_delta))
    c2.REF = R
    c2.WT, c2.WL, c2.WD = (1 / (R["u"][i] - R["l"][i]) for i in range(3))
    return R


def setup():
    R = ref()
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    ties = pd.read_csv(P3 / "ties.csv")
    pick = int(pd.read_csv(P3 / "choice.csv").iloc[0]["tie"])
    insts = {int(t): f_p3.Instance(load_assign(P2 / f"assign_tie{int(t)}.csv", blocks), batches, blocks, cap, D) for t in ties.tie}
    m = pd.read_csv(P3 / "batches_main.csv")
    inc = {int(r.batch): (int(r.route), int(r.start)) for r in m.itertuples()}
    ev = insts[pick].evaluate(inc)
    assert ev["feasible"]
    z, V = insts[pick].score(ev, R)
    return R, insts, pick, inc, ev, z, V


def plan(inst, z):
    """该指派的 off、jt、dmax、出发日向量。"""
    WT, WL, WD = c2.WT, c2.WL, c2.WD
    l = c2.REF["l"]
    mt = {b: min(x["tau"] for x in inst.cands[b]) for b in inst.ids}
    mL = {b: min(x["Lbar"] for x in inst.cands[b]) for b in inst.ids}
    off = (sum(mt.values()) - l[0]) * WT + (sum(mL.values()) - l[1]) * WL
    jt = sum(min(x["tau"] * WT + x["Lbar"] * WL for x in inst.cands[b]) for b in inst.ids) - (l[0] * WT + l[1] * WL)
    dmax = int(math.floor((z - jt) / WD + EPS))
    vecs, complete, _ = c2.day_vectors(inst, dmax=max(dmax, 0)) if dmax >= 0 else ([], True, mt)
    return dict(mt=mt, mL=mL, off=off, jt=jt, dmax=dmax, vecs=vecs, complete=complete)


def vec_params(inst, v, z, off):
    dlt = sum(abs(v[b] - inst.batches[b].a) for b in inst.ids)
    budget = z - dlt * c2.WD - off
    E = int(math.floor(budget / c2.WT + EPS))
    V = sum(1 for (b0, be) in inst.pairs if not (max(1, inst.batches[b0].a - 6) <= v[be] <= inst.batches[b0].e))
    return dlt, budget, E, V


def measure():
    R, insts, pick, inc, ev, z, V = setup()
    print(f"共用标尺 {R}；主结果（并列指派 {pick}）z* = {z:.12f}，V = {V}，τ = {ev['tau']}，L = {ev['L']:.6f}，δ = {ev['delta']}")
    rows = []
    for t, inst in insts.items():
        p = plan(inst, z)
        reps, _ = c2.collapse(inst)
        sizes = []
        for v in p["vecs"]:
            dlt, budget, E, _ = vec_params(inst, v, z, p["off"])
            if E < 0:
                sizes.append(0)
                continue
            cls, cand, iv, ok = c2.clusters(inst, v, E, p["mt"], reps)
            tot = 0
            for c in cls:
                cnt = {(0, 0): 1}
                for b in c:
                    nxt = defaultdict(int)
                    for (e_, s_), nn in cnt.items():
                        for i in cand[b]:
                            x = inst.cands[b][i]
                            ee = e_ + x["tau"] - p["mt"][b]
                            ss = s_ + int(((x["tau"] - p["mt"][b]) * c2.WT + (x["Lbar"] - p["mL"][b]) * c2.WL) / 1e-4)
                            if ee <= E and ss * 1e-4 <= budget + EPS:
                                nxt[ee, ss] += nn
                    cnt = nxt
                tot += sum(cnt.values())
            sizes.append(tot)
        by_d = defaultdict(lambda: [0, 0])
        for v, sz in zip(p["vecs"], sizes):
            d = sum(abs(v[b] - inst.batches[b].a) for b in inst.ids)
            by_d[d][0] += 1
            by_d[d][1] += sz
        rows.append(dict(tie=t, off=p["off"], jt=p["jt"], dmax=p["dmax"], n_vecs=len(p["vecs"]), complete=p["complete"], size_upper=sum(sizes),
                         by_delta=str({d: tuple(x) for d, x in sorted(by_d.items())})))
        print(rows[-1])
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "measure.csv", index=False, encoding="utf-8-sig")


def cluster_front(inst, cl, days, cand, iv, mt, mL, E, budget, part, nparts):
    """簇内 DFS，第 SPLIT 层（或叶子，若簇更小）的前缀按编号轮流分片。返回 (前沿 {超额τ: 最小超额L̄}, 回放次数)。"""
    WT, WL = c2.WT, c2.WL
    opts = {b: sorted(((inst.cands[b][i]["tau"] - mt[b], inst.cands[b][i]["Lbar"] - mL[b], i) for i in cand[b])) for b in cl}
    depth = min(SPLIT, len(cl))
    front, n_sim, counter, sol = {}, 0, [0], {}

    def dfs(k, te, le):
        nonlocal n_sim
        if k == depth:
            counter[0] += 1
            if (counter[0] - 1) % nparts != part:
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


def run(part, nparts, only_tie=None, only_delta=None):
    t0 = time.time()
    R, insts, pick, inc, ev, z, V = setup()
    rows = []
    for t, inst in insts.items():
        if only_tie is not None and t != only_tie:
            continue
        p = plan(inst, z)
        reps, _ = c2.collapse(inst)
        for vi, v in enumerate(p["vecs"]):
            dlt, budget, E, Vv = vec_params(inst, v, z, p["off"])
            if only_delta is not None and dlt != only_delta:
                continue
            if E < 0:
                if part == 0:
                    rows.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, cluster=-1, tex=None, lex=None, n_sim=0, status="预算为负"))
                continue
            cls, cand, iv, ok = c2.clusters(inst, v, E, p["mt"], reps)
            if not ok:
                if part == 0:
                    rows.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, cluster=-1, tex=None, lex=None, n_sim=0, status="R4 算术不可行"))
                continue
            for ci, c in enumerate(cls):
                fr_, ns = cluster_front(inst, c, v, cand, iv, p["mt"], p["mL"], E, budget, part, nparts)
                rows.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, cluster=ci, tex=None, lex=None, n_sim=ns, status="簇", n_clusters=len(cls)))
                for tex, lex in fr_.items():
                    rows.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, cluster=ci, tex=tex, lex=lex, n_sim=0, status="前沿", n_clusters=len(cls)))
            print(f"[part {part}] 指派 {t} 向量 {vi}/{len(p['vecs'])}（δ={dlt}, E={E}, 簇 {len(cls)}）  {time.time() - t0:.0f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "" if only_tie is None else f"_t{only_tie}" + ("" if only_delta is None else f"_d{only_delta}")
    pd.DataFrame(rows).to_csv(OUT / f"part{part}of{nparts}{tag}.csv", index=False, encoding="utf-8-sig")
    print(f"[part {part}] 完成  {time.time() - t0:.0f}s")


def merge():
    import glob
    R, insts, pick, inc, ev, z, V = setup()
    import re
    parts = sorted(glob.glob(str(OUT / "part*of*.csv")))
    groups = defaultdict(list)  # 每组（全部 / 某指派某偏离）须分片齐全
    for f in parts:
        m = re.match(r"part(\d+)of(\d+)(.*)", Path(f).stem)
        groups[(int(m.group(2)), m.group(3))].append(int(m.group(1)))
    for (n, tag), ks in groups.items():
        assert sorted(ks) == list(range(n)), f"分片不完整：{tag} {sorted(ks)} / {n}"
    df = pd.concat([pd.read_csv(f) for f in parts])
    done_keys = set(zip(df.tie, df.vec))
    out = []
    for t, inst in insts.items():
        p = plan(inst, z)
        for vi, v in enumerate(p["vecs"]):
            dlt, budget, E, Vv = vec_params(inst, v, z, p["off"])
            if (t, vi) not in done_keys:
                out.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, best=None, n_sim=0, better=False, tie_score=False, status="未运行"))
                continue
            g = df[(df.tie == t) & (df.vec == vi)]
            st = set(g.status)
            if st & {"预算为负", "R4 算术不可行"} or E < 0:
                out.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, best=float("inf"), n_sim=0, better=False, tie_score=False, status="排除"))
                continue
            ncl = int(g.n_clusters.dropna().iloc[0]) if g.n_clusters.notna().any() else 0
            tot = {0: 0.0}
            for ci in range(ncl):
                f = g[(g.cluster == ci) & (g.status == "前沿")]
                fr_ = {}
                for r in f.itertuples():
                    k = int(r.tex)
                    if k not in fr_ or r.lex < fr_[k]:
                        fr_[k] = r.lex
                new = {}
                for t1, l1 in tot.items():
                    for t2, l2 in fr_.items():
                        if t1 + t2 <= E and (t1 + t2 not in new or l1 + l2 < new[t1 + t2]):
                            new[t1 + t2] = l1 + l2
                tot = new
                if not tot:
                    break
            best = min((tt * c2.WT + ll * c2.WL + dlt * c2.WD + p["off"] for tt, ll in tot.items()), default=float("inf"))
            out.append(dict(tie=t, vec=vi, delta=dlt, V=Vv, E=E, best=best, n_sim=int(g.n_sim.sum()),
                            better=best < z - EPS or (abs(best - z) <= EPS and Vv < V), tie_score=abs(best - z) <= EPS, status="已判定"))
    res = pd.DataFrame(out)
    res.to_csv(OUT / "vectors.csv", index=False, encoding="utf-8-sig")
    dec = res[res.status != "未运行"]
    summ = dict(z_star=z, V_star=V, pick=pick, n_vectors=len(res), n_decided=len(dec), n_not_run=int((res.status == "未运行").sum()),
                n_sim=int(res.n_sim.sum()), better_found=bool(dec.better.any()), n_equal=int(dec.tie_score.sum()),
                best_decided=pd.to_numeric(dec.best).min() if len(dec) else None)
    pd.DataFrame([summ]).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(res.groupby(["tie", "delta", "status"]).size().to_string())
    print(summ)


if __name__ == "__main__":
    {"measure": measure, "merge": merge}.get(sys.argv[1], None) and {"measure": measure, "merge": merge}[sys.argv[1]]()
    if sys.argv[1] == "run":
        a = sys.argv[2:]
        run(int(a[0]), int(a[1]), int(a[2]) if len(a) > 2 else None, int(a[3]) if len(a) > 3 else None)
