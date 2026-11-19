"""F 题：由指派生成每个最终批次的货组，并枚举批内路线（spec v2.1 §5.2、§5.3 S11–S15）。

货组 = (装车点, 卸车点) 相同的货；路线 = 车队依次到访的站点及在每站的卸、装、留置、汇合动作。
枚举规则：
- 到站先汇合（若此前在该站留置过）、再卸下目的地为该站的全部货、再装该站全部待装货；
- 装完后可选择把“刚装的货”留置在该站（之后必须回来汇合），这同时覆盖了 K1 的“重复到访”；
- 不做无动作的到访；每个站点至多到访 MAX_VISIT 次；里程超过上限的剪掉；行驶车队装载量不超过其车数。
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


def batch_groups(assign, batches, blocks, cap):
    """返回 {批次: {gid: Group}}，只含保留的最终批次。"""
    raw = defaultdict(lambda: defaultdict(lambda: [0.0, []]))
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
        elif case == "R3":
            add(beta, k.w, aux, sx, k.id, "代领")
        elif case == "R4":
            hx, b2 = aux
            add(beta, k.w, hx, sx, k.id, "代领")
            add(b2, hx, k.h, k.s(cap, k.owner), k.id, "领回")
    out = {}
    for beta, gs in raw.items():
        assert beta in kept, f"批 {beta} 无自有块却有货"
        out[beta] = {f"{a}>{b}": Group(f"{a}>{b}", a, b, s, parts) for (a, b), (s, parts) in gs.items()}
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


def enumerate_routes(unit, T, groups, D, max_km=MAX_KM, allow_leave=True):
    """返回完整路线列表，每条为 list[fe.Step]（末尾为回驻地）。"""
    gids = list(groups)
    s = {g: groups[g].s for g in gids}
    res = []

    def dfs(pos, pending, onboard, left, visits, dist, movT, steps):
        if dist > max_km + 1e-9:
            return
        if not pending and not onboard and not left:
            d = float(D.at[pos, unit]) if pos != unit else 0.0
            if dist + d <= max_km + 1e-9:
                res.append(steps + [fe.Step(unit)])
            return
        cand = {groups[g].unload for g in onboard} | {groups[g].load for g in pending} | set(left)
        for n in sorted(cand):
            if n == pos or visits.get(n, 0) >= MAX_VISIT:
                continue
            d = float(D.at[pos, n])
            ob, lf, mT = set(onboard), dict(left), movT
            rejoin = n in lf
            if rejoin:
                grp = lf.pop(n)
                ob |= grp
                mT += fe.ceil_(sum(s[g] for g in grp))
            un = {g for g in ob if groups[g].unload == n}
            ob -= un
            ld = {g for g in pending if groups[g].load == n}
            if not (rejoin or un or ld):
                continue
            v2 = dict(visits)
            v2[n] = v2.get(n, 0) + 1
            pend2 = pending - ld
            base = dict(node=n, unload={g: s[g] for g in sorted(un)}, load={g: s[g] for g in sorted(ld)}, rejoin=rejoin)
            # 方案一：装上带走
            if sum(s[g] for g in ob | ld) <= mT + 1e-9:
                dfs(n, pend2, ob | ld, lf, v2, dist + d, mT, steps + [fe.Step(**base)])
            # 方案二：装上后留置（之后回来汇合）
            if allow_leave and ld and pend2 and n not in lf and v2[n] < MAX_VISIT and not any(groups[g].unload == n for g in ld):
                c = fe.ceil_(sum(s[g] for g in ld))
                if c <= mT and sum(s[g] for g in ob) <= mT - c + 1e-9:
                    lf2 = dict(lf)
                    lf2[n] = set(ld)
                    dfs(n, pend2, ob, lf2, v2, dist + d, mT - c, steps + [fe.Step(leave=sorted(ld), **base)])

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
            if lg.arrive[0] - left_at.pop(st.node) - 1 > 1:
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
