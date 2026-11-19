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


class Instance:
    def __init__(self, assign, batches, blocks, cap, D):
        self.assign, self.batches, self.blocks, self.cap, self.D = assign, batches, blocks, cap, D
        self.groups = fr.batch_groups(assign, batches, blocks, cap)
        self.ids = sorted(self.groups)
        self.T, self.cands, self.base_idx = {}, {}, {}
        for b in self.ids:
            u = batches[b].unit
            T = fr.batch_T(self.groups[b], u)[0]
            self.T[b] = T
            allr = []
            for steps in fr.enumerate_routes(u, T, self.groups[b], D):
                ev = fr.evaluate(b, u, T, steps, D)
                if ev["ok"]:
                    ev["steps"] = steps
                    acts = [s for s in steps[:-1]]
                    ev["n_pass"] = sum(1 for s in acts if not (s.load or s.unload or s.rejoin))
                    tg = [s.node for s in acts if (s.load or s.unload) and s.node not in fb.H[u]]
                    ev["n_revisit"] = len(tg) - len(set(tg))
                    allr.append(ev)
            assert allr, f"批 {b} 无合规路线"
            simple = [e for e in allr if e["n_leave"] == 0 and e["n_pass"] == 0 and e["n_revisit"] == 0]
            base = min(simple or allr, key=lambda e: (e["D"], e["tau"], e["Lbar"]))
            nd = []
            for a in allr:
                if not any((c["tau"] <= a["tau"] and c["Lbar"] <= a["Lbar"] + 1e-9 and c["D"] <= a["D"] + 1e-9) and
                           (c["tau"] < a["tau"] or c["Lbar"] < a["Lbar"] - 1e-9 or c["D"] < a["D"] - 1e-9) for c in allr):
                    if not any(abs(c["tau"] - a["tau"]) < 1e-9 and abs(c["Lbar"] - a["Lbar"]) < 1e-6 and abs(c["D"] - a["D"]) < 1e-6 for c in nd):
                        nd.append(a)
            if base not in nd:
                nd.append(base)
            self.cands[b] = nd
            self.base_idx[b] = nd.index(base)
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
        return max(1, bt.a - 6), bt.e

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
                if (st.load or st.unload) and lg.start[0] > lg.arrive[0]:
                    idle = lg.start[0] - lg.arrive[0] - 1 + (1 if lg.arrive[1] < 1e-9 else 0)
                    if idle > 1:
                        viol.append(("S10排队", b, st.node))
                if st.rejoin and st.node in left_at and lg.arrive[0] - left_at.pop(st.node) - 1 > 1:
                    viol.append(("S10留置", b, st.node))
                if st.leave:
                    left_at[st.node] = lg.end[0]
        for u, days in active.items():
            if max(days.values()) > 2:
                viol.append(("S4", u))
        for kid, be, br, hx, g_in, g_out in self.r4:
            t_un = next(lg.end for st, lg in zip(self.cands[be][sol[be][0]]["steps"], res[be].logs) if g_in in st.unload)
            t_ld = next(lg.start for st, lg in zip(self.cands[br][sol[br][0]]["steps"], res[br].logs) if g_out in st.load)
            if t_ld < t_un:
                viol.append(("R4先后", be, br))
        tau = sum(res[b].tau for b in self.ids)
        L = sum(res[b].Lbar for b in self.ids)
        delta = sum(abs(sol[b][1] - self.batches[b].a) for b in self.ids)
        V = sum(1 for (b0, be) in self.pairs if not (max(1, self.batches[b0].a - 6) <= sol[be][1] <= self.batches[b0].e))
        Dtot = sum(res[b].D for b in self.ids)
        vk = sum(res[b].veh_km for b in self.ids)
        return dict(feasible=not viol, viol=viol, tau=tau, L=L, delta=delta, V=V, D=Dtot, veh_km=vk, res=res, whs=whs)

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
        z = 0.0
        for key, l, u in zip(("tau", "L", "delta"), ref["l"], ref["u"]):
            den = (u - l) if u - l > 1e-9 else 1.0
            z += (ev[key] - l) / den
        return z, ev["V"]

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
            for r1 in range(len(self.cands[b1])):
                for d1 in range(w1[0], w1[1] + 1):
                    for r2 in range(len(self.cands[b2])):
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
