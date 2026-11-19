"""Read the original attachments with their interval-end timestamps."""
from datetime import datetime, time
from numbers import Real
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
ATTACHMENTS = ROOT / "problem/2026C/original/附件"
STEPS = 144
CAP = 5000 / 6
ETA = 0.9
SOC_MIN, SOC_MAX = 1200, 10800


def stamp(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def interval(start, stop):
    return f"{stamp(start * 10)}-{stamp(stop * 10)}"


def check_ends(values):
    for i, value in enumerate(values, 1):
        if isinstance(value, time):
            value = f"{value.hour}:{value.minute:02d}"
        expected = "0:00+1" if i == STEPS else stamp(10 * i)
        if value != expected:
            raise ValueError(f"附件时标 {i}: {value!r}，预期 {expected}")


def number(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"预期有限数值，收到 {value!r}")
    return float(value)


def day(value):
    if not isinstance(value, datetime) or value.time() != time():
        raise ValueError(f"预期 Excel 日期，收到 {value!r}")
    return value.date()


def attachment1(path):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        header, *rows = book["Sheet1"].values
        if header != ("时间", "电价", "小区负载", "光伏发电预测功率") or len(rows) != STEPS:
            raise ValueError("附件 1 表头或行数不符")
        check_ends([row[0] for row in rows])
        price, load, pv = np.array([[number(v) for v in row[1:]] for row in rows]).T
        if min(price) <= 0 or min(load) < 0 or min(pv) < 0:
            raise ValueError("附件 1 电价须为正，负载与光伏须非负")
        return price, load / 6, pv / 6
    finally:
        book.close()


def attachment2(path):
    book = load_workbook(path, read_only=True, data_only=True)
    tables = []
    try:
        for name in ("小区负载", "光伏发电实际功率"):
            rows = iter(book[name].values)
            header = next(rows)
            if len(header) != STEPS + 1:
                raise ValueError(f"{name} 时段列数不符")
            check_ends(header[1:])
            table = {}
            for row in rows:
                date = day(row[0])
                power = np.array([number(v) for v in row[1:]])
                if date in table or min(power) < 0:
                    raise ValueError(f"{name} 日期重复或功率为负：{date}")
                table[date] = power / 6
            tables.append(table)
        if tables[0].keys() != tables[1].keys():
            raise ValueError("附件 2 负载和光伏日期不一致")
        return tables
    finally:
        book.close()
