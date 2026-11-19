"""Recalculate the four published totals from pinned Git blobs. Requires openpyxl."""
import csv
import io
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction

from openpyxl import load_workbook

REV = "f9cc377bf60a83c8e3323f8778a662c0f8fb9d01"


def git(*args):
    return subprocess.check_output(["git", "-C", sys.argv[1], *args])


def blob(path):
    return git("show", f"{REV}:{path}")


def rows(path):
    book = load_workbook(io.BytesIO(blob(path)), data_only=True)
    return list(book.active.values)


def days(value):
    if isinstance(value, (int, float)):
        d = date(1899, 12, 30) + timedelta(days=value)
        return [d.replace(year=2026)]
    return [date(2026, int(m), int(d)) for m, d in re.findall(r"(\d+)月(\d+)", value)]


def start_dates(original, p2):
    # Identify the original request by its own cargo lines. Intersect all matches.
    index = defaultdict(set)
    for batch, period, unit, wh, _, item, qty, *_ in original[1:]:
        if isinstance(batch, int):
            key = unit, days(period)[0]
        if wh:
            warehouse = wh
        if item and isinstance(qty, (int, float)):
            index[key[0], warehouse, item, qty].add(key[1])
    matches = {}
    unmatched = defaultdict(int)
    for batch, unit, wh, _, item, qty, proxy, *_ in p2[1:]:
        if batch is not None:
            current, executor = batch, unit
        if proxy is not None:
            own = proxy == 0
        if wh:
            warehouse = wh
        if own and item:
            candidates = index[executor, warehouse, item, qty]
            if not candidates:
                unmatched[current] += 1
                continue
            matches[current] = matches.get(current, candidates) & candidates
    if any(len(v) != 1 for v in matches.values()):
        raise ValueError("Original request date is ambiguous")
    print("Own cargo rows without an exact source match by batch:", dict(unmatched))
    return {k: next(iter(v)) for k, v in matches.items()}


def calculate():
    original = git("ls-tree", "-rz", "--name-only", REV, "--", "problem/F/original").decode().split("\0")
    def attachment(n):
        path, = [p for p in original if f"/附件{n} " in p]
        return rows(path)

    matrix = attachment(1)
    dist = {r[0]: dict(zip(matrix[0][1:], r[1:])) for r in matrix[1:]}
    specs = attachment(5)
    units = [h.split()[0] for h in specs[0][1:13]]
    capacity = {r[0]: dict(zip(units, r[1:13])) for r in specs[1:]}
    starts = start_dates(attachment(4), rows("results/F/问题2_results.xlsx"))
    groups = defaultdict(list)
    for r in rows("results/F/问题3_results.xlsx")[1:]:
        if r[0] is not None:
            batch = r[0]
        groups[batch].append(r)

    tau = delta = distance = 0
    weighted = Fraction()
    for batch, records in groups.items():
        begin, *end = days(records[0][1])
        tau += ((end or [begin])[-1] - begin).days + 1
        delta += abs((begin - starts[batch]).days)
        unit = records[0][2]
        previous = unit
        load = lifted = numerator = Fraction()
        held = {}
        for r in records:
            if r[3]:
                site = r[3]
                leg = dist[previous][site]
                distance += leg
                numerator += leg * load
                load += held.pop(site, 0)
                previous = site
            if r[5]:
                direction, accompanies = r[5], r[11]
            if r[6]:
                amount = Fraction(r[7], capacity[r[6]][unit])
                if direction == "收":
                    load -= amount
                elif direction == "发":
                    lifted += amount
                    if accompanies == "否":
                        held[site] = held.get(site, 0) + amount
                    else:
                        load += amount
                else:
                    raise ValueError(direction)
        if previous != unit or held or load:
            raise ValueError(f"Unclosed mileage ledger in batch {batch}")
        weighted += numerator / lifted
    return dict(tau=tau, delta=delta, D=distance, L=float(weighted))


if __name__ == "__main__":
    totals = calculate()
    summary = csv.DictReader(io.StringIO(blob("results/F/p3/summary.csv").decode("utf-8-sig")))
    main, = [r for r in summary if r["name"].startswith("主路线")]
    for key, value in totals.items():
        print(f"{key}  recalculated={value}  summary={main[key]}  diff={value-float(main[key]):.12g}")
