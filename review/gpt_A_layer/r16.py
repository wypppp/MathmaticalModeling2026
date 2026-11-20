"""从附件 1、2、3、5 重算 R16。依赖 openpyxl；脚本同目录输出逐批证据。"""
import csv
import heapq
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from fractions import Fraction
from math import ceil
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent
DATA = OUT.parents[1] / "problem/F/original/附件"


def sheet(number):
    path = next(DATA.glob(f"附件{number} *.xlsx"))
    return openpyxl.load_workbook(path, data_only=True).active


def period(value):
    if isinstance(value, int):
        day = date(1899, 12, 30) + timedelta(days=value)
        pairs = [(day.month, day.day)] * 2
    else:
        pairs = re.findall(r"(\d+)月(\d+)", value)
        if len(pairs) == 1:
            pairs *= 2
    return tuple((date(2026, int(m), int(d)) - date(2026, 4, 1)).days for m, d in pairs)


def details(number):
    ws = sheet(number)
    cells = {}
    for block in ws.merged_cells.ranges:
        val = ws.cell(block.min_row, block.min_col).value
        for row, col in block.cells:
            cells[row, col] = val
    for i in range(3, ws.max_row + 1):
        r = [cells.get((i, j), ws.cell(i, j).value) for j in range(1, ws.max_column + 1)]
        b, when, unit = r[:3]
        product, qty = r[5:7] if number == 2 else r[4:6]
        if re.fullmatch(r"D\d+", str(product)):
            yield b, period(when), unit, product, qty, r[3], r[-1] or "", i


dist_rows = list(sheet(1).values)
distance = {(r[0], node): val for r in dist_rows[1:] for node, val in zip(dist_rows[0][1:], r[1:])}
cap = {r[0]: r for r in list(sheet(5).values)[1:]}
before = defaultdict(Counter)
requested = {}
for b, when, unit, product, qty, warehouse, note, i in details(2):
    before[b, unit][product, qty] += 1
    requested[b] = when

homes = dict(zip([f"U{i}" for i in range(1, 13)], "WT WS WQ WR WS WP WU WO WP WS WO WO".split()))
own = defaultdict(Counter)
after = {}
targets = defaultdict(list)
loads = defaultdict(lambda: defaultdict(lambda: [Fraction(), Fraction()]))
pre = defaultdict(list)
post = defaultdict(list)
for b, when, unit, product, qty, movement, note, i in details(3):
    after[b] = unit, when
    wh = re.search(r"W[A-U]", movement).group()
    if wh not in targets[b]:
        targets[b].append(wh)
    proxy = re.search(r"代(?:领|交)?(U\d+)", note)
    if not proxy:
        own[b][product, qty] += 1
    home = homes[unit]
    explicit = re.search(r"(?:存放至|从)(W[A-U])", note)
    if explicit:
        home = explicit[1]
    if b == 9 and proxy:
        home = "WQ"
    if b == 23 and proxy:
        home = "WO"
    picking = movement.startswith(wh)
    s = Fraction(qty, cap[product][int(unit[1:])])
    loads[b][wh][0 if picking else 1] += s
    loads[b][home][1 if picking else 0] += s
    if home not in targets[b] and home not in (post[b] if picking else pre[b]):
        (post[b] if picking else pre[b]).append(home)

routes = {}
matches = {}
for b, (unit, when) in after.items():
    scores = [(sum((goods & own[b]).values()), k) for (k, u), goods in before.items() if u == unit]
    score = max(n for n, k in scores)
    winners = [k for n, k in scores if n == score]
    assert score > 0 and len(winners) == 1, (b, scores)
    matches[b] = winners[0], score
    # 同一存放仓库出程只装、回程只卸。多处返卸采用问题1既有顺序。
    returns = [w for w in post[b] if w not in targets[b]]
    if b == 9:
        returns = ["WQ", "WT"]
    visits = [(w, ceil(loads[b][w][0])) for w in pre[b]]
    visits += [(w, sum(map(ceil, loads[b][w]))) for w in targets[b]]
    visits += [(w, ceil(loads[b][w][1])) for w in returns]
    routes[b] = [(unit, 0), *visits, (unit, 0)]
assert len(matches) == len(set(k for k, score in matches.values())) == 27

# 压缩工作时间轴：每天 500 格，每格等于行驶 1 km 的时间，
# 每作业 1 车占 25 格。恰好 500 的日界在结束时归前日、出发时归次日。
def simulate(free, shared):
    events = []
    for b, (unit, when) in after.items():
        heapq.heappush(events, (when[0] * 500, b, 0))
    until = Counter()
    users = defaultdict(set)
    used = Counter()
    result = {}
    while events:
        arrival, b, j = heapq.heappop(events)
        unit, when = after[b]
        node, cars = routes[b][j]
        if j == len(routes[b]) - 1:
            result[b] = (arrival - 1) // 500 - when[0] + 1
            continue
        now = max(arrival, until[node]) if shared and cars else arrival
        constrained = shared and node in set(targets[b] + pre[b] + post[b]) and node not in (
            {"WQ", "WU"} if unit == "U7" else {"WO", "WS"} if unit == "U11" else {homes[unit]})
        if constrained and cars:
            # 用连续作业工作量计日额度；20 车恰好占满 8 小时。
            work = cars * 25
            while work:
                day = now // 500
                key = node, day
                if unit not in users[key] and len(users[key]) >= 3:
                    now = (day + 1) * 500
                    continue
                amount = min(work, 500 - now % 500, 500 - used[key])
                assert amount > 0
                users[key].add(unit)
                used[key] += amount
                now += amount
                work -= amount
        else:
            now += cars * 25
        if shared and cars:
            until[node] = now
        length = distance[node, routes[b][j + 1][0]]
        if not free and now % 500 and now % 500 + length > 500:
            now += 500 - now % 500
        heapq.heappush(events, (now + length, b, j + 1))
    return result


runs = [simulate(free, shared) for shared in (False, True) for free in (False, True)]
with (OUT / "R16.csv").open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow("件3批,单位,件2批,同单位相同品种数量行数,提报开始日序,提报结束日序,实施开始日序,实施结束日序,提报天数,表列天数,逐批严格,逐批续行,联动严格,联动续行,路线及作业车数".split(","))
    for b, (unit, when) in after.items():
        k, score = matches[b]
        a, e = requested[k]
        writer.writerow([b, unit, k, score, a+1, e+1, when[0]+1, when[1]+1, e-a+1, when[1]-when[0]+1,
                         *(run[b] for run in runs), " → ".join(f"{w}({c})" for w, c in routes[b])])
