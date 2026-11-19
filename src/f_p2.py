"""F 题问题 2：需求块指派的整数规划（spec v2.1 §3–§5.2、§4.4）。

每个块 k 的可选项：
  ('own',)                       留在原批次
  ('T', β, case, aux)            转给批次 β（别的单位），case ∈ R1..R8；
                                 aux = R3 的卸货仓 hx；R4 的 (hx, β')；其余为 None
  ('REV', β, case)               领型内部互转反转为代交（裁 D17），case ∈ R6..R8
候选项按“原始目标仓库”生成（上界），是否成立由模型内的保留约束决定；不做“≤3 台”预筛（spec §11）。

字典序：L0 U9 交给 U6 的块数最多（C6 的实现）→ L1 批次最少 → L2 代领代交等效车数最少 → L3 V⁰ 最少。
里程上限 C4 依赖路线，由调用方用 no-good 割（forbid）迭代处理。
"""
from __future__ import annotations

import math
from collections import defaultdict

import gurobipy as gp

import f_blocks as fb

NEAR = 150


def options(k, batches, blocks, cap, D, allow_R4=True, only_shared=False, near=NEAR, allow_rev=True, allow_R3=True):
    """块 k 的全部候选转移项（不含 'own'）。"""
    y = k.owner
    out = []
    for bt in batches.values():
        x = bt.unit
        if x == y or (y == "U9" and x != "U6"):
            continue
        W = fb.targets(bt)
        Hx = set(fb.H[x])
        own_unload = {q.h for q in bt.blocks if q.dir == "领" and q.h in Hx}
        if k.w in W:
            if k.dir == "领":
                if k.h in Hx:
                    out.append(("T", bt.id, "R1", None))
                elif not only_shared:
                    if k.h in W:
                        out.append(("T", bt.id, "R2", None))
                    else:
                        for hx in sorted(own_unload):
                            if allow_R3 and D.at[y, hx] <= near:
                                out.append(("T", bt.id, "R3", hx))
                            if allow_R4:
                                for b2 in batches.values():
                                    if b2.unit == y and hx in fb.targets(b2) and bt.a - 6 <= b2.e:
                                        out.append(("T", bt.id, "R4", (hx, b2.id)))
                        if D.at[x, k.h] <= near:
                            out.append(("T", bt.id, "R5", None))
            else:
                if k.h in Hx:
                    out.append(("T", bt.id, "R6", None))
                elif not only_shared:
                    if k.h in W:
                        out.append(("T", bt.id, "R8", None))
                    elif D.at[x, k.h] <= near:
                        out.append(("T", bt.id, "R7", None))
        # 反转：货在 k.w（发方队属仓库），要到 k.h；执行批次须把 k.h 当目标仓库
        if allow_rev and k.inner and k.dir == "领" and k.h in W:
            if k.w in Hx:
                out.append(("REV", bt.id, "R6"))
            elif not only_shared:
                if k.w in W:
                    out.append(("REV", bt.id, "R8"))
                elif D.at[x, k.w] <= near:
                    out.append(("REV", bt.id, "R7"))
    return out


def solve(batches, blocks, cap, D, allow_R4=True, only_shared=False, near=NEAR, allow_rev=True,
          forbid=(), fix_batches=None, levels=("U9", "B", "A", "V0"), max_extra=3, verbose=False, c6="max", allow_R3=True):
    """返回 dict(assign={块id: 选项}, stats=..., status=...)。forbid：若干选项集合，每个集合不得同时全选。
    fix_batches：把批次数固定为给定值（做折衷曲线时用）；此时 levels 中的 'B' 被跳过。"""
    m = gp.Model("p2")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.MIPGap = 0.0
    opts = {k.id: [("own",)] + options(k, batches, blocks, cap, D, allow_R4, only_shared, near, allow_rev, allow_R3) for k in blocks}
    z = {(kid, o): m.addVar(vtype="B") for kid, os in opts.items() for o in os}
    y = {b: m.addVar(vtype="B") for b in batches}
    own_at = defaultdict(list)  # (批次, 仓库) -> 自有块
    own_unl = defaultdict(list)  # (批次, 卸货仓 h) -> 自有领块
    for k in blocks:
        own_at[k.batch, k.w].append(k.id)
        if k.dir == "领":
            own_unl[k.batch, k.h].append(k.id)
    keep = lambda b, w: gp.quicksum(z[j, ("own",)] for j in own_at[b, w])
    recv = defaultdict(list)  # 批次 -> [(系数, 变量)] 领侧
    send = defaultdict(list)
    deleg = []  # (等效车数, 变量)
    pair = defaultdict(list)  # (原批次, 执行批次) -> 变量
    for k in blocks:
        m.addConstr(gp.quicksum(z[k.id, o] for o in opts[k.id]) == 1)
        m.addConstr(z[k.id, ("own",)] <= y[k.batch])
        (recv if k.dir == "领" else send)[k.batch].append((k.s(cap, k.owner), z[k.id, ("own",)]))
        for o in opts[k.id][1:]:
            v, beta = z[k.id, o], o[1]
            x = batches[beta].unit
            sx = k.s(cap, x)
            deleg.append((sx, v))
            pair[k.batch, beta].append(v)
            if o[0] == "REV":
                send[beta].append((sx, v))
                m.addConstr(v <= keep(beta, k.h))
                if o[2] == "R8":
                    m.addConstr(v <= keep(beta, k.w))
                continue
            case, aux = o[2], o[3]
            (recv if k.dir == "领" else send)[beta].append((sx, v))
            m.addConstr(v <= keep(beta, k.w))
            if case in ("R2", "R8"):
                m.addConstr(v <= keep(beta, k.h))
            if case == "R3":
                m.addConstr(v <= gp.quicksum(z[j, ("own",)] for j in own_unl[beta, aux]))
            if case == "R4":
                hx, b2 = aux
                m.addConstr(v <= gp.quicksum(z[j, ("own",)] for j in own_unl[beta, hx]))
                m.addConstr(v <= keep(b2, hx))
                recv[b2].append((k.s(cap, k.owner), v))
            if case == "R5":
                mates = [z[j.id, oo] for j in blocks if j.owner == k.owner and j.dir == "交" and j.h == k.h
                         for oo in opts[j.id][1:] if oo[0] == "T" and oo[1] == beta and oo[2] in ("R7", "R8")]
                m.addConstr(v <= gp.quicksum(mates))
    for b, bt in batches.items():
        capT = min(30, bt.T0 + max_extra)
        m.addConstr(gp.quicksum(c * v for c, v in recv[b]) <= capT * y[b])
        m.addConstr(gp.quicksum(c * v for c, v in send[b]) <= capT * y[b])
    if c6 == "maximal":
        # C6 的字面读法：U9 保留的块，不得存在“U6 某批次仍保留着去该仓库的自有块”的情形（忽略运力，偏严）
        for k in blocks:
            if k.owner != "U9":
                continue
            for o in opts[k.id][1:]:
                if o[0] == "T" and o[2] in ("R1", "R6"):
                    for j in own_at[o[1], k.w]:
                        m.addConstr(z[k.id, ("own",)] + z[j, ("own",)] <= 1)
    for S in forbid:
        m.addConstr(gp.quicksum(z[kid, o] for kid, o in S) <= len(S) - 1)
    # 目标
    u9 = gp.quicksum(v for (kid, o), v in z.items() if blocks[kid].owner == "U9" and o[0] != "own")
    nB = gp.quicksum(y.values())
    A = gp.quicksum(c * v for c, v in deleg)
    pv = []
    for (b, beta), vs in pair.items():
        bb, be = batches[b], batches[beta]
        if bb.a - 6 > be.e or be.a - 6 > bb.e:  # 允许出发区间不相交
            p = m.addVar(vtype="B")
            for v in vs:
                m.addConstr(p >= v)
            pv.append(p)
    V0 = gp.quicksum(pv)
    # 批次-仓库对（供问题 4 的种子与下界）
    tg = {}

    def tgt(b, w, v):
        if w in fb.H[batches[b].unit]:
            return
        if (b, w) not in tg:
            tg[b, w] = m.addVar(vtype="B")
        m.addConstr(tg[b, w] >= v)

    for (kid, o), v in z.items():
        k = blocks[kid]
        if o[0] == "own":
            tgt(k.batch, k.w, v)
        elif o[0] == "REV":
            tgt(o[1], k.h, v)
        else:
            tgt(o[1], k.w, v)
    Wp = gp.quicksum(tg.values())
    stats = {}
    if fix_batches is not None:
        m.addConstr(nB == fix_batches)
    for lv in levels:
        if lv == "B" and fix_batches is not None:
            stats["B"] = fix_batches
            continue
        expr, sense = {"U9": (u9, gp.GRB.MAXIMIZE), "B": (nB, gp.GRB.MINIMIZE), "A": (A, gp.GRB.MINIMIZE), "V0": (V0, gp.GRB.MINIMIZE),
                       "W": (Wp, gp.GRB.MINIMIZE)}[lv]
        m.setObjective(expr, sense)
        m.optimize()
        if m.Status != gp.GRB.OPTIMAL:
            return dict(status=m.Status, assign=None, stats=stats)
        val = m.ObjVal
        stats[lv] = round(val) if lv != "A" else val
        stats[lv + "_bound"] = m.ObjBound
        if lv == "A":
            m.addConstr(expr <= val + 1e-7)
        else:
            m.addConstr(expr == round(val))
    assign = {kid: o for (kid, o), v in z.items() if v.X > 0.5}
    return dict(status=gp.GRB.OPTIMAL, assign=assign, stats=stats, n_opts=sum(len(v) - 1 for v in opts.values()))


def summarize(assign, batches, blocks, cap):
    """按指派算每个最终批次的 T、N、P、目标仓库集、代领代交量；返回 (逐批表, 汇总)。"""
    R, S, W, items = defaultdict(float), defaultdict(float), defaultdict(set), defaultdict(list)
    A = 0.0
    flow = defaultdict(float)  # (执行单位, 属主) -> 等效车数
    for k in blocks:
        o = assign[k.id]
        if o[0] == "own":
            beta, x, d_, w = k.batch, k.owner, k.dir, k.w
        elif o[0] == "REV":
            beta = o[1]; x = batches[beta].unit; d_ = "交"; w = k.h
        else:
            beta = o[1]; x = batches[beta].unit; d_ = k.dir; w = k.w
        sx = k.s(cap, x)
        (R if d_ == "领" else S)[beta] += sx
        if w not in fb.H[x]:
            W[beta].add(w)
        items[beta].append((k.id, o))
        if o[0] != "own":
            A += sx
            flow[x, k.owner] += sx
            if o[0] == "T" and o[2] == "R4":
                b2 = o[3][1]
                R[b2] += k.s(cap, k.owner)
    rows = []
    for b in sorted(set(R) | set(S)):
        if not any(o[0] == "own" for kid, o in items[b]):
            continue
        T = math.ceil(max(R[b], S[b]) - 1e-9)
        N, P = fb.tnp(T)
        rows.append(dict(batch=b, unit=batches[b].unit, recv=R[b], send=S[b], T=T, T0=batches[b].T0, N=N, P=P,
                         targets="/".join(sorted(W[b])), n_targets=len(W[b])))
    tot = dict(B=len(rows), N=sum(r["N"] for r in rows), P=sum(r["P"] for r in rows), T=sum(r["T"] for r in rows),
               A=A, pairs=sum(r["n_targets"] for r in rows))
    H = defaultdict(float); Rv = defaultdict(float)
    for (x, yv), v in flow.items():
        H[x] += v; Rv[yv] += v
    tot["E"] = sum(abs(H[u] - Rv[u]) for u in fb.UNITS) / (2 * A) if A > 0 else 0.0
    return rows, tot, dict(flow)
