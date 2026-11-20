"""F 题问题 4：指派、路线、排程的联合邻域搜索（spec v2.2 §12-J3）。

批次数固定（默认取问题 3 的批次数）。合成目标 = 五项区间归一化值的等权和：
  执行总时间、载货总行驶距离、开始偏离（沿用问题 3 的标尺：下界 / 规则基线），
  失衡度 E（0 / 问题 3 方案的值），批次-仓库对（该批次数下的最小值 / 问题 3 方案的值）。
邻域：把一个需求块改派给另一个合法去向（含改回自办）。每次改派只重排受影响的批次。
"""
from __future__ import annotations

import random
import time

import f_blocks as fb
import f_p2
import f_p3


class P4:
    def __init__(self, batches, blocks, cap, D, n_batches, ref3, ref_E, ref_W, u9_min, log=print, **opt_kw):
        self.batches, self.blocks, self.cap, self.D = batches, blocks, cap, D
        self.nB, self.ref3, self.ref_E, self.ref_W, self.u9_min, self.log = n_batches, ref3, ref_E, ref_W, u9_min, log
        self.opts = {k.id: [("own",)] + f_p2.options(k, batches, blocks, cap, D, **opt_kw) for k in blocks}
        self.cache = {}
        self.own_at, self.own_unl = {}, {}
        for k in blocks:
            self.own_at.setdefault((k.batch, k.w), []).append(k.id)
            if k.dir == "领":
                self.own_unl.setdefault((k.batch, k.h), []).append(k.id)

    # ---- 静态合规（与 f_p2.solve 的约束逐条对应）
    def static_ok(self, a):
        B, K, cap = self.batches, self.blocks, self.cap
        keep = lambda b, w: any(a[j][0] == "own" for j in self.own_at.get((b, w), ()))
        kept = {k.batch for k in K if a[k.id][0] == "own"}
        if len(kept) != self.nB:
            return False
        recv, send = {}, {}
        u9 = 0
        for k in K:
            o = a[k.id]
            if o[0] == "own":
                d = recv if k.dir == "领" else send
                d[k.batch] = d.get(k.batch, 0.0) + k.s(cap, k.owner)
                continue
            beta = o[1]
            x = B[beta].unit
            if k.owner == "U9":
                if x != "U6":
                    return False
                u9 += 1
            sx = k.s(cap, x)
            if o[0] == "REV":
                send[beta] = send.get(beta, 0.0) + sx
                if not keep(beta, k.h) or (o[2] == "R8" and not keep(beta, k.w)):
                    return False
                continue
            case, aux = o[2], o[3]
            d = recv if k.dir == "领" else send
            d[beta] = d.get(beta, 0.0) + sx
            if not keep(beta, k.w):
                return False
            if case in ("R2", "R8") and not keep(beta, k.h):
                return False
            if case in ("R3", "R4"):
                hx = aux if case == "R3" else aux[0]
                if not any(a[j][0] == "own" for j in self.own_unl.get((beta, hx), ())):
                    return False
            if case == "R4":
                hx, b2 = aux
                if not keep(b2, hx):
                    return False
                recv[b2] = recv.get(b2, 0.0) + k.s(cap, k.owner)
            if case == "R5":
                if not any(j.owner == k.owner and j.dir == "交" and j.h == k.h and a[j.id][0] == "T" and a[j.id][1] == beta
                           and a[j.id][2] in ("R7", "R8") for j in K):
                    return False
        if u9 < self.u9_min:
            return False
        for b in kept:
            capT = min(30, B[b].T0 + 3)
            if recv.get(b, 0.0) > capT + 1e-9 or send.get(b, 0.0) > capT + 1e-9:
                return False
        return True

    def instance(self, a):
        return f_p3.Instance(a, self.batches, self.blocks, self.cap, self.D, cache=self.cache, prune=True)  # R25 流程：剪枝候选（全候选下每步约贵 9 倍）

    def score(self, a, ev):
        _, tot, _ = f_p2.summarize(a, self.batches, self.blocks, self.cap)
        z3 = sum((ev[k] - l) / ((u - l) if u - l > 1e-9 else 1.0) for k, l, u in zip(("tau", "L", "delta"), self.ref3["l"], self.ref3["u"]))
        zE = (tot["E"] - self.ref_E[0]) / (self.ref_E[1] - self.ref_E[0])
        zW = (tot["pairs"] - self.ref_W[0]) / (self.ref_W[1] - self.ref_W[0])
        return z3 + zE + zW, dict(tau=ev["tau"], L=ev["L"], delta=ev["delta"], E=tot["E"], pairs=tot["pairs"], A=tot["A"], N=tot["N"], P=tot["P"],
                                  V=ev["V"], D=ev["D"], veh_km=ev["veh_km"], B=tot["B"])

    def resched(self, inst, sol, affected, sweeps=2):
        """只对 affected 中的批次重选 (路线, 出发日)，其余不动。返回 (sol, ev) 或 None。"""
        sol = dict(sol)
        for b in affected:
            lo, hi = inst.window(b)
            sol[b] = (inst.base_idx[b], min(max(self.batches[b].a, lo), hi))
        sol = {b: sol[b] for b in inst.ids}
        best_ev = inst.evaluate(sol)
        best = inst.score(best_ev, self.ref3) if best_ev["feasible"] else (float("inf"), 0)
        for _ in range(sweeps):
            changed = False
            for b in affected:
                lo, hi = inst.window(b)
                keep = sol[b]
                for ri in range(len(inst.cands[b])):
                    for day in range(lo, hi + 1):
                        if (ri, day) == keep:
                            continue
                        sol[b] = (ri, day)
                        ev = inst.evaluate(sol)
                        if ev["feasible"]:
                            sc = inst.score(ev, self.ref3)
                            if sc < best:
                                best, keep, best_ev, changed = sc, (ri, day), ev, True
                sol[b] = keep
            if not changed:
                break
        if best[0] == float("inf"):
            return None
        return sol, best_ev

    def search(self, a0, sol0, seed=0, max_passes=30, time_limit=1500):
        rng = random.Random(seed)
        a, inst = dict(a0), self.instance(a0)
        sol = dict(sol0)
        ev = inst.evaluate(sol)
        cur, det = self.score(a, ev)
        self.log(f"起点 合成分 {cur:.4f} {_fmt(det)}")
        t0 = time.time()
        hist = [dict(step=0, score=cur, **det)]
        for p in range(max_passes):
            improved = False
            order = [k.id for k in self.blocks]
            rng.shuffle(order)
            for kid in order:
                best_move = None
                for o in self.opts[kid]:
                    if o == a[kid]:
                        continue
                    a2 = dict(a)
                    a2[kid] = o
                    if not self.static_ok(a2):
                        continue
                    inst2 = self.instance(a2)
                    if not inst2.routable:
                        continue
                    aff = [b for b in inst2.ids if b not in inst.sig or inst2.sig[b] != inst.sig[b]]
                    r = self.resched(inst2, {b: sol[b] for b in inst2.ids if b in sol}, aff)
                    if r is None:
                        continue
                    sc, det2 = self.score(a2, r[1])
                    if sc < cur - 1e-9 and (best_move is None or sc < best_move[0]):
                        best_move = (sc, a2, inst2, r[0], det2, o)
                if best_move:
                    cur, a, inst, sol, det, o = best_move
                    improved = True
                    k = self.blocks[kid]
                    hist.append(dict(step=len(hist), score=cur, block=kid, move=str(o), **det))
                    self.log(f"  第 {p + 1} 遍 块{kid}(批{k.batch}{k.owner} {k.dir}{k.w}) → {o}  合成分 {cur:.4f} {_fmt(det)}  {time.time() - t0:.0f}s")
                if time.time() - t0 > time_limit:
                    break
            if not improved or time.time() - t0 > time_limit:
                break
        return a, sol, inst, cur, hist


def _fmt(d):
    return f"天{d['tau']} L{d['L']:.0f} 偏{d['delta']} E{d['E']:.3f} 对{d['pairs']} A{d['A']:.2f}"
