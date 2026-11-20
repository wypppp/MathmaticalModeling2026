"""Attachment reader adapted from the independent v2.5 checker."""

import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
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
