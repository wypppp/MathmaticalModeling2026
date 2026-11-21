"""Recompute F v2.6 from the published workbooks. Requires openpyxl."""

import ast
import csv
import sys
import heapq
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction as F
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

OUT = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else OUT.parents[1]
ATT = ROOT / "problem/F/original/附件"
RESULTS = ROOT / "results/F"
H = {
    f"U{i}": set(h.split())
    for i, h in enumerate(
        ["WT", "WS", "WQ", "WR", "WS", "WP", "WQ WU", "WO", "WP", "WS", "WO WS", "WO"],
        1,
    )
}
BASE = datetime(2026, 4, 1)
# One tick = 0.04 minutes. Dates below are zero-based internally.
DAY, OPEN, CLOSE = 36000, 12000, 24000


def read(path, cols, merged=False):
    book = load_workbook(path, data_only=True)
    ws = book.active
    data = [list(r) for r in ws.iter_rows(max_col=cols, values_only=True)]
    if merged:
        for area in ws.merged_cells.ranges:
            if area.min_col == area.max_col <= cols:
                j = area.min_col - 1
                for i in range(area.min_row, area.max_row):
                    data[i][j] = data[area.min_row - 1][j]
    book.close()
    return data


def original(n, cols, merged=False):
    return read(next(ATT.glob(f"附件{n} *.xlsx")), cols, merged)


def window(value):
    if isinstance(value, (int, float)):
        value = from_excel(value)
    pairs = (
        [(value.month, value.day)]
        if isinstance(value, date)
        else re.findall(r"(\d+)月(\d+)", value)
    )
    days = [(datetime(2026, int(m), int(d)) - BASE).days for m, d in pairs]
    return days[0], days[-1]


def stamp(t):
    return BASE + timedelta(milliseconds=t * 2400)


def drive(t, km):
    tm = t % DAY
    duration = 24 * km
    if km > 500:
        depart = (t // DAY + (tm > OPEN)) * DAY + OPEN
        return depart, depart + duration + ((duration - 1) // (CLOSE - OPEN)) * (
            DAY - CLOSE + OPEN
        )
    depart = t if tm + duration <= CLOSE else (t // DAY + 1) * DAY + OPEN
    return depart, depart + duration


def idle_days(start, end, work=()):
    """Count complete 08–16 windows with zero work, including equality at 16."""
    return [
        d
        for d in range(start // DAY, end // DAY + 1)
        if start <= d * DAY + OPEN
        and end >= d * DAY + CLOSE
        and all(min(v, d * DAY + CLOSE) <= max(u, d * DAY + OPEN) for u, v in work)
    ]


assert idle_days(OPEN, CLOSE) == [0] and idle_days(OPEN, CLOSE - 1) == []
matrix = original(1, 34)
dist = {(r[0], w): v for r in matrix[1:] for w, v in zip(matrix[0][1:], r[1:])}
cap = {(r[0], f"U{i}"): v for r in original(5, 13)[1:] for i, v in enumerate(r[1:], 1)}
requests = {}
blocks = {}
for i, r in enumerate(original(4, 11, True)[1:], 2):
    b, interval, u, w, flow, item, qty, *_, note = r
    if not re.fullmatch(r"D\d+", str(item)):
        continue
    requests[b] = (u, *window(interval))
    home = next(iter(H[u])) if len(H[u]) == 1 else re.search(r"放置于(W[A-U])", note)[1]
    blocks.setdefault((b, w, "发" if flow.startswith(w) else "收", home), []).append(
        (item, qty)
    )
keys = list(blocks)
original_trucks = Counter()
for row in original(4, 11)[1:]:
    if row[0] is not None:
        current = row[0]
    if isinstance(row[7], int) and re.fullmatch(r"D\d+", str(row[5])):
        original_trucks[current] += row[7]


def save(name, header, data):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header.split(","))
        writer.writerows(data)


def allocation(path):
    assigned, carriers, tab, groups = {}, {}, {}, []
    for r in read(path, 11)[1:]:
        if r[0]:
            b, u = r[:2]
            tab[b] = tuple(r[8:11])
            carriers[b] = u
        if r[2]:
            g = dict(b=b, w=r[2], side=r[3], flag=r[6], owner=r[7] or u, items=[])
            groups.append(g)
        if r[4]:
            g["items"].append((r[4], r[5]))
    expanded = []
    for g in groups:
        remaining = list(g["items"])
        while remaining:
            choices = [
                k
                for k in keys
                if requests[k[0]][0] == g["owner"]
                and remaining[: len(blocks[k])] == blocks[k]
            ]
            assert choices, (g, remaining)
            k = max(choices, key=lambda k: len(blocks[k]))
            expanded.append(dict(g, items=remaining[: len(blocks[k])]))
            remaining = remaining[len(blocks[k]) :]
    groups = expanded
    for g in groups:
        matches = [
            k
            for k in keys
            if requests[k[0]][0] == g["owner"]
            and Counter(blocks[k]) == Counter(g["items"])
        ]
        direct = [k for k in matches if k[1:3] == (g["w"], g["side"])]
        reverse = [
            k
            for k in matches
            if k[2] == "发"
            and k[1] in set.union(*H.values())
            and k[3] == g["w"]
            and g["side"] == "收"
        ]
        if direct or reverse:
            (k,) = direct or reverse
            assert k not in assigned, (k, g)
            assigned[k] = g
            g["reverse"] = not direct
        else:
            (k,) = matches
            assert g["flag"] == 0 and g["side"] == "发"
            g["recovery"] = True
        g["key"] = k
    assert set(assigned) == set(keys)
    origin = {
        b: next(iter(ids))
        for b in carriers
        if len(
            ids := {k[0] for k, g in assigned.items() if g["b"] == b and not g["flag"]}
        )
        == 1
    }
    assert len(origin) == len(set(origin.values())) == len(carriers)
    return groups, assigned, carriers, origin, tab


def routes(path):
    plans, stops = {}, defaultdict(list)
    for i, r in enumerate(read(path, 14)[1:], 2):
        if r[0]:
            b = r[0]
            plans[b] = (r[2], *window(r[1]))
        if r[3]:
            s = dict(w=r[3], row=i, arr=r[4], dep=r[12], ops=[], loads=Counter())
            stops[b].append(s)
        if r[5]:
            op = dict(
                side=r[5],
                owner=r[9] or plans[b][0],
                flag=r[8],
                stay=r[11] == "否",
                printed=r[10],
                items=[],
                size=F(),
                row=i,
            )
            s["ops"].append(op)
        if r[6]:
            size = F(r[7], cap[r[6], plans[b][0]])
            op["items"].append((r[6], r[7]))
            op["size"] += size
            s["loads"][op["side"]] += size
    return plans, stops


def replay(plans, stops, dist):
    events, times, usage = [], {}, defaultdict(dict)
    free = defaultdict(int)
    for b, (u, start, end) in plans.items():
        _, arr = drive(start * DAY + OPEN, dist[u, stops[b][0]["w"]])
        heapq.heappush(events, (arr, b, 0))
    while events:
        arr, b, j = heapq.heappop(events)
        s = stops[b][j]
        w = s["w"]
        u = plans[b][0]
        public = w not in H[u]
        work = 600 * sum(math.ceil(v) for v in s["loads"].values())
        t = max(arr, free[w]) if work else arr
        slots = []
        while work:
            d = t // DAY
            units = usage[w, d]
            if t % DAY >= CLOSE or (public and u not in units and len(units) >= 3):
                t = (d + 1) * DAY + OPEN
                continue
            step = min(work, d * DAY + CLOSE - t)
            slots.append((t, t + step))
            if public:
                units[u] = units.get(u, 0) + step
            work -= step
            t += step
        if slots:
            free[w] = t
        dep = None
        if j + 1 < len(stops[b]):
            dep, following = drive(t, dist[w, stops[b][j + 1]["w"]])
            heapq.heappush(events, (following, b, j + 1))
        times[b, j] = (arr, slots, t, dep)
    return times, usage


def audit(n):
    filename = "问题2_results" if n == 3 else "问题4_附件6格式"
    groups, assigned, units, orig, tab = allocation(RESULTS / (filename + ".xlsx"))
    plans, stops = routes(RESULTS / f"问题{n}_results.xlsx")
    assert set(plans) == set(units) == set(range(1, len(plans) + 1))
    assert [plans[b][1] for b in sorted(plans)] == sorted(v[1] for v in plans.values())
    times, usage = replay(plans, stops, dist)
    if n == 3:
        with (RESULTS / "p2/assign_tie2.csv").open(encoding="utf-8-sig") as f:
            expected = {int(r["block"]): r for r in csv.DictReader(f)}
        assert set(expected) == set(range(len(keys)))
    issues = []

    def check(condition, rule, b, detail):
        if not condition:
            issues.append([rule, b, detail])

    timeline, batch_rows, block_rows, holds, capacity_rows = [], [], [], [], []
    target = {
        b: {k[1] for k, g in assigned.items() if g["b"] == b and not g["flag"]} - H[u]
        for b, u in units.items()
    }
    ownhome = {
        b: {
            k[3]
            for k, g in assigned.items()
            if g["b"] == b and not g["flag"] and k[2] == "发"
        }
        for b in units
    }
    T = {}
    for b, u in units.items():
        sides = Counter()
        for g in groups:
            if g["b"] == b:
                sides[g["side"]] += sum(F(q, cap[d, u]) for d, q in g["items"])
        T[b] = math.ceil(max(sides.values()))
    legops = defaultdict(dict)
    active = defaultdict(list)
    vehicle_km = F()
    total_L, total_D, total_tau, total_delta = F(), 0, 0, 0
    for b, seq in stops.items():
        u, start, end = plans[b]
        source = orig[b]
        _, a, e = requests[source]
        t = T[b]
        N = t + 1 + (1 if t <= 20 else 2) + min(2, math.ceil(t / 10))
        P = 2 * N + 3 + 2 * math.ceil(t / 5)
        check((t, N, P) == tab[b], "车与人", b, (t, N, P, tab[b]))
        check(units[b] == u, "执行单位", b, u)
        back = times[b, len(seq) - 1][0] // DAY
        check(back == end, "实施结束", b, (back, end))
        check(0 <= start <= back < 91, "S1", b, (start, back))
        check(a - 6 <= start <= e, "S2", b, (a, start, e))
        for d in range(start, back + 1):
            active[u, d].append(b)
        mobile = Counter()
        held = []
        distance = 0
        numerator = lifted = F()
        prev = u
        peak = F()
        for j, s in enumerate(seq):
            w = s["w"]
            arr, slots, finish, dep = times[b, j]
            transit = dist[prev, w]
            distance += transit
            numerator += sum(mobile.values()) * transit
            for label, record, v in [("抵达", s["arr"], arr), ("离开", s["dep"], dep)]:
                if record is None and v is None:
                    continue
                err = (stamp(v) - record).total_seconds() / 60
                cell = ("E" if label == "抵达" else "M") + str(s["row"])
                check(abs(err) <= 0.5, "输出分钟", b, (cell, label, err))
            idle = idle_days(arr, dep or arr, slots)
            check(len(idle) <= 1, "S10停站", b, (w, idle))
            timeline.append(
                [
                    b,
                    source,
                    j + 1,
                    s["row"],
                    w,
                    s["arr"],
                    stamp(arr),
                    stamp(slots[0][0]) if slots else "",
                    stamp(finish),
                    s["dep"],
                    stamp(dep) if dep else "",
                    sum(math.ceil(x) for x in s["loads"].values()),
                    " / ".join(
                        stamp(p).strftime("%m/%d %H:%M:%S")
                        + "–"
                        + stamp(q).strftime("%H:%M:%S")
                        for p, q in slots
                    ),
                    ";".join(str(d + 1) for d in idle),
                ]
            )
            rejoin = any(w == site for site, _, _ in held)
            check(
                bool(s["ops"]) or rejoin or (j == len(seq) - 1 and w == u),
                "X1无途经",
                b,
                (j, w),
            )
            check(w != u or j == len(seq) - 1, "X1驻地", b, (j, w))
            if rejoin:
                check(held[-1][0] == w, "S11逆序", b, (j, w))
                site, amounts, parked = held.pop()
                mobile.update(amounts)
                resume = slots[0][0] if slots else (dep if dep is not None else arr)
                idle = idle_days(parked, resume)
                holds.append(
                    [
                        b,
                        site,
                        stamp(parked),
                        stamp(arr),
                        stamp(resume),
                        len(idle),
                        ";".join(str(d + 1) for d in idle),
                    ]
                )
                check(len(idle) <= 1, "S10留置", b, (w, idle))
            parked_load = Counter()
            # At a single stop unloading may precede loading irrespective of display order.
            for op in sorted(s["ops"], key=lambda x: x["side"] == "发"):
                check(abs(float(op["size"]) * (1 if op["side"] == "发" else -1)
                          - op["printed"]) <= 0.00000051, "作业等效车数", b, op["row"])
                remaining_items = list(op["items"])
                while remaining_items:
                    matches = [g for g in groups if g["b"] == b and g["owner"] == op["owner"]
                               and g["flag"] == op["flag"]
                               and remaining_items[:len(g["items"])] == g["items"]]
                    (g,) = matches
                    del remaining_items[:len(g["items"])]
                    k = g["key"]
                    recovery = g.get("recovery", False)
                    movements = legops[b, k, recovery]
                    check(op["side"] not in movements, "重复作业", b, (k, j))
                    movements[op["side"]] = (w, j)
                    size = sum(F(q, cap[item, u]) for item, q in g["items"])
                    if op["side"] == "发":
                        lifted += size
                        if op["stay"]:
                            parked_load[k] += size
                        else:
                            mobile[k] += size
                    else:
                        mobile[k] -= size
                        check(mobile[k] >= 0, "S14先装后卸", b, (k, w))
            if parked_load:
                check(
                    all(op["stay"] for op in s["ops"] if op["side"] == "发"),
                    "X2本站装货标志",
                    b,
                    w,
                )
                parked_load.update(+mobile)
                mobile.clear()
                held.append((w, parked_load, finish))
            travelling = sum(mobile.values())
            peak = max(peak, travelling)
            remaining = t - sum(
                math.ceil(sum(amounts.values())) for _, amounts, _ in held
            )
            check(travelling <= remaining, "S14", b, (w, float(travelling), remaining))
            prev = w
        check(
            seq[-1]["w"] == u and not held and not any(mobile.values()),
            "S11/S12收尾",
            b,
            prev,
        )
        check(len(target[b]) <= 4, "C1", b, len(target[b]))
        check(t <= original_trucks[source] + 3, "C2", b, (t, original_trucks[source]))
        check(t <= 30, "C3", b, t)
        check(distance <= 2000, "C4", b, distance)
        vehicle_km += numerator
        total_L += numerator / lifted
        total_D += distance
        tau = back - start + 1
        total_tau += tau
        total_delta += abs(start - a)
        batch_rows.append(
            [
                b,
                source,
                u,
                stamp(a * DAY).date(),
                stamp(e * DAY).date(),
                stamp(start * DAY).date(),
                stamp(back * DAY).date(),
                start - a,
                t,
                N,
                P,
                distance,
                float(numerator / lifted),
                tau,
                len(target[b]),
                float(peak),
            ]
        )
    for (u, d), bs in active.items():
        check(len(bs) <= 2, "S4", str(bs), (u, d + 1))
    for (w, d), counts in sorted(usage.items()):
        if counts:
            work = sum(counts.values()) / 600
            capacity_rows.append(
                [w, stamp(d * DAY).date(), len(counts), "/".join(sorted(counts)), work]
            )
            check(len(counts) <= 3 and work <= 20, "S8", w, (d, work))
    helped, received = Counter(), Counter()
    violations = set()
    allowed = {b: {u} | H[u] | target[b] for b, u in units.items()}
    rules = Counter()
    soft_order = []
    early_dispatch = defaultdict(list)
    early_return = defaultdict(list)
    jobs = defaultdict(lambda: defaultdict(list))
    recovered = {g["key"]: g for g in groups if g.get("recovery")}
    u6_targets = {k[1] for k in keys if requests[k[0]][0] == "U6"} - H["U6"]
    u9_upper = {
        k
        for k in keys
        if requests[k[0]][0] == "U9"
        and (
            k[1] in u6_targets
            or (
                k[2] == "发"
                and k[1] in set.union(*H.values()) - H["U9"]
                and k[3] in u6_targets
            )
        )
    }
    u9_actual = {
        k
        for k, g in assigned.items()
        if requests[k[0]][0] == "U9" and units[g["b"]] == "U6"
    }
    check(
        u9_upper == u9_actual
        and all(
            units[g["b"]] in {"U9", "U6"}
            for k, g in assigned.items()
            if requests[k[0]][0] == "U9"
        ),
        "C6",
        "全局",
        (u9_upper, u9_actual),
    )
    tightened = []
    for i, k in enumerate(keys):
        orig_b, w0, _, home0 = k
        y, a, e = requests[orig_b]
        g = assigned[k]
        b, w, side = g["b"], g["w"], g["side"]
        x, start, end = plans[b]
        own = not g["flag"]
        h = w0 if g["reverse"] else home0
        size = sum(F(q, cap[d, x]) for d, q in g["items"])
        moves = legops[b, k, False]
        (load, li), (unload, ui) = moves["发"], moves["收"]
        check(li < ui, "装卸时序", b, (i, li, ui))
        check((w == load if side == "发" else w == unload), "目标作业", b, i)
        job = "接领" if side == "发" else "送交"
        jobs[b][job].append(li if side == "发" else ui)
        rec = recovered.get(k)
        other = ""
        if own:
            rule = "自有"
            check(
                (unload if side == "发" else load) == h and orig[b] == orig_b,
                "自有仓",
                b,
                i,
            )
        else:
            check(g["flag"] == (1 if side == "发" else -1), "代领交标记", b, i)
            check(w in target[b] and x != y, "自有目标支持", b, i)
            if not a - 6 <= start <= e:
                violations.add((orig_b, b))
            helped[x] += size
            received[y] += size
            if side == "收":
                rule = "R6" if h in H[x] else "R8" if h in target[b] else "R7"
                check(load == h and (rule != "R7" or dist[x, h] <= 150), rule, b, i)
                if rule == "R7":
                    allowed[b].add(h)
            elif h in H[x]:
                rule = "R1"
                check(unload == h, rule, b, i)
            elif h in target[b]:
                rule = "R2"
                check(unload == h, rule, b, i)
            elif rec:
                rule = "R4"
                rb = rec["b"]
                rload, rli = legops[rb, k, True]["发"]
                runload, rui = legops[rb, k, True]["收"]
                other = f"领回批{rb}，暂存批回驻地{stamp(end * DAY).date()}，领回批出发{stamp(plans[rb][1] * DAY).date()}"
                check(
                    unload in ownhome[b]
                    and unload in target[rb]
                    and plans[rb][0] == y
                    and rload == unload
                    and runload == h
                    and rli < rui
                    and plans[rb][1] > times[b, len(stops[b]) - 1][0] // DAY,
                    rule,
                    b,
                    i,
                )
                early_return[rb].append(rui)
                jobs[rb]["接领"].append(rli)
            elif unload == h:
                rule = "R5"
                support = [
                    (otherk, og)
                    for otherk, og in assigned.items()
                    if og["b"] == b
                    and og["flag"] == -1
                    and og["owner"] == y
                    and legops[b, otherk, False]["发"][0] == h
                ]
                other = "配对代交块 " + ",".join(
                    str(keys.index(ok)) for ok, og in support
                )
                check(
                    dist[x, h] <= 150
                    and any(legops[b, ok, False]["发"][1] < li for ok, og in support),
                    rule,
                    b,
                    i,
                )
                allowed[b].add(h)
            else:
                rule = "R3"
                check(unload in ownhome[b] and dist[y, unload] <= 150, rule, b, i)
            rules[rule] += 1
        if side == "收" and load in H[x] and unload not in H[x]:
            early_dispatch[b].append(li)
            if not own:
                tightened.append((i, b, rule, load, unload))

        if side == "发" and unload in H[x]:
            early_return[b].append(ui)
        if n == 3:
            p = expected[i]
            assert (orig_b, y, w0, home0, orig[b], x, rule) == (
                int(p["batch"]), p["owner"], p["w"], p["h"], int(p["to_batch"]),
                p["to_unit"], p["case"] or "自有"
            )
            if rule == "R4":
                assert (unload, orig[rec["b"]]) == ast.literal_eval(p["aux"])
            if rule == "R3":
                assert unload == p["aux"]
        condition = {
            "R3": f"{y}到{unload}={dist[y, unload]}km",
            "R5": f"{x}到{h}={dist[x, h]}km",
            "R7": f"{x}到{h}={dist[x, h]}km",
        }.get(rule, "")
        block_rows.append(
            [
                i,
                orig_b,
                y,
                b,
                orig[b],
                x,
                w,
                h,
                side,
                rule,
                load,
                li + 1,
                unload,
                ui + 1,
                "/".join(sorted(target[b])),
                "/".join(sorted(ownhome[b])),
                condition,
                other,
                float(size),

            ]
        )
    for b, seq in stops.items():
        u = units[b]
        external = [j for j, s in enumerate(seq) if s["ops"] and s["w"] not in H[u]]
        check(
            all(j < min(external, default=len(seq)) for j in early_dispatch[b]),
            "S12出程",
            b,
            early_dispatch[b],
        )
        check(
            all(j > max(external, default=-1) for j in early_return[b]),
            "S12返程",
            b,
            early_return[b],
        )
        for w, count in Counter(s["w"] for s in seq if s["w"].startswith("W")).items():
            check(count <= 2, "仓库访问次数", b, (w, count))
        for s in seq:
            check(s["w"] in allowed[b], "S15", b, s["w"])
        if (
            jobs[b]["接领"]
            and jobs[b]["送交"]
            and min(jobs[b]["接领"]) < max(jobs[b]["送交"])
        ):
            soft_order.append(b)
    A = sum(helped.values())
    E = sum(abs(helped[u] - received[u]) for u in H) / (2 * A) if A else 0
    save(
        f"Q{n}_stations.csv",
        "批号,原批,站序,表行,节点,表到达,精确到达,开始服务,服务完成,表离开,精确离开,作业车数,实际作业时段,完整等待日日序",
        timeline,
    )
    save(
        f"Q{n}_batches.csv",
        "批号,原批,单位,提报开始,提报结束,出发,回驻地,有符号偏离,T,N,P,里程,载货均距,天数,目标数,移动车队载重峰值",
        batch_rows,
    )
    save(
        f"Q{n}_blocks.csv",
        "块,原批,货主,执行批,执行原批,执行单位,目标仓,存放仓,仓库方向,规则,装车站,装车站序,卸货站,卸货站序,自有目标,自有卸点,距离条件,依赖,等效车数",
        block_rows,
    )
    save(f"Q{n}_warehouse.csv", "仓库,日期,单位数,单位,当日作业车当量", capacity_rows)
    save(
        f"Q{n}_holds.csv",
        "批,仓,本站装完,汇合到达,汇合开工或离开,完整等待日数,日序",
        holds,
    )
    save(f"Q{n}_findings.csv", "规则,批,明细", issues)
    print(
        n,
        len(plans),
        sum(r[9] for r in batch_rows),
        sum(r[10] for r in batch_rows),
        float(A),
        total_tau,
        total_delta,
        total_D,
        float(total_L),
        float(E),
        sum(map(len, target.values())),
    )
    print(
        "回放统计",
        len(timeline),
        sum((r[5] is not None) + (r[9] is not None) for r in timeline),
        max(
            abs((r[i] - r[i + 1]).total_seconds())
            for r in timeline
            for i in (5, 9)
            if r[i] is not None
        )
        / 60,
        sum(" / " in r[12] for r in timeline),
    )
    print("S12 W1 新增覆盖", tightened, "C6", len(u9_actual))
    print(
        "S3",
        sorted(violations),
        "S13",
        soft_order,
        "rules",
        rules,
        "issues",
        issues,
        "holds",
        holds,
    )
    if issues:
        raise ValueError(issues)
    return {
        "调运总批次": len(plans), "调运总车数": sum(r[9] for r in batch_rows),
        "出动总人数": sum(r[10] for r in batch_rows), "代领代交等效车数": A,
        "人员调动执行总时间": total_tau, "开始偏离": total_delta, "调运总里程": total_D,
        "载货车辆总行驶距离": total_L, "失衡度": E, "批次仓库对": sum(map(len, target.values())),
        "车公里": vehicle_km, "V": len(violations)
    }


if __name__ == "__main__":
    for n in (3, 4):
        audit(n)
