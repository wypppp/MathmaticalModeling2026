"""F 题问题 3：固定指派下的路线选择与排程（spec v2.2 §5.3、§12-J1）。

解 = 每个最终批次的 (路线编号, 出发日)。所有指标来自 f_engine 的整体回放。
- 基线：每批取“不留置、不途经、每个目标仓库只去一次”的里程最短路线；按提报开始日从早到晚逐批插入，
  出发日依次试 a, a+1, …, e, a−1, …, a−6，取第一个使全体仍可行的。
- 主路线：从基线出发，逐批在 (候选路线 × 允许出发日) 上取使合成目标最小的选择，反复扫描到不再改进（坐标下降）。
"""
from __future__ import annotations

from collections import defaultdict

import f_blocks as fb
import f_engine as fe
import f_routes as fr

LAST_DAY = 91
R4_RULE = "batch"  # 【裁U2】batch = β′ 出发日晚于 β 回驻地日（spec v2.3）；phys = 物理先后（v2.2 的 D15，敏感性用）


class Instance:
    def __init__(self, assign, batches, blocks, cap, D, cache=None, cand_filter=None, early=6, agg="sum", prune=False):
        """cand_filter：对候选路线的过滤（消融用；与 cache 同用时须为每种过滤单独建 cache）。early：最多可提前的天数。
        agg：三项的合成方式，"sum" 等权和 / "minimax" 先比最差项再比总和 / (w1,w2,w3) 加权和。
        prune：True 时按孤立 (τ, L̄, D) 帕累托剪枝（R25 及以前的做法，消融用）；默认 False 保留全部可行路线——
        D 不在目标里，排队下被 D 支配的路线也可能更好（evidence R31）。self.pareto[b] 记录帕累托子集的下标（成对邻域用）。"""
        self.early, self.agg, self.prune = early, agg, prune
        self.assign, self.batches, self.blocks, self.cap, self.D = assign, batches, blocks, cap, D
        self.groups = fr.batch_groups(assign, batches, blocks, cap)
        self.ids = sorted(self.groups)
        self.T, self.cands, self.base_idx, self.pareto = {}, {}, {}, {}
        for b in self.ids:
            u = batches[b].unit
            T = fr.batch_T(self.groups[b], u)[0]
            self.T[b] = T
            sig = (b, T, tuple(sorted((g.gid, round(g.s, 9)) for g in self.groups[b].values())), prune)
            self.sig = getattr(self, "sig", {})
            self.sig[b] = sig
            if cache is not None and sig in cache:
                self.cands[b], self.base_idx[b], self.pareto[b] = cache[sig]
                continue
            allr = []
            for steps in fr.enumerate_routes(u, T, self.groups[b], D):
                ev = fr.evaluate(b, u, T, steps, D)
                if ev["ok"]:
                    ev["steps"] = steps
                    ev["n_noop"] = sum(1 for s in steps[:-1] if not (s.load or s.unload or s.rejoin))
                    acts = [s for s in steps[:-1]]
                    ev["n_pass"] = sum(1 for s in acts if not (s.load or s.unload or s.rejoin))
                    tg = [s.node for s in acts if (s.load or s.unload) and s.node not in fb.H[u]]
                    ev["n_revisit"] = len(tg) - len(set(tg))
                    allr.append(ev)
            if cand_filter is not None:
                allr = [e for e in allr if cand_filter(e)]
            if not allr:
                if cache is not None:
                    cache[sig] = ([], -1, [])
                self.cands[b], self.base_idx[b], self.pareto[b] = [], -1, []
                continue
            simple = [e for e in allr if e["n_leave"] == 0 and e["n_pass"] == 0 and e["n_revisit"] == 0]
            base = min(simple or allr, key=lambda e: (e["D"], e["tau"], e["Lbar"]))
            nd = []
            for a in allr:
                # 帕累托剪枝只在“孤立回放满足 S10”相同的路线之间比较：孤立违反 S10 的路线可能在整体回放中也违反，
                # 不能让它支配孤立合规的路线（v2.8 关闭孤立过滤后，否则会剪掉唯一可行的路线）
                grp = [c for c in allr if c.get("iso_s10", True) == a.get("iso_s10", True)]
                if not any((c["tau"] <= a["tau"] and c["Lbar"] <= a["Lbar"] + 1e-9 and c["D"] <= a["D"] + 1e-9) and
                           (c["tau"] < a["tau"] or c["Lbar"] < a["Lbar"] - 1e-9 or c["D"] < a["D"] - 1e-9) for c in grp):
                    if not any(abs(c["tau"] - a["tau"]) < 1e-9 and abs(c["Lbar"] - a["Lbar"]) < 1e-6 and abs(c["D"] - a["D"]) < 1e-6
                               and c.get("iso_s10", True) == a.get("iso_s10", True) for c in nd):
                        nd.append(a)
            if base not in nd:
                nd.append(base)
            self.cands[b] = nd if prune else allr
            self.base_idx[b] = self.cands[b].index(base)
            self.pareto[b] = [self.cands[b].index(a) for a in nd]
            if cache is not None:
                cache[sig] = (self.cands[b], self.base_idx[b], self.pareto[b])
        self.routable = all(self.cands[b] for b in self.ids)
        if not self.routable:
            return
        self.lb_tau = sum(min(c["tau"] for c in self.cands[b]) for b in self.ids)
        self.lb_L = sum(min(c["Lbar"] for c in self.cands[b]) for b in self.ids)
        # 被代走的 (原批次, 执行批次) 对；R4 的 (执行批次, 领回批次, 暂存仓)
        self.pairs, self.r4 = set(), []
        for k in blocks:
            o = assign[k.id]
            if o[0] != "own":
                self.pairs.add((k.batch, o[1]))
                if o[0] == "T" and o[2] == "R4":
                    self.r4.append((k.id, o[1], o[3][1], o[3][0], f"{k.w}>{o[3][0]}", f"{o[3][0]}>{k.h}"))

    def window(self, b):
        bt = self.batches[b]
        return max(1, bt.a - self.early), bt.e

    def plans(self, sol):
        out = []
        for b in self.ids:
            ri, day = sol[b]
            u = self.batches[b].unit
            out.append(fe.Plan(b, u, day, self.T[b], self.cands[b][ri]["steps"], tuple(fb.H[u])))
        return out

    def evaluate(self, sol):
        """返回 dict：feasible、违例列表、三项目标、V、逐批结果。"""
        res, whs = fe.simulate(self.plans(sol), self.D)
        viol = []
        viol_ret = []  # 只在“留置算到车队回站”口径下才违反的留置（主口径之外的敏感性）
        active = defaultdict(lambda: defaultdict(int))
        for b in self.ids:
            r, (ri, day) = res[b], sol[b]
            lo, hi = self.window(b)
            if not lo <= day <= hi:
                viol.append(("S2", b))
            if r.end_day > LAST_DAY:
                viol.append(("S1", b))
            if r.flags:
                viol.append(("flag", b, r.flags))
            u = self.batches[b].unit
            for d in range(r.start_day, r.end_day + 1):
                active[u][d] += 1
            steps = self.cands[b][ri]["steps"]
            left_at = {}
            for st, lg in zip(steps, r.logs):
                if (st.load or st.unload) and fr.queue_violates(lg):
                    viol.append(("S10排队", b, st.node))
                if fr.LEAVE_WAIT_LIMIT and st.rejoin and st.node in left_at:
                    le = left_at.pop(st.node)
                    if fr.hold_violates(le, lg):
                        viol.append(("S10留置", b, st.node))
                    if fr.S10_HOURS is not None and fr.hold_violates(le, lg, "return"):
                        viol_ret.append(("S10留置", b, st.node))  # 敏感性：留置算到车队回站
                if st.leave:
                    left_at[st.node] = lg.end
        for u, days in active.items():
            if max(days.values()) > 2:
                viol.append(("S4", u))
        for kid, be, br, hx, g_in, g_out in self.r4:
            t_un = next(lg.end for st, lg in zip(self.cands[be][sol[be][0]]["steps"], res[be].logs) if g_in in st.unload)
            t_ar = next(lg.arrive for st, lg in zip(self.cands[br][sol[br][0]]["steps"], res[br].logs) if g_out in st.load)
            if t_ar < t_un:  # spec R4：β′ 到达 h_x 的时刻 ≥ β 在 h_x 卸完的时刻（A5 前误用了开始作业时刻）
                viol.append(("R4先后", be, br))
            if R4_RULE == "batch" and res[br].start_day <= res[be].end_day:  # D15 备选：整批先后
                viol.append(("R4整批先后", be, br))
        tau = sum(res[b].tau for b in self.ids)
        L = sum(res[b].Lbar for b in self.ids)
        delta = sum(abs(sol[b][1] - self.batches[b].a) for b in self.ids)
        V = sum(1 for (b0, be) in self.pairs if not (max(1, self.batches[b0].a - 6) <= sol[be][1] <= self.batches[b0].e))
        Dtot = sum(res[b].D for b in self.ids)
        vk = sum(res[b].veh_km for b in self.ids)
        other = [v for v in viol if v[0] != "S10留置"]
        return dict(feasible=not viol, feasible_ret=not other and not viol_ret, viol=viol, tau=tau, L=L, delta=delta, V=V, D=Dtot,
                    veh_km=vk, res=res, whs=whs)

    # ---------- 基线 ----------
    def baseline(self):
        order = sorted(self.ids, key=lambda b: (self.batches[b].a, b))
        sol = {}
        for b in order:
            a, (lo, hi) = self.batches[b].a, self.window(b)
            tries = list(range(a, hi + 1)) + list(range(a - 1, lo - 1, -1))
            ok = False
            # 先用基线路线；所有出发日都排不出时，才按里程从短到长换用其他候选路线
            routes = [self.base_idx[b]] + sorted((i for i in range(len(self.cands[b])) if i != self.base_idx[b]),
                                                 key=lambda i: self.cands[b][i]["D"])
            for ri in routes:
                for day in tries:
                    sol[b] = (ri, day)
                    sub = _Sub(self, sol)
                    if sub.evaluate(sol)["feasible"]:
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                # 回退一步：与 b 有 R4 关系且已排入的批次，按里程从短到长换路线、重选出发日，再试 b
                partners = [x[1] for x in self.r4 if x[2] == b and x[1] in sol] + [x[2] for x in self.r4 if x[1] == b and x[2] in sol]
                for p in partners:
                    keep_p = sol[p]
                    ap, (lop, hip) = self.batches[p].a, self.window(p)
                    tries_p = list(range(ap, hip + 1)) + list(range(ap - 1, lop - 1, -1))
                    for rp in sorted(range(len(self.cands[p])), key=lambda i: self.cands[p][i]["D"]):
                        for dp in tries_p:
                            for ri in routes:
                                for day in tries:
                                    sol[p], sol[b] = (rp, dp), (ri, day)
                                    if _Sub(self, sol).evaluate(sol)["feasible"]:
                                        ok = True
                                        break
                                if ok:
                                    break
                            if ok:
                                break
                        if ok:
                            break
                    if ok:
                        break
                    sol[p] = keep_p
            if not ok:
                sol[b] = (self.base_idx[b], a)  # 留给调用方报告
        return sol

    # ---------- 主路线：坐标下降 ----------
    def score(self, ev, ref):
        """J1：区间归一化等权和；ref = dict(l=(tau,L,delta), u=(tau,L,delta))。"""
        zs = []
        for key, l, u in zip(("tau", "L", "delta"), ref["l"], ref["u"]):
            den = (u - l) if u - l > 1e-9 else 1.0
            zs.append((ev[key] - l) / den)
        if self.agg == "sum":
            return sum(zs), ev["V"]
        if self.agg == "minimax":
            return max(zs) + 1e-6 * sum(zs), ev["V"]
        return sum(w * z for w, z in zip(self.agg, zs)), ev["V"]

    def improve(self, sol, ref, max_sweeps=20, log=None):
        sol = dict(sol)
        cur = self.evaluate(sol)
        best = self.score(cur, ref) if cur["feasible"] else (float("inf"), 0)
        for sweep in range(max_sweeps):
            changed = False
            for b in self.ids:
                lo, hi = self.window(b)
                keep = sol[b]
                for ri in range(len(self.cands[b])):
                    for day in range(lo, hi + 1):
                        if (ri, day) == keep:
                            continue
                        sol[b] = (ri, day)
                        ev = self.evaluate(sol)
                        if ev["feasible"]:
                            sc = self.score(ev, ref)
                            if sc < (best[0] - 1e-12, best[1]) or (abs(sc[0] - best[0]) <= 1e-12 and sc[1] < best[1]):
                                best, keep, changed = sc, (ri, day), True
                    sol[b] = keep
                sol[b] = keep
            if log:
                log(sweep, best)
            if not changed:
                break
        return sol, best


def _improve_pairs(self, sol, ref, log=None):
    """成对邻域：对共用排队仓库、同单位或有 R4 关系的两个批次，联合枚举 (路线, 出发日)。返回 (解, 分数, 是否改进)。"""
    sol = dict(sol)
    best = self.score(self.evaluate(sol), ref)
    whs = {b: {s.node for c in self.cands[b] for s in c["steps"] if (s.load or s.unload) and s.node not in fb.H[self.batches[b].unit]} for b in self.ids}
    link = {(x[1], x[2]) for x in self.r4} | {(x[2], x[1]) for x in self.r4}
    improved = False
    for i, b1 in enumerate(self.ids):
        for b2 in self.ids[i + 1:]:
            w1, w2 = self.window(b1), self.window(b2)
            near = w1[0] <= w2[1] + 10 and w2[0] <= w1[1] + 10
            if not (((whs[b1] & whs[b2]) or self.batches[b1].unit == self.batches[b2].unit) and near or (b1, b2) in link):
                continue
            k1, k2 = sol[b1], sol[b2]
            # 全候选集上成对枚举组合数过大：路线只取帕累托子集（加上当前路线），出发日全试
            R1 = sorted(set(self.pareto[b1]) | {sol[b1][0]})
            R2 = sorted(set(self.pareto[b2]) | {sol[b2][0]})
            for r1 in R1:
                for d1 in range(w1[0], w1[1] + 1):
                    for r2 in R2:
                        for d2 in range(w2[0], w2[1] + 1):
                            if (r1, d1) == sol[b1] or (r2, d2) == sol[b2]:
                                continue  # 单批改动已由坐标下降覆盖
                            sol[b1], sol[b2] = (r1, d1), (r2, d2)
                            ev = self.evaluate(sol)
                            if ev["feasible"]:
                                sc = self.score(ev, ref)
                                if sc < (best[0] - 1e-12, best[1]) or (abs(sc[0] - best[0]) <= 1e-12 and sc[1] < best[1]):
                                    best, k1, k2, improved = sc, (r1, d1), (r2, d2), True
                            sol[b1], sol[b2] = k1, k2
            sol[b1], sol[b2] = k1, k2
            if log and improved:
                log(b1, b2, best)
    return sol, best, improved


Instance.improve_pairs = _improve_pairs


class _Sub:
    """只含已排入批次的子实例（基线逐批插入时用）。"""

    def __init__(self, inst, sol):
        self.__dict__.update(inst.__dict__)
        self.ids = sorted(sol)
        self.pairs = {(b0, be) for (b0, be) in inst.pairs if be in sol}
        self.r4 = [x for x in inst.r4 if x[1] in sol and x[2] in sol]

    evaluate = Instance.evaluate
    plans = Instance.plans
    window = Instance.window


# ---------- 全候选集上的补充搜索（R33 起）----------
def key3(inst, ev, ref):
    """最终比较键：(合成分, V, 总里程)。总里程是人裁之前的默认第三级（evidence R31：同分同 V 的方案总里程不同）。"""
    sc, V = inst.score(ev, ref)
    return (round(sc, 12), V, ev["D"])


def fixed_day_search(inst, ref, days, starts, seed=0, sweeps=6, slack=3, init=None):
    """固定出发日、只换路线的坐标下降，多起点。起点 0 = init 的路线（若给），其余随机（孤立 τ ≤ 最少 + slack）。返回 (最好解, 键)。"""
    import random as _r
    rng = _r.Random(seed)
    mt = {b: min(c["tau"] for c in inst.cands[b]) for b in inst.ids}
    ok_r = {b: [i for i, c in enumerate(inst.cands[b]) if c["tau"] <= mt[b] + slack] for b in inst.ids}
    best, best_k = None, (float("inf"),)
    for s in range(starts):
        if s == 0 and init is not None:
            sol = {b: (init[b][0], days[b]) for b in inst.ids}
        else:
            sol = {b: (rng.choice(ok_r[b]), days[b]) for b in inst.ids}
        ev = inst.evaluate(sol)
        cur = key3(inst, ev, ref) if ev["feasible"] else (float("inf"),)
        for _ in range(sweeps):
            changed = False
            for b in inst.ids:
                keep = sol[b]
                for ri in ok_r[b]:
                    if ri == keep[0]:
                        continue
                    sol[b] = (ri, days[b])
                    e2 = inst.evaluate(sol)
                    if e2["feasible"]:
                        k2 = key3(inst, e2, ref)
                        if k2 < cur:
                            cur, keep, changed = k2, sol[b], True
                sol[b] = keep
            if not changed:
                break
        if cur < best_k:
            best, best_k = dict(sol), cur
    return best, best_k


def polish(inst, sol, ref, max_sweeps=10):
    """坐标下降（路线 × 出发日），按 (合成分, V, 总里程) 比较：在合成分与 V 不变的前提下压低总里程。"""
    sol = dict(sol)
    cur = key3(inst, inst.evaluate(sol), ref)
    for _ in range(max_sweeps):
        changed = False
        for b in inst.ids:
            lo, hi = inst.window(b)
            keep = sol[b]
            for ri in range(len(inst.cands[b])):
                for day in range(lo, hi + 1):
                    if (ri, day) == keep:
                        continue
                    sol[b] = (ri, day)
                    e2 = inst.evaluate(sol)
                    if e2["feasible"]:
                        k2 = key3(inst, e2, ref)
                        if k2 < cur:
                            cur, keep, changed = k2, (ri, day), True
                sol[b] = keep
        if not changed:
            break
    return sol, cur
