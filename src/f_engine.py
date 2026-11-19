"""F 题时间引擎：按 spec v2.1 §5.3 回放一组批次的实施方案（事件驱动，连续时间）。

时间表示：(day, h)。day 为日序号（4/1 = 1），h 为当天 8:00 起的小时数，0 ≤ h ≤ 8。
规则：
- S5/S6 行驶：62.5 km/h；≤500 km 的路段须当天 16:00 或之前到达才出发，否则次日 8:00；
  >500 km 的路段 8:00 出发，每天 8 小时，途中过夜。
- S7 装卸：一站内卸、装分别对等效车数向上取整，c = ⌈卸⌉ + ⌈装⌉，用时 c/2.5 小时，只在 8:00–16:00，跨日续做。
- S8/S9 目标仓库（非执行单位可用的队属仓库）：单队列先到先服务，每天至多服务 3 支单位；
  每天 8 小时 × 2.5 = 20 台次即日容量。
- S11/S14 留置：把若干货组连同 ⌈s⌉ 辆车留在某站，之后回到该站汇合。
引擎只负责“给定方案算时刻和指标”，不判断方案是否合规（合规由独立检查器负责），但会记录违例线索。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

SPEED = 62.5
RATE = 2.5
DAY_H = 8.0
DAY_KM = 500.0
UNIT_CAP = 3
EPS = 1e-9

# 读法开关（A 层检查 A2 用）。默认值 = spec v2.2，主结果只在默认值下产生。
OPT = dict(
    split_legs=False,    # True：任何路段都可随时出发，行驶到 16:00 停、次日 8:00 续行（S6/G6 的备选）
    split_long=False,    # True：只对 > 500 km 的路段允许随时出发、途中过夜（即 §6 G6 的敏感性）
    no_ceil=False,       # True：作业车数 c = s⁺ + s⁻ 不取整（G7/G15 的备选）
    load_anytime=False,  # True：装卸不受 8:00–16:00 限制，连续作业（录3.9“不考虑仓库的工作时段”的备选读法）
    no_wh_cap=False,     # True：仓库不排队、无日容量（S8/S9 关闭，诊断用）
)


def ceil_(x: float) -> int:
    return int(math.ceil(x - 1e-9))


@dataclass
class Step:
    """车队到达 node 后依次：卸 unload、装 load（{货组: 等效车数}），留置 leave 中的货组；rejoin=True 表示与此前留在该站的车汇合。"""
    node: str
    unload: dict = field(default_factory=dict)
    load: dict = field(default_factory=dict)
    leave: list = field(default_factory=list)
    rejoin: bool = False


@dataclass
class Plan:
    bid: int
    unit: str
    start_day: int
    T: int
    steps: list  # 最后一步应为回到驻地（node == unit）
    own_wh: tuple = ()  # 执行单位可用的队属仓库（不排队、不占目标仓库容量）


@dataclass
class StepLog:
    node: str
    arrive: tuple
    start: tuple
    end: tuple
    depart: tuple
    c_unload: int
    c_load: int
    s_unload: float
    s_load: float
    onboard_after: float
    moving_T: int


@dataclass
class Result:
    bid: int
    logs: list
    D: float
    L_groups: dict  # 货组 -> 在车上行驶的距离
    s_groups: dict
    Lbar: float
    veh_km: float
    start_day: int
    end_day: int
    tau: int
    flags: list


def travel(t: tuple, dist: float):
    """返回 (出发时刻, 到达时刻)。"""
    d, h = t
    if dist <= EPS:
        return (d, h), (d, h)
    hrs = dist / SPEED
    if OPT["split_legs"] or (OPT["split_long"] and dist > DAY_KM + EPS):
        if h >= DAY_H - EPS:
            d, h = d + 1, 0.0
        dep, rem = (d, h), hrs
        while h + rem > DAY_H + EPS:
            rem -= DAY_H - h
            d, h = d + 1, 0.0
        return dep, (d, h + rem)
    if dist <= DAY_KM + EPS:
        if h + hrs <= DAY_H + EPS:
            return (d, h), (d, min(DAY_H, h + hrs))
        return (d + 1, 0.0), (d + 1, hrs)
    if h > EPS:
        d, h = d + 1, 0.0
    n = ceil_(dist / DAY_KM)
    return (d, 0.0), (d + n - 1, (dist - DAY_KM * (n - 1)) / SPEED)


class Warehouse:
    def __init__(self):
        self.free_at = (0, 0.0)
        self.units = {}  # day -> set(unit)
        self.veh = {}  # day -> 台次
        self.log = []  # (bid, unit, day, 台次)

    def serve(self, bid, unit, arrive, c, queued=True):
        """从 arrive 起服务 c 台次；返回 (开始, 结束)。queued=False 时不排队、不计容量（自己的队属仓库）。"""
        queued = queued and not OPT["no_wh_cap"]
        t = max(arrive, self.free_at) if queued else arrive
        d, h = t
        rem, start = float(c), None
        if c == 0:
            return t, t
        if OPT["load_anytime"]:  # 连续作业；h 以当天 8:00 起算，24 小时进一日；不计日容量
            start = (d, h)
            h += rem / RATE
            while h >= 24 - EPS:
                d, h = d + 1, h - 24
            end = (d, h) if h <= DAY_H + EPS else (d + 1, 0.0)
            if queued:
                self.free_at = end
            return start, end
        while rem > EPS:
            if h >= DAY_H - EPS:
                d, h = d + 1, 0.0
            if queued:
                us = self.units.setdefault(d, set())
                if unit not in us and len(us) >= UNIT_CAP:
                    d, h = d + 1, 0.0
                    continue
                us.add(unit)
            if start is None:
                start = (d, h)
            do = min(rem, (DAY_H - h) * RATE)
            h += do / RATE
            rem -= do
            if queued:
                self.veh[d] = self.veh.get(d, 0.0) + do
                self.log.append((bid, unit, d, do))
        end = (d, h)
        if queued:
            self.free_at = end
        return start, end


def simulate(plans: list, dist) -> tuple:
    """回放全部批次。dist 为距离表（DataFrame，.at[i, j]）。返回 ({bid: Result}, {仓库: Warehouse})。"""
    whs: dict = {}
    st = {}
    heap = []
    for p in plans:
        st[p.bid] = dict(i=0, t=(p.start_day, 0.0), pos=p.unit, onboard={}, left={}, moving_T=p.T,
                         D=0.0, L={}, s={}, logs=[], flags=[], arr=None)
        _schedule_travel(p, st[p.bid], dist, heap)
    plan_of = {p.bid: p for p in plans}
    while heap:
        t, bid = heapq.heappop(heap)
        p, s = plan_of[bid], st[bid]
        step = p.steps[s["i"]]
        # 到达 step.node
        if step.rejoin:
            grp = s["left"].pop(step.node, {})
            s["onboard"].update(grp)
            s["moving_T"] += ceil_(sum(grp.values())) if grp else 0
        su, sl = sum(step.unload.values()), sum(step.load.values())
        cu, cl = (su, sl) if OPT["no_ceil"] else (ceil_(su), ceil_(sl))
        queued = step.node.startswith("W") and step.node not in p.own_wh
        if cu + cl > 0:
            wh = whs.setdefault(step.node, Warehouse())
            start, end = wh.serve(bid, p.unit, t, cu + cl, queued)
        else:
            start = end = t
        for g in step.unload:
            if g not in s["onboard"]:
                s["flags"].append(f"卸载不在车上的货组 {g}@{step.node}")
            s["onboard"].pop(g, None)
        for g, v in step.load.items():
            s["onboard"][g] = v
            s["s"][g] = v
            s["L"].setdefault(g, 0.0)
        if step.leave:
            grp = {g: s["onboard"].pop(g) for g in step.leave}
            s["left"][step.node] = grp
            s["moving_T"] -= ceil_(sum(grp.values()))
        load_now = sum(s["onboard"].values())
        if load_now > s["moving_T"] + 1e-6:
            s["flags"].append(f"超载 {load_now:.3f}>{s['moving_T']}@{step.node}")
        s["logs"].append(StepLog(step.node, t, start, end, end, cu, cl, su, sl, load_now, s["moving_T"]))
        s["t"], s["pos"] = end, step.node
        s["i"] += 1
        if s["i"] < len(p.steps):
            _schedule_travel(p, s, dist, heap)
    out = {}
    for p in plans:
        s = st[p.bid]
        if s["left"]:
            s["flags"].append(f"留置未汇合 {list(s['left'])}")
        if s["onboard"]:
            s["flags"].append(f"结束时车上仍有货 {list(s['onboard'])}")
        tot = sum(s["s"].values())
        vk = sum(s["s"][g] * s["L"][g] for g in s["s"])
        end_day = s["logs"][-1].arrive[0]
        out[p.bid] = Result(p.bid, s["logs"], s["D"], dict(s["L"]), dict(s["s"]), vk / tot if tot > 0 else 0.0, vk,
                            p.start_day, end_day, end_day - p.start_day + 1, s["flags"])
    return out, whs


def _schedule_travel(p, s, dist, heap):
    nxt = p.steps[s["i"]].node
    d_km = float(dist.at[s["pos"], nxt]) if s["pos"] != nxt else 0.0
    dep, arr = travel(s["t"], d_km)
    if s["logs"]:
        s["logs"][-1].depart = dep
    s["D"] += d_km
    for g in s["onboard"]:
        s["L"][g] += d_km
    heapq.heappush(heap, (arr, p.bid))


def fmt(t: tuple, year: int = 2026) -> str:
    """(day, h) -> 'm/d h:mm'。"""
    d, h = t
    m, dd = (4, d) if d <= 30 else ((5, d - 30) if d <= 61 else (6, d - 61))
    mins = int(round(h * 60))
    return f"{m}/{dd} {8 + mins // 60}:{mins % 60:02d}"
