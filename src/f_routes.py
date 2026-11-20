"""F 题：由指派生成每个最终批次的货组，并枚举批内路线（spec v2.1 §5.2、§5.3 S11–S15）。

货组 = (装车点, 卸车点) 相同的货；路线 = 车队依次到访的站点及在每站的卸、装、留置、汇合动作。
枚举规则：
- 到站先汇合（若此前在该站留置过）、再卸下目的地为该站的全部货、再装该站待装货的任一子集（其余留到下次到访再装）；
- 装完后可选择把刚装的货的任一子集留置在该站（之后必须回来汇合）；
- 每个站点至多“有动作地”到访 MAX_VISIT 次；里程超过上限的剪掉；行驶车队装载量不超过其车数；
- S15：两个作业站之间可以途经本批次自己的站点（驻地、执行单位可用的队属仓库、本批次涉及的仓库）而不作业。
  实现：在这些站点构成的子图上取最短路，途经点作为无动作的 Step 写进路线（里程、时间逐段计算）。
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import f_blocks as fb
import f_engine as fe

MAX_VISIT = 2
MAX_KM = 2000.0


@dataclass
class Group:
    gid: str
    load: str
    unload: str
    s: float
    parts: list = field(default_factory=list)  # (块id, 角色)：own / 代领 / 代交 / 领回
    after: str = ""  # 非空时：本组须在“从该站装车的货组”装车之后才能装（R5：先到 h_k 装代交货，后到 w_k 代领）


def batch_groups(assign, batches, blocks, cap):
    """返回 {批次: {gid: Group}}，只含保留的最终批次。"""
    raw = defaultdict(lambda: defaultdict(lambda: [0.0, []]))
    after = {}
    kept = {k.batch for k in blocks if assign[k.id][0] == "own"}

    def add(beta, a, b, s, kid, role):
        g = raw[beta][a, b]
        g[0] += s
        g[1].append((kid, role))

    for k in blocks:
        o = assign[k.id]
        if o[0] == "own":
            x = k.owner
            if k.dir == "领":
                add(k.batch, k.w, k.h, k.s(cap, x), k.id, "own")
            else:
                add(k.batch, k.h, k.w, k.s(cap, x), k.id, "own")
            continue
        beta = o[1]
        x = batches[beta].unit
        sx = k.s(cap, x)
        if o[0] == "REV":
            add(beta, k.w, k.h, sx, k.id, "代交")
            continue
        case, aux = o[2], o[3]
        if k.dir == "交":
            add(beta, k.h, k.w, sx, k.id, "代交")
        elif case in ("R1", "R2", "R5"):
            add(beta, k.w, k.h, sx, k.id, "代领")
            if case == "R5":
                after[beta, (k.w, k.h)] = k.h
        elif case == "R3":
            add(beta, k.w, aux, sx, k.id, "代领")
        elif case == "R4":
            hx, b2 = aux
            add(beta, k.w, hx, sx, k.id, "代领")
            add(b2, hx, k.h, k.s(cap, k.owner), k.id, "领回")
    out = {}
    for beta, gs in raw.items():
        assert beta in kept, f"批 {beta} 无自有块却有货"
        out[beta] = {f"{a}>{b}": Group(f"{a}>{b}", a, b, s, parts, after.get((beta, (a, b)), "")) for (a, b), (s, parts) in gs.items()}
    return out


def batch_T(groups, unit):
    """运力：领侧（卸到队属仓库或暂存点的货）与交侧分别求和取大。领/交按货组是否从执行单位可用仓库装车区分。"""
    own = set(fb.H[unit])
    send = sum(g.s for g in groups.values() if any(r in ("own", "代交") for _, r in g.parts) and _is_send(g, own))
    recv = sum(g.s for g in groups.values()) - send
    return fe.ceil_(max(recv, send)), recv, send


def _is_send(g, own):
    # 交侧：自有送交（从自己仓库装）或代交
    roles = {r for _, r in g.parts}
    if roles <= {"代交"}:
        return True
    if "own" in roles and g.load in own and g.unload not in own:
        return True
    return False


def _subsets(xs):
    xs = list(xs)
    return [tuple(x for i, x in enumerate(xs) if m >> i & 1) for m in range(1 << len(xs))]


def enumerate_routes(unit, T, groups, D, max_km=MAX_KM, allow_leave=True):
    """返回完整路线列表，每条为 list[fe.Step]（末尾为回驻地）。"""
    gids = list(groups)
    s = {g: groups[g].s for g in gids}
    res = []
    own_set = set(fb.H[unit])
    # S12：含自有块、从可用队属仓库装车送往外面的货组，须在到访任何外部仓库作业之前装车
    own_send = {g for g in gids if groups[g].load in own_set and groups[g].unload not in own_set and any(r == "own" for _, r in groups[g].parts)}
    # S15：允许途经的站点集合及其上的最短路
    nodes = sorted({unit} | set(fb.H[unit]) | {g.load for g in groups.values()} | {g.unload for g in groups.values()})
    dc = {(a, b): (0.0 if a == b else float(D.at[a, b])) for a in nodes for b in nodes}
    nxt = {(a, b): b for a in nodes for b in nodes}
    for k in nodes:
        for a in nodes:
            for b in nodes:
                if dc[a, k] + dc[k, b] < dc[a, b] - 1e-9:
                    dc[a, b] = dc[a, k] + dc[k, b]
                    nxt[a, b] = nxt[a, k]

    def via(a, b):
        """a 到 b 最短路上的途经点（不含 a、b），作为无动作 Step。"""
        out, cur = [], a
        while nxt[cur, b] != b:
            cur = nxt[cur, b]
            out.append(fe.Step(cur))
        return out

    def dfs(pos, pending, onboard, left, visits, dist, movT, steps, ext=False):
        if dist > max_km + 1e-9:
            return
        if ext and pending & own_send:
            return
        if not pending and not onboard and not left:
            d = dc[pos, unit]
            if dist + d <= max_km + 1e-9:
                res.append(steps + via(pos, unit) + [fe.Step(unit)])
            return
        cand = {groups[g].unload for g in onboard} | {groups[g].load for g in pending} | set(left)
        for n in sorted(cand):
            if n == pos or visits.get(n, 0) >= MAX_VISIT:
                continue
            if n in left and n != next(reversed(left)):
                continue  # S11：多站留置按相反顺序汇合
            ob, lf, mT = set(onboard), dict(left), movT
            rejoin = n in lf
            if rejoin:
                grp = lf.pop(n)
                ob |= grp
                mT += fe.ceil_(sum(s[g] for g in grp))
            un = {g for g in ob if groups[g].unload == n}
            ob -= un
            ld_all = sorted(g for g in pending if groups[g].load == n)
            v2 = dict(visits)
            v2[n] = v2.get(n, 0) + 1
            may_defer = v2[n] < MAX_VISIT
            legs = [(dc[pos, n], via(pos, n))]
            if float(D.at[pos, n]) > dc[pos, n] + 1e-9:
                legs.append((float(D.at[pos, n]), []))  # 直达虽远，但可能少跨一天
            for S in _subsets(ld_all):
                if len(S) < len(ld_all) and not may_defer:
                    continue
                if not (rejoin or un or S):
                    continue
                if ext and set(S) & own_send:
                    continue
                if any(groups[g].after and any(groups[x].load == groups[g].after for x in pending if x not in S) for g in S):
                    continue  # R5：代交货尚未在 h_k 装车
                ext2 = ext or (n.startswith("W") and n not in own_set)
                Sset = set(S)
                pend2 = pending - Sset
                base = dict(node=n, unload={g: s[g] for g in sorted(un)}, load={g: s[g] for g in S}, rejoin=rejoin)
                leave_opts = [()]
                if allow_leave and S and pend2 and n not in lf and may_defer:
                    leave_opts += [L for L in _subsets(S) if L]
                for L in leave_opts:
                    Lset = set(L)
                    c = fe.ceil_(sum(s[g] for g in L)) if L else 0
                    if c > mT or sum(s[g] for g in (ob | Sset) - Lset) > mT - c + 1e-9:
                        continue
                    lf2 = dict(lf)
                    if L:
                        lf2[n] = Lset
                    for d, pre in legs:
                        dfs(n, pend2, (ob | Sset) - Lset, lf2, v2, dist + d, mT - c, steps + pre + [fe.Step(leave=sorted(L), **base)], ext2)

    dfs(unit, frozenset(gids), set(), {}, {}, 0.0, T, [])
    return res


def evaluate(bid, unit, T, steps, D, start_day=10):
    """孤立回放一条路线；返回 dict(D, Lbar, veh_km, tau, ok, res)。ok=False 表示违反 S10（留置整日闲置 > 1 天）或引擎报错。"""
    plan = fe.Plan(bid, unit, start_day, T, steps, tuple(fb.H[unit]))
    r = fe.simulate([plan], D)[0][bid]
    ok = not r.flags
    left_at = {}
    for st, lg in zip(steps, r.logs):
        if st.rejoin and st.node in left_at:
            # S10：留置车整日闲置天数；汇合车队 16:00 才到时，当天也算闲置
            if lg.arrive[0] - left_at.pop(st.node) - 1 + (1 if lg.arrive[1] >= fe.DAY_H - 1e-9 else 0) > 1:
                ok = False
        if st.leave:
            left_at[st.node] = lg.end[0]
    return dict(D=r.D, Lbar=r.Lbar, veh_km=r.veh_km, tau=r.tau, ok=ok, res=r, n_leave=sum(bool(st.leave) for st in steps))


def candidates(bid, unit, T, groups, D, max_km=MAX_KM, allow_leave=True):
    """枚举并评估，返回按 (tau, Lbar, D) 非支配的候选列表（每项含 steps 和指标）。"""
    out = []
    for steps in enumerate_routes(unit, T, groups, D, max_km, allow_leave):
        ev = evaluate(bid, unit, T, steps, D)
        if ev["ok"]:
            ev["steps"] = steps
            out.append(ev)
    nd = []
    for a in out:
        dom = False
        for b in out:
            if b is a:
                continue
            le = b["tau"] <= a["tau"] and b["Lbar"] <= a["Lbar"] + 1e-9 and b["D"] <= a["D"] + 1e-9
            lt = b["tau"] < a["tau"] or b["Lbar"] < a["Lbar"] - 1e-9 or b["D"] < a["D"] - 1e-9
            if le and (lt or (b["n_leave"] < a["n_leave"]) or (b["n_leave"] == a["n_leave"] and id(b) < id(a))):
                dom = True
                break
        if not dom:
            nd.append(a)
    return nd, len(out)
