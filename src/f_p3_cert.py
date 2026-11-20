"""问题 3 最优性证书（evidence V26–V30）。不改主结果，只检验主结果在路线空间内是否最优。

思路（松弛 + 枚举 + 回放）：
1. V26 前提：任一批在联合回放中的结束时刻 ≥ 它同一路线、同一出发日单独回放的结束时刻，L̄ 不变。
   于是每批的真实 (τ, L̄) ≥ 孤立值，真实合成分 ≥ 按孤立值计的“松弛分”。
2. V27 松弛：在全部可行路线（不剪枝）× 允许出发日上，按孤立值计分，只保留 S1、S2、S4、R4 整批先后
   （这些在孤立区间上都是必要条件），求最小松弛分 = 合成分的下界。
3. V29 枚举：松弛分 ≤ 主结果合成分的全部松弛解（Gurobi 解池，PoolSearchMode=2）逐一做整体回放和合规判断。
   任何真实合成分更小的方案，其松弛分必更小，所以必在池中；池完整且池内无更好可行解 ⇒ 主结果最优。
4. V30：全候选集上的坐标下降（启发式交叉检查；成对邻域组合数过大不做）。

合成分标尺 ref 沿用 R25（下界 124 / 12566.233135 / 0，基线 134 / 14412.883927 / 5），不改。
用法：python src/f_p3_cert.py [pool_limit=200000]
输出：results/F/p3_cert/summary.csv、v26_monotone.csv、pool_eval.csv
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import gurobipy as gp
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_engine as fe  # noqa: E402
import f_p3  # noqa: E402
import f_parse as fp  # noqa: E402
import f_routes as fr  # noqa: E402
from f_run_p3 import load_assign  # noqa: E402

OUT = ROOT / "results" / "F" / "p3_cert"
REF = dict(l=(124, 12566.233135, 0.0), u=(134, 14412.883927, 5))  # R25 的标尺，固定


def build():
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    assign = load_assign(ROOT / "results" / "F" / "p2" / "assign_main.csv", blocks)
    inst = f_p3.Instance(assign, batches, blocks, cap, D)
    # 主结果（剪枝候选集上的索引）→ 换成全候选集
    m = pd.read_csv(ROOT / "results" / "F" / "p3" / "batches_main.csv")
    inc_pruned = {int(r.batch): (int(r.route), int(r.start)) for r in m.itertuples()}
    inc_steps = {b: inst.cands[b][ri]["steps"] for b, (ri, _) in inc_pruned.items()}
    for b in inst.ids:
        u = batches[b].unit
        allr = []
        for steps in fr.enumerate_routes(u, inst.T[b], inst.groups[b], D):
            ev = fr.evaluate(b, u, inst.T[b], steps, D)
            if ev["ok"]:
                ev["steps"] = steps
                allr.append(ev)
        inst.cands[b] = allr
    inc = {}
    for b, (_, day) in inc_pruned.items():
        idx = [i for i, c in enumerate(inst.cands[b]) if c["steps"] == inc_steps[b]]
        assert len(idx) >= 1, b
        inc[b] = (idx[0], day)
    return inst, inc, D


def iso(inst, D, b, ri, day):
    p = fe.Plan(b, inst.batches[b].unit, day, inst.T[b], inst.cands[b][ri]["steps"], tuple(fb.H[inst.batches[b].unit]))
    return fe.simulate([p], D)[0][b]


def options(inst, b):
    lo, hi = inst.window(b)
    return [(ri, d) for ri, c in enumerate(inst.cands[b]) for d in range(lo, hi + 1) if d + c["tau"] - 1 <= f_p3.LAST_DAY]


def v26(inst, inc, D, n_random=2000, seed=0):
    """单调性前提：返回逐项比较的记录与失败数。"""
    rows, fails = [], 0
    # (a) 孤立 τ、L̄ 与出发日无关（全部选项穷举）
    for b in inst.ids:
        for ri, d in options(inst, b):
            r, c = iso(inst, D, b, ri, d), inst.cands[b][ri]
            if r.tau != c["tau"] or abs(r.Lbar - c["Lbar"]) > 1e-9:
                fails += 1
                rows.append(dict(kind="shift", batch=b, route=ri, day=d, iso_tau=c["tau"], sim_tau=r.tau))
    n_shift = sum(len(options(inst, b)) for b in inst.ids)

    def check(sol, kind):
        nonlocal fails
        res, _ = fe.simulate(inst.plans(sol), D)
        bad = 0
        for b in inst.ids:
            r0 = iso(inst, D, b, *sol[b])
            if res[b].logs[-1].arrive < r0.logs[-1].arrive or res[b].tau < r0.tau or abs(res[b].Lbar - r0.Lbar) > 1e-9:
                bad += 1
                rows.append(dict(kind=kind, batch=b, route=sol[b][0], day=sol[b][1], iso_tau=r0.tau, sim_tau=res[b].tau))
        fails += bad

    rng = random.Random(seed)
    for _ in range(n_random):
        check({b: rng.choice(options(inst, b)) for b in inst.ids}, "random")
    n_nb = 0
    for b in inst.ids:  # 主结果的单批邻域
        for o in options(inst, b):
            s = dict(inc)
            s[b] = o
            check(s, "neighbour")
            n_nb += 1
    return rows, fails, n_shift, n_nb


def relaxation(inst, D, obj="score"):
    """松弛 MILP。obj = score / tau / L。返回 (模型, 变量字典, 常数项)。"""
    l, u = REF["l"], REF["u"]
    w = (1 / (u[0] - l[0]), 1 / (u[1] - l[1]), 1 / (u[2] - l[2]))
    m = gp.Model("p3_relax")
    m.Params.OutputFlag = 0
    x, cost = {}, {}
    for b in inst.ids:
        a = inst.batches[b].a
        for ri, d in options(inst, b):
            c = inst.cands[b][ri]
            x[b, ri, d] = m.addVar(vtype=gp.GRB.BINARY)
            if obj == "score":
                cost[b, ri, d] = w[0] * c["tau"] + w[1] * c["Lbar"] + w[2] * abs(d - a)
            elif obj == "tau":
                cost[b, ri, d] = c["tau"]
            else:
                cost[b, ri, d] = c["Lbar"]
        m.addConstr(gp.quicksum(x[k] for k in x if k[0] == b) == 1)
    # S4：同一执行单位同一天在执行的批次 ≤ 2（孤立区间 ⊆ 真实区间）
    by_unit = {}
    for (b, ri, d) in x:
        by_unit.setdefault(inst.batches[b].unit, []).append((b, ri, d))
    for un, ks in by_unit.items():
        if len({k[0] for k in ks}) < 3:
            continue
        for t in range(1, f_p3.LAST_DAY + 1):
            act = [k for k in ks if k[2] <= t <= k[2] + inst.cands[k[0]][k[1]]["tau"] - 1]
            if len({k[0] for k in act}) >= 3:
                m.addConstr(gp.quicksum(x[k] for k in act) <= 2)
    # R4 整批先后：领回批次的出发日 > 执行批次的结束日（真实结束日 ≥ 孤立结束日）
    for _, be, br, *_ in inst.r4:
        st_br = gp.quicksum(d * x[k] for k in x for d in [k[2]] if k[0] == br)
        en_be = gp.quicksum((k[2] + inst.cands[be][k[1]]["tau"] - 1) * x[k] for k in x if k[0] == be)
        m.addConstr(st_br >= en_be + 1)
    const = -(w[0] * l[0] + w[1] * l[1]) if obj == "score" else 0.0
    m.setObjective(gp.quicksum(cost[k] * x[k] for k in x) + const, gp.GRB.MINIMIZE)
    return m, x, const


def pick(x, getter):
    sol = {}
    for k, v in x.items():
        if getter(v) > 0.5:
            sol[k[0]] = (k[1], k[2])
    return sol


def main():
    pool_limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    inst, inc, D = build()
    ev_inc = inst.evaluate(inc)
    s_inc, V_inc = inst.score(ev_inc, REF)
    n_opt = sum(len(options(inst, b)) for b in inst.ids)
    print(f"全候选 {sum(len(inst.cands[b]) for b in inst.ids)} 条路线，{n_opt} 个 (路线, 出发日) 选项；主结果 可行={ev_inc['feasible']} "
          f"tau={ev_inc['tau']} L={ev_inc['L']:.6f} delta={ev_inc['delta']} V={V_inc} 合成分={s_inc:.10f}  {time.time() - t0:.1f}s")
    summ = [dict(item="主结果", value=s_inc, tau=ev_inc["tau"], L=ev_inc["L"], delta=ev_inc["delta"], V=V_inc)]

    # V26
    rows, fails, n_shift, n_nb = v26(inst, inc, D)
    pd.DataFrame(rows).to_csv(OUT / "v26_monotone.csv", index=False, encoding="utf-8-sig")
    print(f"V26：平移不变 {n_shift} 项 + 随机联合方案 2000 组 + 主结果邻域 {n_nb} 组，失败 {fails}  {time.time() - t0:.1f}s")
    summ.append(dict(item="V26 失败数", value=fails, tau=None, L=None, delta=None, V=None))

    # V27：三种目标的松弛下界
    for obj in ("tau", "L", "score"):
        m, x, const = relaxation(inst, D, obj)
        m.Params.MIPGap = 0
        m.optimize()
        sol = pick(x, lambda v: v.X)
        ev = inst.evaluate(sol)
        lb = m.ObjBound if obj != "score" else m.ObjBound
        print(f"V27 松弛[{obj}]：状态 {m.Status} 最优值 {m.ObjVal:.10f} 界 {m.ObjBound:.10f}；其解回放 可行={ev['feasible']} "
              f"tau={ev['tau']} L={ev['L']:.3f} delta={ev['delta']} 合成分={inst.score(ev, REF)[0]:.6f}")
        summ.append(dict(item=f"松弛下界[{obj}]", value=lb, tau=ev["tau"], L=ev["L"], delta=ev["delta"], V=ev["V"],
                         replay_feasible=ev["feasible"], replay_score=inst.score(ev, REF)[0]))
    relax_opt = summ[-1]["value"]

    # V29：枚举松弛分 ≤ 主结果合成分的全部松弛解
    m, x, const = relaxation(inst, D, "score")
    m.Params.PoolSearchMode = 2
    m.Params.PoolSolutions = pool_limit
    m.Params.PoolGapAbs = s_inc - relax_opt + 1e-7
    m.Params.MIPGap = 0
    m.Params.TimeLimit = 3600
    m.optimize()
    n_pool = m.SolCount
    complete = (m.Status == gp.GRB.OPTIMAL) and n_pool < pool_limit
    print(f"V29 解池：{n_pool} 个解（上限 {pool_limit}），状态 {m.Status}，完整={complete}  {time.time() - t0:.1f}s")
    recs, best = [], (s_inc, V_inc, None)
    keys = list(x)
    for i in range(n_pool):
        m.Params.SolutionNumber = i
        vals = m.getAttr("Xn", [x[k] for k in keys])
        sol = {k[0]: (k[1], k[2]) for k, v in zip(keys, vals) if v > 0.5}
        ev = inst.evaluate(sol)
        relax = m.PoolObjVal
        sc, V = inst.score(ev, REF) if ev["feasible"] else (float("inf"), None)
        recs.append(dict(i=i, relax_score=relax, feasible=ev["feasible"], score=sc, tau=ev["tau"], L=ev["L"], delta=ev["delta"], V=V,
                         n_viol=len(ev["viol"]), viol0=str(ev["viol"][:2])))
        if ev["feasible"] and (sc < best[0] - 1e-9 or (abs(sc - best[0]) <= 1e-9 and V < best[1])):
            best = (sc, V, sol)
    pe = pd.DataFrame(recs)
    pe.to_csv(OUT / "pool_eval.csv", index=False, encoding="utf-8-sig")
    nf = int(pe.feasible.sum()) if len(pe) else 0
    print(f"  回放：可行 {nf} 个；可行解最小合成分 {pe[pe.feasible].score.min() if nf else None}；更好解={'有' if best[2] else '无'}  {time.time() - t0:.1f}s")
    summ.append(dict(item="V29 解池规模", value=n_pool, complete=complete, n_feasible=nf,
                     better_found=best[2] is not None, best_score=best[0], best_V=best[1]))
    if best[2]:
        ev = inst.evaluate(best[2])
        pd.DataFrame([dict(batch=b, route=ri, day=d) for b, (ri, d) in sorted(best[2].items())]).to_csv(OUT / "better_sol.csv", index=False)
        print("  更好解：", dict(tau=ev["tau"], L=ev["L"], delta=ev["delta"], V=ev["V"]))

    # V30：全候选集邻域
    sol, _ = inst.improve(inc, REF)  # 成对邻域在全候选集上组合数过大（批 30 × 批 43 约 160 万次回放），不做；完整性由 V29 保证
    ev = inst.evaluate(sol)
    sc = inst.score(ev, REF)
    print(f"V30 全候选邻域：合成分 {sc[0]:.10f} V={sc[1]}（主结果 {s_inc:.10f}），tau={ev['tau']} L={ev['L']:.3f} delta={ev['delta']}  {time.time() - t0:.1f}s")
    summ.append(dict(item="V30 全候选邻域", value=sc[0], tau=ev["tau"], L=ev["L"], delta=ev["delta"], V=sc[1]))
    pd.DataFrame(summ).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
