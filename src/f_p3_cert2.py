"""问题 3 最优性证书第二轮（evidence V31–V32）：按偏离分情形 + 固定出发日 + 分簇精确枚举。

推理：
- 合成分 = (τ−124)/10 + (L̄−12566.233)/1846.65 + δ/5。主结果 s* = 1.319659，δ≥7 时仅偏离项就 ≥1.4，不可能更好；
  δ=d 时能更好须 τ ≤ t_max(d) = 124 + ⌊(s* − d/5)·10⌋，即每批的超额 τ（相对最少孤立 τ）之和 ≤ E(d) = t_max − 124。
- 由 V26（回放 τ ≥ 孤立 τ ≥ 最少孤立 τ），任一更好方案中每批的孤立 τ ≤ min_b + E，回放结束日 ≤ 出发日 + min_b + E − 1。
- 固定出发日向量后，按这些区间把批次分簇：区间不重叠、或不共用作业仓库且不同单位的批次之间没有相互作用（V31）；
  R4 关系的两批若区间不可能相碰，先后用算术判定，否则并入同簇回放。
- 每簇枚举路线组合（只用孤立值之和剪枝，不用部分回放剪枝，因为先到先服务不单调），整簇回放做全部合规判断，
  保留 (τ, L̄) 前沿；各簇前沿组合后判断是否存在合成分 < s*（或同分 V 更小）的方案。
- 路线按“时序签名”合并（逐站节点、卸装台次、留置/汇合、R4 相关步）：签名相同的路线回放时刻相同，只保留 L̄ 最小者（V31 检验）。
用法：python src/f_p3_cert2.py measure | run | d5（δ=5 的 4 个向量做多起点路线搜索，启发式）
"""
from __future__ import annotations

import itertools
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import gurobipy as gp
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_engine as fe  # noqa: E402
import f_p3  # noqa: E402
from f_p3_cert import REF, build, iso  # noqa: E402

OUT = ROOT / "results" / "F" / "p3_cert"
WT = 1 / (REF["u"][0] - REF["l"][0])
WL = 1 / (REF["u"][1] - REF["l"][1])
WD = 1 / (REF["u"][2] - REF["l"][2])
EPS = 1e-9


def ceil_(x):
    return int(math.ceil(x - 1e-9))


def signature(inst, b, c):
    r4g = set()
    for _, be, br, _, g_in, g_out in inst.r4:
        if be == b:
            r4g.add(("in", g_in))
        if br == b:
            r4g.add(("out", g_out))
    sig = []
    for st in c["steps"]:
        cu, cl = ceil_(sum(st.unload.values())), ceil_(sum(st.load.values()))
        mark = tuple(sorted(k for k in r4g if (k[0] == "in" and k[1] in st.unload) or (k[0] == "out" and k[1] in st.load)))
        sig.append((st.node, cu + cl, bool(st.leave), tuple(st.leave), st.rejoin, mark))
    return tuple(sig)


def collapse(inst):
    """每批：签名 -> 该签名下 L̄ 最小的候选下标；返回 {b: [下标]}、合并前后条数。"""
    reps, n0 = {}, 0
    for b in inst.ids:
        best = {}
        for i, c in enumerate(inst.cands[b]):
            n0 += 1
            s = signature(inst, b, c)
            if s not in best or c["Lbar"] < inst.cands[b][best[s]]["Lbar"] - EPS:
                best[s] = i
        reps[b] = sorted(best.values())
    return reps, n0


def ops_nodes(inst, b, idxs):
    return {st.node for i in idxs for st in inst.cands[b][i]["steps"] if st.load or st.unload}


def day_vectors(inst, dmax=6, limit=2_000_000):
    """δ ≤ dmax 的全部出发日向量（S1、S2、S4、R4 以最少孤立 τ 作必要条件）。"""
    mt = {b: min(c["tau"] for c in inst.cands[b]) for b in inst.ids}
    m = gp.Model("days")
    m.Params.OutputFlag = 0
    y = {}
    for b in inst.ids:
        lo, hi = inst.window(b)
        for d in range(lo, hi + 1):
            if d + mt[b] - 1 <= f_p3.LAST_DAY:
                y[b, d] = m.addVar(vtype=gp.GRB.BINARY)
        m.addConstr(gp.quicksum(v for (bb, _), v in y.items() if bb == b) == 1)
    by_unit = defaultdict(list)
    for (b, d) in y:
        by_unit[inst.batches[b].unit].append((b, d))
    for ks in by_unit.values():
        for t in range(1, f_p3.LAST_DAY + 1):
            act = [k for k in ks if k[1] <= t <= k[1] + mt[k[0]] - 1]
            if len({k[0] for k in act}) >= 3:
                m.addConstr(gp.quicksum(y[k] for k in act) <= 2)
    for _, be, br, *_ in inst.r4:
        m.addConstr(gp.quicksum(d * v for (bb, d), v in y.items() if bb == br) >=
                    gp.quicksum((d + mt[be] - 1) * v for (bb, d), v in y.items() if bb == be) + 1)
    dev = gp.quicksum(abs(d - inst.batches[b].a) * v for (b, d), v in y.items())
    m.addConstr(dev <= dmax)
    m.setObjective(dev, gp.GRB.MINIMIZE)
    m.Params.PoolSearchMode = 2
    m.Params.PoolSolutions = limit
    m.Params.PoolGapAbs = dmax + 1
    m.optimize()
    keys = list(y)
    vecs = []
    for i in range(m.SolCount):
        m.Params.SolutionNumber = i
        vals = m.getAttr("Xn", [y[k] for k in keys])
        vecs.append({k[0]: k[1] for k, v in zip(keys, vals) if v > 0.5})
    return vecs, m.SolCount < limit and m.Status == gp.GRB.OPTIMAL, mt


def clusters(inst, days, E, mt, reps):
    """返回 (簇列表, R4 算术判定是否可行)。"""
    cand = {b: [i for i in reps[b] if inst.cands[b][i]["tau"] <= mt[b] + E] for b in inst.ids}
    iv = {b: (days[b], days[b] + mt[b] + E - 1) for b in inst.ids}
    nodes = {b: ops_nodes(inst, b, cand[b]) for b in inst.ids}
    par = {b: b for b in inst.ids}

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    ok = all(cand[b] for b in inst.ids)
    for b1, b2 in itertools.combinations(inst.ids, 2):
        (l1, h1), (l2, h2) = iv[b1], iv[b2]
        if l1 <= h2 and l2 <= h1 and (inst.batches[b1].unit == inst.batches[b2].unit or nodes[b1] & nodes[b2]):
            par[f(b1)] = f(b2)
    for _, be, br, *_ in inst.r4:
        lo_end = days[be] + mt[be] - 1          # 执行批次最早可能的结束日
        hi_end = days[be] + mt[be] + E - 1      # 最晚
        if days[br] <= lo_end:
            ok = False                           # 必违反整批先后
        elif days[br] <= hi_end:
            par[f(be)] = f(br)                   # 取决于路线与回放，并簇
    comp = defaultdict(list)
    for b in inst.ids:
        comp[f(b)].append(b)
    return [sorted(c) for c in comp.values()], cand, iv, ok


def combos_count(cl, cand, inst, mt, E):
    """满足孤立超额 τ 之和 ≤ E 的组合数（剪枝后的枚举规模）。"""
    cnt = {0: 1}
    for b in cl:
        nxt = defaultdict(int)
        for e, n in cnt.items():
            for i in cand[b]:
                ee = e + inst.cands[b][i]["tau"] - mt[b]
                if ee <= E:
                    nxt[ee] += n
        cnt = nxt
    return sum(cnt.values())


def measure():
    t0 = time.time()
    inst, inc, D = build()
    reps, n0 = collapse(inst)
    print(f"候选 {n0} 条，按时序签名合并后 {sum(len(v) for v in reps.values())} 条  {time.time() - t0:.1f}s")
    vecs, complete, mt = day_vectors(inst)
    dist = defaultdict(int)
    for v in vecs:
        dist[sum(abs(v[b] - inst.batches[b].a) for b in inst.ids)] += 1
    print(f"δ≤6 的出发日向量 {len(vecs)} 个（完整={complete}），按 δ 分布 {dict(sorted(dist.items()))}  {time.time() - t0:.1f}s")
    s_inc = inst.score(inst.evaluate(inc), REF)[0]
    print(f"主结果合成分 {s_inc:.10f}")
    worst, tot = 0, 0
    for v in vecs:
        dlt = sum(abs(v[b] - inst.batches[b].a) for b in inst.ids)
        E = int(math.floor((s_inc - dlt * WD) / WT + 1e-9))
        cls, cand, iv, ok = clusters(inst, v, E, mt, reps)
        if not ok:
            continue
        sizes = [combos_count(c, cand, inst, mt, E) for c in cls]
        tot += sum(sizes)
        worst = max(worst, max(sizes))
    print(f"全部向量的簇内枚举规模合计 {tot}，最大单簇 {worst}  {time.time() - t0:.1f}s")
    dinc = {b: inc[b][1] for b in inst.ids}
    cls, cand, iv, ok = clusters(inst, dinc, 3, mt, reps)
    print("主结果出发日：", [(c, combos_count(c, cand, inst, mt, 3)) for c in cls if len(c) > 1])


def cluster_eval(inst, cl, days, cand, iv, mt, E, budget):
    """簇内穷举：孤立值之和剪枝；整簇回放，可行且每批留在区间内的组合计入 (超额 τ, 超额 L̄) 前沿。返回 (前沿, 回放次数)。"""
    mL = {b: min(x["Lbar"] for x in inst.cands[b]) for b in cl}
    opts = {b: sorted(((inst.cands[b][i]["tau"] - mt[b], inst.cands[b][i]["Lbar"] - mL[b], i) for i in cand[b])) for b in cl}
    front, n_sim = {}, 0
    sol = {}

    def dfs(k, te, le):
        nonlocal n_sim
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


def v31(inst, vecs, mt, reps, n=300, seed=0, s_inc=1.3196587541981049):
    """随机检验：每批都在区间内时，分簇回放 = 整体回放（逐批逐站时刻）。"""
    rng = random.Random(seed)
    tested = fails = 0
    for _ in range(n):
        v = rng.choice(vecs)
        dlt = sum(abs(v[b] - inst.batches[b].a) for b in inst.ids)
        E = int(math.floor((s_inc - dlt * WD) / WT + 1e-9))
        cls, cand, iv, ok = clusters(inst, v, E, mt, reps)
        if not ok:
            continue
        sol = {b: (rng.choice(cand[b]), v[b]) for b in inst.ids}
        res, _ = fe.simulate(inst.plans(sol), inst.D)
        if any(res[b].end_day > iv[b][1] for b in inst.ids):
            continue
        tested += 1
        for c in cls:
            sub = {b: sol[b] for b in c}
            r2, _ = fe.simulate(f_p3._Sub(inst, sub).plans(sub), inst.D)
            for b in c:
                if [(lg.arrive, lg.start, lg.end) for lg in r2[b].logs] != [(lg.arrive, lg.start, lg.end) for lg in res[b].logs]:
                    fails += 1
    return tested, fails


def run(cap=3_000_000, part=0, nparts=1):
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    inst, inc, D = build()
    s_inc, V_inc = inst.score(inst.evaluate(inc), REF)
    reps, _ = collapse(inst)
    vecs, complete, mt = day_vectors(inst)
    tested, fails = v31(inst, vecs, mt, reps, n=5000 if part == 0 else 0, s_inc=s_inc)
    print(f"V31：随机 5000 组中 {tested} 组每批都在区间内，分簇回放与整体回放不一致 {fails} 处  {time.time() - t0:.1f}s")
    mLall = {b: min(x["Lbar"] for x in inst.cands[b]) for b in inst.ids}
    rows, n_sim_tot = [], 0
    for vi, v in enumerate(vecs):
        if vi % nparts != part:
            continue
        dlt = sum(abs(v[b] - inst.batches[b].a) for b in inst.ids)
        E = int(math.floor((s_inc - dlt * WD) / WT + 1e-9))
        budget = s_inc - dlt * WD
        V = sum(1 for (b0, be) in inst.pairs if not (max(1, inst.batches[b0].a - 6) <= v[be] <= inst.batches[b0].e))
        cls, cand, iv, ok = clusters(inst, v, E, mt, reps)
        row = dict(vec=vi, delta=dlt, E=E, V=V, n_clusters=len(cls), max_cluster=max(len(c) for c in cls), r4_ok=ok)
        if not ok:
            rows.append(dict(row, status="R4 算术判定不可行"))
            continue
        mL = mLall
        size = 0
        for c in cls:
            q = 1e-4  # 按合成分超额离散（向下取整 ⇒ 计数是 DFS 叶子数的上界）
            cnt = {(0, 0): 1}
            for b in c:
                nxt = defaultdict(int)
                for (e_, s_), nn in cnt.items():
                    for i in cand[b]:
                        x = inst.cands[b][i]
                        ee = e_ + x["tau"] - mt[b]
                        ss = s_ + int(((x["tau"] - mt[b]) * WT + (x["Lbar"] - mL[b]) * WL) / q)
                        if ee <= E and ss * q <= budget + EPS:
                            nxt[ee, ss] += nn
                cnt = nxt
            size += sum(cnt.values())
        if size > cap:
            rows.append(dict(row, status=f"规模 {size} 超上限，未判定"))
            continue
        tot = {0: 0.0}
        n_sim = 0
        for c in cls:
            fr_, ns = cluster_eval(inst, c, v, cand, iv, mt, E, budget)
            n_sim += ns
            new = {}
            for t1, l1 in tot.items():
                for t2, l2 in fr_.items():
                    if t1 + t2 <= E and (t1 + t2 not in new or l1 + l2 < new[t1 + t2]):
                        new[t1 + t2] = l1 + l2
            tot = new
            if not tot:
                break
        n_sim_tot += n_sim
        best = min((t * WT + l * WL + dlt * WD for t, l in tot.items()), default=float("inf"))
        better = best < s_inc - EPS or (abs(best - s_inc) <= EPS and V < V_inc)
        rows.append(dict(row, status="已判定", n_sim=n_sim, best_score=best, better=better))
    df = pd.DataFrame(rows)
    tag = "" if nparts == 1 else f"_part{part}of{nparts}"
    df.to_csv(OUT / f"v32_vectors{tag}.csv", index=False, encoding="utf-8-sig")
    print(f"V32：向量 {len(vecs)} 个（完整={complete}），回放 {n_sim_tot} 次  {time.time() - t0:.1f}s")
    print(df.groupby(["delta", "status"]).size().to_string())
    done = df[df.status == "已判定"]
    print("已判定向量中存在更好方案：", bool(done.better.any()) if len(done) else None, "；已判定向量的最好合成分", done.best_score.min() if len(done) else None)
    pd.DataFrame([dict(V31_tested=tested, V31_fails=fails, n_vectors=len(vecs), complete=complete, n_sim=n_sim_tot,
                       decided=len(done), undecided=int((df.status.str.startswith("规模")).sum()),
                       r4_infeasible=int((df.status.str.startswith("R4")).sum()),
                       better_found=bool(done.better.any()) if len(done) else False,
                       best_decided=done.best_score.min() if len(done) else None)]).to_csv(OUT / f"v32_summary{tag}.csv", index=False, encoding="utf-8-sig")



def export_candidate(inst, sol, tag):
    """把候选方案导出成附件 6、7 格式（供独立检查器核验）与逐批 csv；不覆盖主结果文件。"""
    import f_export
    import f_p2
    ev = inst.evaluate(sol)
    new_id = f_export.renumber(inst.ids, {b: sol[b][1] for b in inst.ids})
    rows, _, _ = f_p2.summarize(inst.assign, inst.batches, inst.blocks, inst.cap)
    tnp = {x["batch"]: (x["T"], x["N"], x["P"]) for x in rows}
    f_export.write_p2(OUT / f"{tag}_问题2格式.xlsx", inst.assign, inst.batches, inst.blocks, inst.cap, new_id, tnp)
    f_export.write_p3(OUT / f"{tag}_问题3格式.xlsx", 7, inst, sol, ev, new_id)
    pd.DataFrame([dict(batch=b, new_batch=new_id[b], day=sol[b][1], tau=ev["res"][b].tau, Lbar=ev["res"][b].Lbar, D=ev["res"][b].D,
                       route_nodes=">".join(st.node for st in inst.cands[b][sol[b][0]]["steps"])) for b in inst.ids]).to_csv(
        OUT / f"{tag}_batches.csv", index=False, encoding="utf-8-sig")
    print(f"  导出候选 {tag}：tau={ev['tau']} L={ev['L']:.6f} delta={ev['delta']} V={ev['V']} D={ev['D']} 合成分={inst.score(ev, REF)[0]:.10f}")


def delta5_search(n_starts=30, seed=0, sweeps=6):
    """δ=5 的 4 个出发日向量：固定出发日，只换路线的坐标下降，多起点（启发式佐证，不是证明）。"""
    t0 = time.time()
    inst, inc, D = build()
    s_inc, V_inc = inst.score(inst.evaluate(inc), REF)
    reps, _ = collapse(inst)
    vecs, _, mt = day_vectors(inst)
    v5 = [v for v in vecs if sum(abs(v[b] - inst.batches[b].a) for b in inst.ids) == 5]
    rng = random.Random(seed)
    rows = []
    for vi, v in enumerate(v5):
        best_v = (float("inf"), None)
        best_sol = None
        for s in range(n_starts):
            if s == 0:
                sol = {b: (inc[b][0], v[b]) for b in inst.ids}
            else:
                sol = {b: (rng.choice([i for i in range(len(inst.cands[b])) if inst.cands[b][i]["tau"] <= mt[b] + 3]), v[b]) for b in inst.ids}
            ev = inst.evaluate(sol)
            cur = inst.score(ev, REF)[0] if ev["feasible"] else float("inf")
            for _ in range(sweeps):
                changed = False
                for b in inst.ids:
                    keep = sol[b]
                    for ri in range(len(inst.cands[b])):
                        if ri == keep[0] or inst.cands[b][ri]["tau"] > mt[b] + 3:
                            continue
                        sol[b] = (ri, v[b])
                        e2 = inst.evaluate(sol)
                        if e2["feasible"]:
                            sc = inst.score(e2, REF)[0]
                            if sc < cur - 1e-12:
                                cur, keep, changed = sc, sol[b], True
                    sol[b] = keep
                if not changed:
                    break
            ev = inst.evaluate(sol)
            rows.append(dict(vec=vi, shift=str({b: v[b] - inst.batches[b].a for b in inst.ids if v[b] != inst.batches[b].a}), start=s,
                             feasible=ev["feasible"], score=cur, tau=ev["tau"], L=ev["L"], V=ev["V"]))
            if ev["feasible"] and cur < best_v[0]:
                best_v, best_sol = (cur, s), dict(sol)
        print(f"δ=5 向量 {vi} {rows[-1]['shift']}：{n_starts} 个起点的最好合成分 {best_v[0]:.10f}（主结果 {s_inc:.10f}）  {time.time() - t0:.1f}s")
        if best_sol is not None and best_v[0] < s_inc - EPS:
            export_candidate(inst, best_sol, f"d5_vec{vi}" + ("" if n_starts == 30 else f"_n{n_starts}_s{seed}"))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"delta5_search{'' if n_starts == 30 else f'_n{n_starts}_s{seed}'}.csv", index=False, encoding="utf-8-sig")
    print("更好方案：", bool((df.score < s_inc - EPS).any()), "；最好", df.score.min())


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "measure":
        measure()
    elif sys.argv[1] == "d5":
        delta5_search(*(int(x) for x in sys.argv[2:4]))
    else:
        run(part=int(sys.argv[2]) if len(sys.argv) > 2 else 0, nparts=int(sys.argv[3]) if len(sys.argv) > 3 else 1)
