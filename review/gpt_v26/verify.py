"""Construct independent mileage witnesses, then compare against the pinned CSVs."""

import ast
import csv
import io
import json
import math
import subprocess
from collections import Counter, defaultdict
from fractions import Fraction as F

from inputs import OUT, ROOT, H, blocks, keys, requests, dist, cap, original_trucks

BASE = "588815c9b41fa9e34ae9c5c75daff4a401911e5f"


def ref(path):
    data = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def save(name, rows):
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def weight(i, b):
    return sum(F(q, cap[item, requests[b][0]]) for item, q in blocks[keys[i]])


def witness(u, jobs, trucks):
    # Each stop unloads ready consignments, then loads all eligible ones.
    # Only a witness is needed; every branch actually returned is feasible.
    def search(path, km, waiting, aboard, events, final_phase):
        current = path[-1]
        if not waiting and not aboard:
            length = km + dist[current, u]
            if length <= 2000:
                return path + [u], length, events
            return
        nodes = {jobs[i][0] for i in waiting} | {jobs[i][1] for i in aboard}
        for w in sorted(nodes, key=lambda w: (dist[current, w], w)):
            if w == current or path.count(w) >= 2 or (final_phase and w not in H[u]):
                continue
            if w not in H[u] and any(
                jobs[i][0] in H[u] and not jobs[i][3] for i in waiting
            ):
                continue
            length = km + dist[current, w]
            if length > 2000:
                continue
            drop = {i for i in aboard if jobs[i][1] == w}
            load = {i for i in waiting if jobs[i][0] == w}
            if any(jobs[i][4] == "R5" and jobs[i][1] not in path for i in load):
                continue
            remaining = waiting - load
            moving = (aboard - drop) | load
            mass = sum(jobs[i][2] for i in moving)
            if mass > trucks:
                continue
            finish = final_phase or (w in H[u] and any(jobs[i][3] for i in drop))
            event = dict(w=w, drop=sorted(drop), load=sorted(load), onboard=str(mass))
            found = search(
                path + [w], length, remaining, moving, events + [event], finish
            )
            if found:
                return found

    result = search([u], 0, set(jobs), set(), [], False)
    assert result, (u, trucks, jobs)
    return result


def audit(sol):
    groups = defaultdict(dict)
    balance = Counter()
    targets = defaultdict(set)
    total = F(0)
    for k in sol:
        i, b = k["i"], k["batch"]
        orig, w, d, h = keys[i]
        y, x = requests[orig][0], requests[b][0]
        pickup = d == "发" and not k["reverse"]
        q = weight(i, b)
        groups[b][i] = (k["start"], k["end"], q, pickup, k["rule"])
        if k["back"]:
            back = k["back"]
            groups[back][i] = (k["end"], h, weight(i, back), True, "back")
        dest = h if k["reverse"] else w
        if dest not in H[x]:
            targets[b].add(dest)
        if x != y:
            total += q
            balance[x] += q
            balance[y] -= q
    routes = []
    for b, jobs in sorted(groups.items()):
        sides = Counter()
        for _, _, q, pickup, _ in jobs.values():
            sides[pickup] += q
        t = math.ceil(max(sides.values()))
        assert t <= min(30, original_trucks[b] + 3) and len(targets[b]) <= 4
        n = t + 2 + (t >= 21) + min(2, math.ceil(t / 10))
        path, km, events = witness(requests[b][0], jobs, t)
        routes.append(
            dict(
                batch=b,
                T=t,
                N=n,
                P=2 * n + 3 + 2 * math.ceil(t / 5),
                warehouses=" ".join(sorted(targets[b])),
                km=km,
                path=" ".join(path),
                events=json.dumps(events, separators=(",", ":")),
            )
        )
    summary = {key: sum(r[key] for r in routes) for key in ["T", "N", "P"]}
    summary.update(
        A=total,
        E=sum(map(abs, balance.values())) / (2 * total),
        pairs=sum(map(len, targets.values())),
        batches=len(routes),
        max_km=max(r["km"] for r in routes),
    )
    return routes, summary


solutions = json.loads((OUT / "solutions.json").read_text())
results = [audit(s) for s in solutions]
refs = "results/F/p2/"
rows = ref(refs + "ties.csv")
assert len(solutions) == len(rows)
old = ref("review/GPT问题2独立复算/block_audit.csv")


def compare(sol, rows):
    by_id = {int(r["block"]): r for r in rows}
    assert len(rows) == len(by_id) == len(sol) == 90
    differences = []
    for k in sol:
        i, b = k["i"], k["batch"]
        orig, w, d, h = keys[i]
        r = by_id[i]
        rule = k["rule"]
        aux = (
            str((k["end"], k["back"]))
            if rule == "R4"
            else k["end"] if rule == "R3" else ""
        )
        expected = (
            orig,
            requests[orig][0],
            w,
            "领" if d == "发" else "交",
            h,
            b,
            requests[b][0],
            "" if rule == "own" else rule,
            aux,
        )
        actual = (
            int(r["batch"]),
            r["owner"],
            r["w"],
            r["dir"],
            r["h"],
            int(r["to_batch"]),
            r["to_unit"],
            r["case"],
            r["aux"],
        )
        metadata_ok = (
            r["inner"] == str(w in set.union(*H.values()))
            and r["option"] == ("own" if rule == "own" else "T")
            and math.isclose(weight(i, orig), float(r["s_owner"]), rel_tol=1e-12)
        )
        if (
            expected != actual
            or not metadata_ok
            or not math.isclose(weight(i, b), float(r["s_exec"]), rel_tol=1e-12)
        ):
            differences.append(i)
    return differences


summaries, route_rows, comparisons = [], [], []
for row in rows:
    j = int(row["tie"])
    reference = ref(refs + f"assign_tie{j}.csv")
    matches = [k for k, s in enumerate(solutions) if not compare(s, reference)]
    assert len(matches) == 1
    assert (row["chosen"] == "True") == (j == 2)
    assert row["diff_blocks"] == ("" if j == 0 else "43")
    (k,) = matches
    routes, summary = results[k]
    for field in ("T", "N", "P", "pairs", "A", "E"):
        assert math.isclose(summary[field], float(row[field]), rel_tol=1e-12)
    summaries.append(dict(tie=j, enumerated=k + 1, **summary))
    route_rows.extend(dict(tie=j, **r) for r in routes)
    for s in solutions[k]:
        comparisons.append(
            dict(
                tie=j,
                block=s["i"],
                batch=s["batch"],
                rule=s["rule"],
                start=s["start"],
                end=s["end"],
                back=s["back"],
                match=True,
            )
        )
    diff_main = compare(solutions[k], ref(refs + "assign_main.csv"))
    diff_old = [
        s["i"]
        for s in solutions[k]
        if int(old[s["i"]]["to"]) != s["batch"]
        or (old[s["i"]]["back"] or "0") != str(s["back"])
        or old[s["i"]]["leg"] != s["start"] + "→" + s["end"]
        or old[s["i"]]["rule"] != ("自有" if s["rule"] == "own" else s["rule"])
    ]
    assert diff_old == ([] if j == 0 else [43])
    assert diff_main == ([] if j == 2 else [43])
    print(j, summary, "old", diff_old, "main", diff_main)
save("metrics.csv", summaries)
save("routes.csv", route_rows)
save("block_comparison.csv", comparisons)
