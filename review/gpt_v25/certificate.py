"""Independent isolated route search and necessary departure conditions."""

from collections import defaultdict
from fractions import Fraction
from itertools import product
from math import lcm
from pathlib import Path
import csv
import io
import subprocess
import tempfile

import check


def instance():
    groups, assigned, units, origins, _ = check.allocation(
        check.RESULTS / "问题2_results.xlsx"
    )
    _, stops = check.routes(check.RESULTS / "问题3_results.xlsx")
    with (check.OUT / "Q3_blocks.csv").open(encoding="utf-8-sig") as file:
        rules = {
            check.keys[int(row["块"])]: row["规则"] for row in csv.DictReader(file)
        }
    legs = defaultdict(list)
    edges = []
    for group in groups:
        b = group["b"]
        k = group["key"]
        rule = rules[k] if not group.get("recovery") else "领回"
        positions = {}
        for stop in stops[b]:
            for op in stop["ops"]:
                if (op["owner"], op["flag"], op["items"]) == (
                    group["owner"],
                    group["flag"],
                    group["items"],
                ):
                    assert op["side"] not in positions
                    positions[op["side"]] = (stop["w"], op["size"])
        src, size = positions["发"]
        dst, _ = positions["收"]
        if rule == "领回":
            edges.append((origins[assigned[k]["b"]], origins[b]))
        legs[b].append((src, dst, size, group["side"], group["owner"], rule))
    cases = {}
    for b, jobs in legs.items():
        u = units[b]
        nodes = [u, *sorted(check.H[u] | {node for job in jobs for node in job[:2]})]
        T = max(
            sum(job[2] for job in jobs if job[3] == side).__ceil__()
            for side in ("收", "发")
        )
        scale = lcm(*(job[2].denominator for job in jobs))
        assert scale * T * 2000 < 2**126
        data = []
        for src, dst, size, side, owner, rule in jobs:
            support = 0
            if rule == "R5":
                support = sum(
                    1 << j
                    for j, other in enumerate(jobs)
                    if other[3] == "收" and other[0] == dst and other[4] == owner
                )
                assert support
            data.append(
                (
                    nodes.index(src),
                    nodes.index(dst),
                    int(size * scale),
                    int(side == "收" and src in check.H[u] and dst not in check.H[u]),
                    int(side == "发" and dst in check.H[u]),
                    support,
                )
            )
        cases[origins[b]] = (nodes, T, scale, data)
    return cases, sorted(edges)


def route_input(cases):
    file = io.StringIO()
    print(len(cases), file=file)
    for b, (nodes, T, scale, legs) in sorted(cases.items()):
        print(b, len(nodes), len(legs), T, scale, file=file)
        print(*(int(node in check.H[nodes[0]]) for node in nodes), file=file)
        for src in nodes:
            print(*(check.dist[src, dst] for dst in nodes), file=file)
        for leg in legs:
            print(*leg, file=file)
    return file.getvalue()


def validate_isolated(case, days, length, km, trace):
    """Check every retained route again using Python FCFS and exact fractions."""
    nodes, trucks, scale, jobs = case
    unit = nodes[0]
    stops = []
    onboard, holds, loaded, unloaded = set(), [], set(), set()
    visits = defaultdict(int)
    prev = unit
    distance, ton_km = 0, 0
    hold_pairs = []
    reserved = 0

    def indices(mask):
        return {i for i in range(len(jobs)) if mask & (1 << i)}

    for pos, step in enumerate(trace.split()):
        v, in_mask, out_mask, park_mask = map(int, step.split(":"))
        load, unload, park = map(indices, (in_mask, out_mask, park_mask))
        w = nodes[v]
        hop = check.dist[prev, w]
        distance += hop
        ton_km += sum(jobs[i][2] for i in onboard) * hop
        assert w != prev
        prev = w
        if v:
            visits[v] += 1
            assert visits[v] <= 2
        rejoin = any(v == hold[0] for hold in holds)
        assert load or unload or rejoin or (v == 0 and pos == len(trace.split()) - 1)
        if rejoin:
            node, prior, groups, cars = holds.pop()
            assert v == node
            hold_pairs.append((prior, pos))
            reserved -= cars
            onboard |= groups
        assert unload <= onboard and not load & loaded
        if (load or unload) and w not in check.H[unit]:
            assert all(i in loaded for i, j in enumerate(jobs) if j[3])
            assert all(not j[4] for i, j in enumerate(jobs) if i in unloaded)
        for i in load:
            src, _, _, _, _, support = jobs[i]
            assert src == v and (support == 0 or indices(support) & loaded)
        for i in unload:
            _, dst, _, _, last, _ = jobs[i]
            assert dst == v
            if last:
                assert all(
                    (i in loaded or nodes[j[0]] in check.H[unit])
                    and (i in unloaded or nodes[j[1]] in check.H[unit])
                    for i, j in enumerate(jobs)
                )
        onboard = (onboard - unload) | load
        assert park <= onboard
        if park:
            assert v and load and park == onboard
            cars = Fraction(sum(jobs[i][2] for i in park), scale).__ceil__()
            holds.append((v, pos, park, cars))
            reserved += cars
            onboard -= park
        assert sum(jobs[i][2] for i in onboard) <= (trucks - reserved) * scale
        loaded |= load
        unloaded |= unload
        stops.append(
            {
                "w": w,
                "loads": {
                    side: Fraction(sum(jobs[i][2] for i in selected), scale)
                    for side, selected in [("发", load), ("收", unload)]
                },
            }
        )
    assert not onboard and not holds and len(unloaded) == len(jobs) and prev == unit
    assert (
        distance == km <= 2000 and Fraction(ton_km, sum(j[2] for j in jobs)) == length
    )
    times, _ = check.replay({1: (unit, 0, days - 1)}, {1: stops}, check.dist)
    assert times[1, len(stops) - 1][0] // check.DAY + 1 == days
    for first, second in hold_pairs:
        arr, slots, _, dep = times[1, second]
        resume = slots[0][0] if slots else dep
        assert len(check.idle_days(times[1, first][2], resume)) <= 1


def date_vectors(min_days, edges, cap):
    """Enumerate only vectors within cap; fixed minimum durations suffice."""
    info = {b: check.requests[b] for b in min_days}
    related = {b for edge in edges for b in edge}
    dependent = sorted(related)
    independent = sorted(info.keys() - related)

    def options(b, budget):
        _, a, e = info[b]
        return range(
            max(0, a - 6, a - budget), min(e, 91 - min_days[b], a + budget) + 1
        )

    def fits(starts):
        for a, b in edges:
            if a in starts and b in starts and starts[a] + min_days[a] > starts[b]:
                return False
        by_unit = defaultdict(list)
        for b, s in starts.items():
            by_unit[info[b][0]].append((s, s + min_days[b]))
        for ints in by_unit.values():
            for s, _ in ints:
                if sum(lo <= s < hi for lo, hi in ints) > 2:
                    return False
        return True

    def extend(j, starts, budget):
        if j == len(independent):
            yield cap - budget, dict(starts)
            return
        b = independent[j]
        a = info[b][1]
        for s in options(b, budget):
            starts[b] = s
            if fits(starts):
                yield from extend(j + 1, starts, budget - abs(s - a))
        starts.pop(b, None)

    for days in product(*(options(b, cap) for b in dependent)):
        starts = dict(zip(dependent, days))
        cost = sum(abs(s - info[b][1]) for b, s in starts.items())
        if cost <= cap and fits(starts):
            yield from extend(0, starts, cap - cost)
