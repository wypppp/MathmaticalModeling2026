"""Reproduce from repo root: run check.py, compile routes.cpp, run optimal.py."""

import csv
from collections import Counter, defaultdict
from fractions import Fraction as F
from functools import lru_cache
from itertools import product
from math import prod, ceil
from pathlib import Path
import os, subprocess
import certificate as c
import check

cases, edges = c.instance()
batches = sorted(cases)
data = subprocess.check_output(
    [
        os.environ.get(
            "F_ROUTES", str(check.OUT / ("routes.exe" if os.name == "nt" else "routes"))
        )
    ],
    input=c.route_input(cases),
    text=True,
)
routes = defaultdict(list)
details = {}


def blockmask(mask, jobs):
    return sum(x[2] for i, x in enumerate(jobs) if mask >> i & 1)


for line in data.splitlines():
    b, d, num, den, km, *trace = line.split()
    b, d, km = map(int, (b, d, km))
    key = b, len(routes[b])
    nodes, T, scale, jobs = cases[b]
    grouped = True
    stops = []
    stack = []
    pairs = []
    masks = []
    for j, step in enumerate(trace):
        n, im, om, hm = map(int, step.split(":"))
        masks.append((im, om, hm))
        for mask in (im, om):
            selected = {x[:2] for i, x in enumerate(jobs) if mask >> i & 1}
            grouped &= all(
                bool(mask >> i & 1) == (x[:2] in selected) for i, x in enumerate(jobs)
            )
        if stack and stack[-1][0] == n:
            pairs.append((stack.pop()[1], j))
        if hm:
            stack.append((n, j))
        stops.append(
            dict(
                w=nodes[n],
                loads={
                    side: F(blockmask(mask, jobs), scale)
                    for side, mask in [("发", im), ("收", om)]
                },
            )
        )
    assert not stack
    details[key] = dict(
        d=d,
        L=F(int(num), int(den)),
        km=km,
        stops=stops,
        pairs=pairs,
        g=grouped,
        trace=trace,
        masks=masks,
    )
    routes[b].append(key)

ties = set()


def timed(choices, starts):
    ordered = sorted(choices, key=lambda k: (starts[k[0]], k[0]))
    plans = {i: (cases[b][0][0], starts[b], 0) for i, (b, k) in enumerate(ordered)}
    stops = {i: details[key]["stops"] for i, key in enumerate(ordered)}
    times, usage = check.replay(plans, stops, check.dist)
    arrivals = {}
    for (i, j), (arr, slots, _, _) in times.items():
        if not slots:
            continue
        token = (stops[i][j]["w"], arr)
        if token in arrivals:
            ties.add((arrivals[token], ordered[i][0], token[0]))
        arrivals[token] = ordered[i][0]
    active = Counter()
    durations = {}
    for i, key in enumerate(ordered):
        b = key[0]
        u, start, _ = plans[i]
        end = times[i, len(stops[i]) - 1][0] // check.DAY
        if end >= 91 or any(
            b == a and end >= starts[j] for a, j in edges if j in starts
        ):
            return
        for day in range(start, end + 1):
            active[u, day] += 1
            if active[u, day] > 2:
                return
        for j in range(len(stops[i])):
            arr, slots, finish, dep = times[i, j]
            if len(check.idle_days(arr, dep or arr, slots)) > 1:
                return
        for first, last in details[key]["pairs"]:
            arr, slots, finish, dep = times[i, last]
            if (
                len(check.idle_days(times[i, first][2], slots[0][0] if slots else dep))
                > 1
            ):
                return
        durations[b] = end - start + 1
    return durations


def read_rows(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


bs = read_rows(check.OUT / "Q3_batches.csv")
_, ss = check.routes(check.RESULTS / "问题3_results.xlsx")


def worksheet_route(b, row):
    printed = int(row["批号"])

    actual = ss[printed]
    matches = [
        k
        for k in routes[b]
        if [(s["w"], +Counter(s["loads"])) for s in details[k]["stops"]]
        == [(s["w"], +Counter(s["loads"])) for s in actual]
        and abs(float(details[k]["L"]) - float(row["载货均距"])) < 1e-8
    ]
    values = {details[k]["L"] for k in matches}
    assert len(values) == 1
    return next(iter(values))


mainL = sum(worksheet_route(int(row["原批"]), row) for row in bs)
min_days = {b: min(details[k]["d"] for k in keys) for b, keys in routes.items()}
vec = sorted(
    c.date_vectors(min_days, edges, 6),
    key=lambda pair: (pair[0], tuple(pair[1][b] for b in batches)),
)
check.save(
    "Q3_departures.csv",
    "偏离," + ",".join(map(str, batches)),
    ([d, *(v[b] + 1 for b in batches)] for d, v in vec),
)
isolated_ok = {k: bool(timed([k], {b: 0})) for b, keys in routes.items() for k in keys}


def lbound(grouped, isolated):
    return sum(
        min(
            details[k]["L"]
            for k in keys
            if (not grouped or details[k]["g"]) and (not isolated or isolated_ok[k])
        )
        for keys in routes.values()
    )


group_lb = lbound(True, True)


# Baseline routes are matched to the independent grouped enumeration by their
# station sequence, loading, unloading, and hold flags; use exact model weights.
def baseline():
    rows = read_rows(check.RESULTS / "p3/steps_baseline.csv")
    starts = {
        int(r["batch"]): int(r["start"]) - 1
        for r in read_rows(check.RESULTS / "p3/batches_baseline.csv")
    }
    chosen = []
    shortest_options = []
    for b in batches:
        seq = [r for r in rows if int(r["batch"]) == b]

        def signature(k):
            return [
                (s["w"], ceil(s["loads"]["发"]), ceil(s["loads"]["收"]), bool(h))
                for s, (_, _, h) in zip(details[k]["stops"], details[k]["masks"])
            ]

        sig = [
            (r["node"], int(r["c_load"]), int(r["c_unload"]), bool(r["leave"]))
            for r in seq
        ]
        candidates = [k for k in routes[b] if details[k]["g"] and isolated_ok[k]]
        matches = [k for k in candidates if signature(k) == sig]
        assert matches and len({details[k]["L"] for k in matches}) == 1, (b, sig)
        k = matches[0]
        short = min(details[x]["km"] for x in candidates)
        if short != details[k]["km"]:
            print("基线路线非最短", b, details[k]["km"], short)
        chosen.append(k)
        shortest_options.append(
            [k]
            if details[k]["km"] == short
            else [q for q in candidates if details[q]["km"] == short]
        )
    for alternative in product(*shortest_options):
        durations = timed(alternative, starts)
        if durations:
            check.save(
                "Q3_shortest_baseline_example.csv",
                "原批,出发日序,实际天数,均距精确值,里程,节点装卸留置掩码",
                (
                    [
                        k[0],
                        starts[k[0]] + 1,
                        durations[k[0]],
                        str(details[k]["L"]),
                        details[k]["km"],
                        " ".join(details[k]["trace"]),
                    ]
                    for k in alternative
                ),
            )
            break
    else:
        raise ValueError(
            "No feasible all-shortest witness at the published baseline dates"
        )
    ds = timed(chosen, starts)
    assert ds
    return (
        sum(ds.values()),
        sum(details[k]["L"] for k in chosen),
        sum(abs(s - check.requests[b][1]) for b, s in starts.items()),
    )


ud, ul, delta = baseline()
weight = (ul - group_lb) / (ud - sum(min_days.values()))
main = 129 * weight + mainL
isol_cost = {k: r["L"] + weight * r["d"] for k, r in details.items()}
lb0 = sum(min(isol_cost[k] for k in keys) for keys in routes.values())


def score(value, delta):
    return (value - 126 * weight - group_lb) / (ul - group_lb) + F(delta, 5)


print(
    "BASE",
    ud,
    float(ul),
    delta,
    "LB",
    sum(min_days.values()),
    float(group_lb),
    float(lbound(False, True)),
    float(lbound(True, False)),
    float(lbound(False, False)),
    "scores",
    float(score(main, 5)),
    float(score(lb0, 7)),
    flush=True,
)
blocks = read_rows(check.OUT / "Q3_blocks.csv")
pairs = {(int(r["原批"]), int(r["执行原批"])) for r in blocks if r["规则"] != "自有"}


def V(v):
    return sum(
        not check.requests[i][1] - 6 <= v[b] <= check.requests[i][2] for i, b in pairs
    )


def service(t, n):
    if not n:
        return t
    if t % check.DAY == check.CLOSE:
        t = (t // check.DAY + 1) * check.DAY + check.OPEN
    return t + n + (t % check.DAY - check.OPEN + n - 1) // 12000 * 24000


@lru_cache(None)
def windows(key, days):
    """Include every service day up to this route's budget-implied deadline."""
    return {
        (s["w"], day)
        for s in details[key]["stops"]
        if any(s["loads"].values())
        for day in range(days)
    }


def unique_keys(keys):
    keep = {}
    for key in keys:
        r = details[key]
        sig = (
            tuple((s["w"], sum(map(ceil, s["loads"].values()))) for s in r["stops"]),
            tuple(r["pairs"]),
        )
        if sig not in keep or (r["L"], r["km"]) < (
            details[keep[sig]]["L"],
            details[keep[sig]]["km"],
        ):
            keep[sig] = key
    return list(keep.values())


component_cache = {}


def solve_component(group, pool, starts, slack, costs):
    order = sorted(group, key=lambda b: len(pool[b]), reverse=True)
    signature = (
        tuple(
            (
                b,
                starts[b],
                tuple(pool[b]),
                min((starts[j] for i, j in edges if i == b), default=91),
            )
            for b in order
        ),
        slack,
    )
    if signature in component_cache:
        return component_cache[signature]
    best = None
    chosen = []
    count = 0
    floor = sum(costs[b] for b in order)

    def visit(i, excess):
        nonlocal best, count
        cap = best[0] - floor if best else slack
        if excess > cap:
            return
        if i == len(order):
            count += 1
            days = timed(chosen, starts)
            if not days:
                return
            result = (
                floor
                + excess
                + weight * (sum(days.values()) - sum(details[k]["d"] for k in chosen))
            )
            if result > floor + cap:
                return
            km = sum(details[k]["km"] for k in chosen)
            candidate = (result, km, tuple(chosen))
            if best is None or candidate < best:
                best = candidate
            return
        b = order[i]
        for k in pool[b]:
            diff = isol_cost[k] - costs[b]
            if diff + excess > cap:
                break
            chosen.append(k)
            visit(i + 1, excess + diff)
            chosen.pop()

    visit(0, F(0))
    component_cache[signature] = (best, count)
    return best, count


def solve_vector(keys, starts, delta):
    cap = main - (delta - 5) * (ul - group_lb) / 5
    pool = {
        b: [
            k
            for k in keys[b]
            if all(i != b or starts[b] + details[k]["d"] <= starts[j] for i, j in edges)
        ]
        for b in batches
    }
    if not all(pool.values()):
        return None
    costs = {b: min(map(isol_cost.get, p)) for b, p in pool.items()}
    solved = F(0)
    picked = []
    replays = 0
    while pool:
        slack = cap - solved - sum(costs[b] for b in pool)
        if slack < 0:
            return None
        overlap = {}
        for b, p in pool.items():
            pool[b] = sorted(
                (k for k in p if isol_cost[k] - costs[b] <= slack),
                key=lambda k: (isol_cost[k], details[k]["km"]),
            )
            possible = set()
            for k in pool[b]:
                days = details[k]["d"] + int(
                    (slack - (isol_cost[k] - costs[b])) // weight
                )
                possible.update((s, d + starts[b]) for s, d in windows(k, days))
            overlap[b] = possible
        groups = []
        for b in pool:
            merged = {b}
            for group in list(groups):
                if any(overlap[b] & overlap[j] for j in group):
                    merged.update(group)
                    groups.remove(group)
            groups.append(merged)
        group = min(groups, key=lambda g: prod(len(pool[b]) for b in g))
        best, count = solve_component(group, pool, starts, slack, costs)
        replays += count
        if not best:
            return None
        value, km, choices = best
        solved += value
        picked.extend(choices)
        for b in group:
            del pool[b]
    ds = timed(picked, starts)
    assert ds and solved == sum(details[k]["L"] for k in picked) + weight * sum(
        ds.values()
    )
    return solved, V(starts), sum(details[k]["km"] for k in picked), picked, ds, replays


if __name__ == "__main__":
    check.save(
        "Q3_route_jobs.csv",
        "原批,位序,装车站,卸货站,等效车数,R5支持位掩码",
        (
            [b, i, nodes[src], nodes[dst], str(F(size, scale)), support]
            for b, (nodes, _, scale, jobs) in sorted(cases.items())
            for i, (src, dst, size, _, _, support) in enumerate(jobs)
        ),
    )
    for file, goal in [
        ("Q3_distance_minimum.csv", "distance"),
        ("Q3_time_minimum.csv", "time"),
    ]:
        starts = {}
        chosen = []
        for row in read_rows(check.OUT / file):
            b = int(row["原批"])
            starts[b] = int(row["出发日序"]) - 1
            assert check.requests[b][1] - 6 <= starts[b] <= check.requests[b][2]
            (key,) = [
                k
                for k in routes[b]
                if details[k]["trace"] == row["节点装卸留置掩码"].split()
            ]
            assert details[key]["g"]
            chosen.append(key)
        assert set(starts) == set(batches)
        ds = timed(chosen, starts)
        assert ds
        value = (
            sum(details[k]["L"] for k in chosen)
            if goal == "distance"
            else sum(ds.values())
        )
        assert value == (group_lb if goal == "distance" else sum(min_days.values()))
    for k, valid in isolated_ok.items():
        if valid:
            r = details[k]
            c.validate_isolated(
                cases[k[0]], r["d"], r["L"], r["km"], " ".join(r["trace"])
            )
    print("vectors", Counter(d for d, v in vec), flush=True)
    # The block space contains every grouped route. A lower bound in this
    # space also applies to the grouped model, with the same J1 reference.
    keys = {b: unique_keys(p) for b, p in routes.items()}
    out = []
    witness = []
    ties.clear()
    for i, (delta, v) in enumerate(vec, 1):
        result = solve_vector(keys, v, delta)
        if result:
            value, viol, km, chosen, days, count = result
            z = score(value, delta)
            print(i, delta, float(z), viol, km, count, flush=True)
            out.append([i, delta, "达到主分或更优", str(z), float(z), viol, km])
            for k in sorted(chosen):
                b = k[0]
                r = details[k]
                witness.append(
                    [
                        i,
                        b,
                        v[b] + 1,
                        days[b],
                        str(r["L"]),
                        r["km"],
                        r["g"],
                        " ".join(r["trace"]),
                    ]
                )
        else:
            out.append([i, delta, "排除", "", "", "", ""])
        if i % 20 == 0:
            print("vectors done", i, flush=True)
    print("FCFS exact ties during competitive component replay", sorted(ties))
    check.save("Q3_optimality.csv", "向量,偏离,判定,z精确,z,V,总里程", out)
    check.save(
        "Q3_optimal_witness.csv",
        "向量,原批,出发日序,实际天数,均距精确值,里程,同端点同处理,节点装卸留置掩码",
        witness,
    )
