"""问题 2 并列替代指派下的问题 3 最优性证书（探索，不覆盖主结果）。复用 f_p3_cert2 的分簇枚举。

J1 标尺按定义取本实例：l = 孤立下界，u = 本实例规则基线（τ, L̄, δ）。替代指派的基线 δ = 0，偏离项分母退化，
按 f_p3.score 的约定取 1（即每偏离 1 天合成分 +1）。因此 δ ≥ 1 时 z ≥ 1 > z*（z* < 1 时成立），只需枚举 δ = 0 这一个出发日向量。
用法：python src/f_p3_alt_cert.py <k> measure | run | deep <seed>（固定 δ=0 出发日、300 起点的深度路线搜索，启发式）
输出：results/F/p2_alt/cert_alt<k>.csv
"""
from __future__ import annotations

import ast
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

OUT = ROOT / "results" / "F" / "p2_alt"


def build(k):
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    a = pd.read_csv(OUT / f"assign_alt{k}.csv")
    assign = {int(r.block): ast.literal_eval(r.option) for r in a.itertuples()}
    inst = f_p3.Instance(assign, batches, blocks, cap, D)
    sol = pd.read_csv(OUT / f"alt{k}_batches.csv")
    inc = {}
    for r in sol.itertuples():
        idx = [i for i, c in enumerate(inst.cands[r.batch])
               if ">".join(st.node for st in c["steps"]) == r.route_nodes   # 台账的 tau 是排队后的值，不能用来匹配
               and abs(c["Lbar"] - r.Lbar) < 1e-6 and abs(c["D"] - r.D) < 1e-6]
        assert idx, r.batch
        inc[r.batch] = (idx[0], int(r.day))
    p = pd.read_csv(OUT / f"p3_alt{k}.csv").set_index("name")
    ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(p.at["基线", "tau"], p.at["基线", "L"], p.at["基线", "delta"]))
    return inst, inc, ref


def setup(k):
    inst, inc, ref = build(k)
    c2.REF = ref
    c2.WT = 1 / (ref["u"][0] - ref["l"][0])
    c2.WL = 1 / (ref["u"][1] - ref["l"][1])
    c2.WD = 1.0 if ref["u"][2] - ref["l"][2] < 1e-9 else 1 / (ref["u"][2] - ref["l"][2])
    ev = inst.evaluate(inc)
    assert ev["feasible"]
    s_inc, V_inc = inst.score(ev, ref)
    reps, _ = c2.collapse(inst)
    mt = {b: min(x["tau"] for x in inst.cands[b]) for b in inst.ids}
    v = {b: inst.batches[b].a for b in inst.ids}  # δ = 0 的唯一出发日向量
    E = int(math.floor(s_inc / c2.WT + 1e-9))
    print(f"替代解 {k}：z* = {s_inc:.10f}，V = {V_inc}，τ = {ev['tau']}，L = {ev['L']:.6f}；超额天数预算 E = {E}；"
          f"δ ≥ 1 时 z ≥ {c2.WD:.3f} {'> z*，排除' if c2.WD > s_inc else '≤ z*，不能排除'}")
    return inst, inc, ref, s_inc, V_inc, reps, mt, v, E


def measure(k):
    inst, inc, ref, s_inc, V_inc, reps, mt, v, E = setup(k)
    cls, cand, iv, ok = c2.clusters(inst, v, E, mt, reps)
    mL = {b: min(x["Lbar"] for x in inst.cands[b]) for b in inst.ids}
    print(f"簇 {len(cls)} 个，最大簇 {max(len(c) for c in cls)} 批，R4 算术可行 {ok}")
    for c in sorted(cls, key=len, reverse=True)[:8]:
        cnt = {(0, 0): 1}
        for b in c:
            nxt = defaultdict(int)
            for (e_, s_), nn in cnt.items():
                for i in cand[b]:
                    x = inst.cands[b][i]
                    ee = e_ + x["tau"] - mt[b]
                    ss = s_ + int(((x["tau"] - mt[b]) * c2.WT + (x["Lbar"] - mL[b]) * c2.WL) / 1e-4)
                    if ee <= E and ss * 1e-4 <= s_inc + c2.EPS:
                        nxt[ee, ss] += nn
            cnt = nxt
        print(f"  簇 {sorted(c)}：组合上界 {sum(cnt.values())}")


def run(k):
    t0 = time.time()
    inst, inc, ref, s_inc, V_inc, reps, mt, v, E = setup(k)
    cls, cand, iv, ok = c2.clusters(inst, v, E, mt, reps)
    tot, n_sim = {0: 0.0}, 0
    for c in cls:
        fr_, ns = c2.cluster_eval(inst, c, v, cand, iv, mt, E, s_inc)
        n_sim += ns
        new = {}
        for t1, l1 in tot.items():
            for t2, l2 in fr_.items():
                if t1 + t2 <= E and (t1 + t2 not in new or l1 + l2 < new[t1 + t2]):
                    new[t1 + t2] = l1 + l2
        tot = new
        print(f"  簇 {len(c)} 批完成，累计回放 {n_sim}  {time.time() - t0:.0f}s")
        if not tot:
            break
    best = min((t * c2.WT + l * c2.WL for t, l in tot.items()), default=float("inf"))
    row = dict(alt=k, z_inc=s_inc, V_inc=V_inc, E=E, n_clusters=len(cls), n_sim=n_sim, best=best, better=best < s_inc - c2.EPS,
               tie=abs(best - s_inc) <= c2.EPS, seconds=time.time() - t0)
    pd.DataFrame([row]).to_csv(OUT / f"cert_alt{k}.csv", index=False, encoding="utf-8-sig")
    print(row)


def deep(k, seed):
    t0 = time.time()
    inst, inc, ref, s_inc, V_inc, reps, mt, v, E = setup(k)
    sol, key = f_p3.fixed_day_search(inst, ref, v, 300, seed=seed, init=inc)
    sol, key = f_p3.polish(inst, sol, ref)
    ev = inst.evaluate(sol)
    row = dict(alt=k, seed=seed, tau=ev["tau"], L=ev["L"], delta=ev["delta"], V=ev["V"], D=ev["D"], score=key[0], z_inc=s_inc,
               improved=key[0] < s_inc - 1e-12, seconds=time.time() - t0)
    pd.DataFrame([row]).to_csv(OUT / f"deep_alt{k}_s{seed}.csv", index=False, encoding="utf-8-sig")
    if row["improved"]:
        c2.OUT = OUT
        c2.export_candidate(inst, sol, f"alt{k}_deep_s{seed}")
    print(row)


if __name__ == "__main__":
    if sys.argv[2] == "deep":
        deep(int(sys.argv[1]), int(sys.argv[3]))
    else:
        {"measure": measure, "run": run}[sys.argv[2]](int(sys.argv[1]))
