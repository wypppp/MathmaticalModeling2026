"""Outer approximation of prior FCFS completions for low-distance routes."""

from collections import defaultdict
from bisect import bisect_left
import optimal as o
import check


def possible(target, grouped, limit, cutoff):
    # Integer unit = 24 replay ticks. A day spans 1500 units, shifts run 500..1000.
    opts = {
        b: o.unique_keys([k for k in ks if not grouped or o.details[k]["g"]])
        for b, ks in o.routes.items()
    }
    floor = {b: min(o.details[k]["L"] for k in ks) for b, ks in opts.items()}
    spare = limit - sum(floor.values())
    arrivals = defaultdict(list)
    finishes = defaultdict(dict)
    queued = defaultdict(set)
    state = {}
    log = defaultdict(list)
    visitors = defaultdict(set)

    def arrive(task, t):
        if t <= cutoff and t not in arrseen[task]:
            arrseen[task].add(t)
            arrivals[t].append(task)

    arrseen = defaultdict(set)
    arrived = defaultdict(list)
    for b, ks in opts.items():
        if b == target:
            continue
        u, a, e = check.requests[b]
        for k in ks:
            if o.details[k]["L"] - floor[b] >= spare:
                continue
            ss = o.details[k]["stops"]
            prev = u
            trace = []
            for s in ss:
                n = s["w"]
                hop = check.dist[prev, n]
                work = sum(map(o.ceil, s["loads"].values())) * 25
                trace.append((n, hop, work))
                prev = n
            tr = tuple(trace)
            for i, (n, hop, work) in enumerate(tr):
                state[b, tr, i] = n, work
                if work and n not in check.H[u]:
                    visitors[n].add(u)
            for start in range(max(0, a - 6), e + 1):
                arrive(
                    (b, tr, 0), check.drive(start * 36000 + 12000, tr[0][1])[1] // 24
                )

    def after(task, t):
        b, tr, i = task
        if i + 1 < len(tr):
            arrive((b, tr, i + 1), check.drive(t * 24, tr[i + 1][1])[1] // 24)

    def start(task, t, earliest):
        b, tr, i = task
        n, work = state[task]
        if not work:
            after(task, t)
            return
        end = o.service(t * 24, work * 24) // 24
        if end <= cutoff:
            finishes[end][task] = min(finishes[end].get(task, earliest), earliest)
        # A saturated public day can defer work to the next opening.
        # Retain the job's original arrival for FCFS comparisons.
        if (
            len(visitors[n] - {check.requests[b][0]}) >= 3
            and n not in check.H[check.requests[b][0]]
        ):
            for future in range(
                (t // 1500 + 1) * 1500 + 500, min(earliest + 4500, cutoff) + 1, 1500
            ):
                end = o.service(future * 24, work * 24) // 24
                if end <= cutoff:
                    finishes[end][task] = min(
                        finishes[end].get(task, earliest), earliest
                    )

    for t in range(cutoff + 1):
        for task in arrivals.pop(t, []):
            n, w = state[task]
            if w:
                queued[n].add(task)
                arrived[task].append(t)
            start(task, t, t)
        by_site = {}
        for task, earliest in finishes.pop(t, {}).items():
            b, tr, i = task
            n, _ = state[task]
            after(task, t)
            by_site[n, b] = min(by_site.get((n, b), earliest), earliest)
        for (n, b), earliest in by_site.items():
            log[n].append((t, earliest, b))
            for q in queued[n]:
                if q[0] == b:
                    continue
                aa = arrived[q]
                idx = bisect_left(aa, max(earliest, t - 4500))
                if idx < len(aa):
                    start(q, t, aa[idx])
    return log


def best_wait(route, phase, first, last):
    """Earliest legal rejoin after parking ends at phase, ignoring other queues."""
    ss = route["stops"]
    now = phase
    prev = ss[first]["w"]
    for j in range(first + 1, last + 1):
        s = ss[j]
        node = s["w"]
        _, arr = check.drive(now, check.dist[prev, node])
        work = 600 * sum(map(o.ceil, s["loads"].values()))
        if j < last:
            now = o.service(arr, work)
        elif work:
            now = (
                (arr // check.DAY + 1) * check.DAY + check.OPEN
                if arr % check.DAY == check.CLOSE
                else arr
            )
        else:
            now = check.drive(arr, check.dist[node, ss[j + 1]["w"]])[0]
        prev = node
    return len(check.idle_days(phase, now))


if __name__ == "__main__":
    suspects = []
    for b, keys in o.routes.items():
        grouped = [k for k in keys if o.details[k]["g"]]
        minimum = min(o.details[k]["L"] for k in grouped if o.isolated_ok[k])
        suspects.extend(k for k in grouped if o.details[k]["L"] < minimum)
    assert len(suspects) == 2 and all(k[0] == 20 for k in suspects)
    b = 20
    u, a, e = check.requests[b]
    # In both exceptional routes the first stop is the parking warehouse.
    # Before work starts there, removing this batch cannot postpone any job
    # that precedes it in the FCFS queue.
    log = possible(b, True, o.group_lb, (e + 4) * 1500)
    proof = []
    for k in suspects:
        r = o.details[k]
        ((first, last),) = r["pairs"]
        assert first == 0
        s = r["stops"][0]
        n = s["w"]
        work = 600 * sum(map(o.ceil, s["loads"].values()))
        phases = {
            p
            for p in range(check.OPEN, check.CLOSE + 1, 24)
            if best_wait(r, p, first, last) <= 1
        }
        for start in range(max(0, a - 6), e + 1):
            arrival = (
                check.drive(start * check.DAY + check.OPEN, check.dist[u, n])[1] // 24
            )
            starts = {arrival}
            starts.update(
                t for t, prior, _ in log[n] if prior <= arrival <= t <= arrival + 4500
            )
            starts.update((start + i) * 1500 + 500 for i in (1, 2, 3))
            finish = {o.service(t * 24, work) % check.DAY for t in starts}
            assert finish.isdisjoint(phases)
            proof.append(
                [k[1], n, start + 1, len(phases), len(finish), len(finish & phases)]
            )
    check.save(
        "Q3_distance_bound.csv",
        "原批20路线索引,首站,出发日序,S10允许留置完工相位数,外包络可能完工相位数,交集数",
        proof,
    )
    print("Grouped joint distance lower bound", float(o.group_lb))
