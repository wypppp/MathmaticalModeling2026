"""Audit the exported Q2 workbook using only original input data and spec v2."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from inputs import (ATTACHMENTS, CAP, ETA, ROOT, SOC_MAX, SOC_MIN, STEPS,
                    attachment1, attachment2, day, interval, number)

TOL = 1e-6
ROUND = 0.00005  # Each exported numeric cell is rounded to four decimal places.
FIRST, LAST = date(2025, 2, 1), date(2025, 12, 31)
DATES = [FIRST + timedelta(days=i) for i in range((LAST - FIRST).days + 1)]
BLOCKS = [slice(i, i + 24) for i in range(0, STEPS, 24)]


def table(book, name, header):
    rows = iter(book[name].values)
    if tuple(next(rows)) != tuple(header):
        raise ValueError(f"{name} 表头或时段标签不符合 spec")
    return enumerate(rows, 2)


def grouped_rows(rows):
    groups = {}
    for row_number, (date_value, *values) in rows:
        if date_value is not None:
            current = day(date_value)
            if current in groups:
                raise ValueError(f"第 {row_number} 行日期块重复：{current}")
            groups[current] = []
        if not groups:
            raise ValueError(f"第 {row_number} 行缺少所属日期")
        groups[current].append((row_number, values))
    return groups


def slot_range(label):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", str(label))
    if not match:
        raise ValueError(f"紧急购电时间段无效：{label!r}")
    h1, m1, h2, m2 = map(int, match.groups())
    start, stop = (h1 * 60 + m1) // 10, (h2 * 60 + m2) // 10
    if not (0 <= start < stop <= STEPS and label == interval(start, stop)):
        raise ValueError(f"紧急购电时间段无效：{label!r}")
    return start, stop


def read_export(path):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        plan = {}
        plan_header = ["日期\\时间", *(interval(i, i + 1) for i in range(STEPS)),
                       "全天购电量", "全天购电费"]
        for row, values in table(book, "计划购电量", plan_header):
            date_key = day(values[0])
            if date_key in plan:
                raise ValueError(f"计划购电量日期重复：{date_key}")
            plan[date_key] = row, np.array([number(v) for v in values[1:]])
        battery = grouped_rows(table(book, "充放电量",
                                      ["日期", "时间段", "充电量", "放电量", "时刻", "储电量"]))
        grouped = grouped_rows(table(book, "紧急购电量", ["日期", "购电时间段", "购电量"]))
        emergency = {}
        for date_key, rows in grouped.items():
            runs = []
            if len(rows) == 1 and rows[0][1] == ["无", 0]:
                emergency[date_key] = runs
                continue
            end = -1
            for row, (label, amount) in rows:
                start, stop = slot_range(label)
                if start <= end:
                    raise ValueError(f"紧急购电量第 {row} 行区间重叠、相邻或乱序")
                runs.append((start, stop, number(amount)))
                end = stop
            emergency[date_key] = runs
        if list(plan) != DATES or list(battery) != DATES or set(emergency) - set(DATES):
            raise ValueError("计划或充放电日期不符合 2025-02-01 至 2025-12-31，或紧急记录越界")
        return plan, battery, emergency
    finally:
        book.close()


def compatible_ledger(surplus, charge, discharge, soc_start, soc_end, runs, price):
    """LP outer bound on the unknown ten-minute schedule and emergency cost.

    At net battery action x=c-d, the exact slot graph has breakpoints at
    -CAP, 0, CAP and at the two extreme surpluses allowed by rounding q.
    Their convex hull contains every admissible slot, including both exclusions.
    A feasible relaxation cannot establish the original schedule or its validity.
    """
    matrix_rows, matrix_cols, matrix_values, rhs, bounds, cost = [], [], [], [], [], []

    def equation(columns, coefficients, value):
        matrix_rows.extend([len(rhs)] * len(columns))
        matrix_cols.extend(columns)
        matrix_values.extend(coefficients)
        rhs.append(value)

    for i in range(STEPS + 1):
        lower, upper = SOC_MIN, SOC_MAX
        if i in (0, STEPS):
            reading = soc_start if i == 0 else soc_end
            lower, upper = max(lower, reading - ROUND), min(upper, reading + ROUND)
        if lower > upper:
            return None
        bounds.append((lower, upper))
        cost.append(0)
    run_for_slot = {}
    for j, (a, b, _) in enumerate(runs):
        run_for_slot.update({t: j for t in range(a, b)})
    block_vars = [[] for _ in range(6)]
    run_vars = [[] for _ in runs]

    for t, center in enumerate(surplus):
        columns, charges, discharges, emergencies = [], [], [], []
        ymin, ymax = center - ROUND, center + ROUND
        if t not in run_for_slot:
            if ymax < -CAP:
                return None
            vertices = [(x, 0.0) for x in (-CAP, min(0, ymax), min(CAP, ymax))]
        else:
            # Grid intersections also include any x-axis kink inside the y band.
            levels = [ymin, *(y for y in (-CAP, 0, CAP) if ymin < y < ymax), ymax]
            vertices = [(x, max(0, x - y))
                        for y in levels
                        for x in sorted({-CAP, 0, CAP, float(np.clip(y, -CAP, CAP))})]
        for action, e in vertices:
            columns.append(len(bounds))
            charges.append(max(0, action))
            discharges.append(max(0, -action))
            emergencies.append(e)
            bounds.append((0, 1))
            cost.append(5 * price[t] * e)
        equation(columns, [1] * len(columns), 1)
        equation([t, t + 1, *columns],
                 [-1, 1, *(-ETA * c + d / ETA for c, d in zip(charges, discharges))], 0)
        block_vars[t // 24].extend(zip(columns, charges, discharges))
        if t in run_for_slot:
            run_vars[run_for_slot[t]].extend(zip(columns, emergencies))

    def rounded_total(columns, values, reading):
        slack = len(bounds)
        bounds.append((-ROUND, ROUND))
        cost.append(0)
        equation([*columns, slack], [*values, 1], reading)

    for entries, c, d in zip(block_vars, charge, discharge):
        columns, charges, discharges = zip(*entries)
        rounded_total(columns, charges, c)
        rounded_total(columns, discharges, d)
    for entries, (_, _, energy) in zip(run_vars, runs):
        rounded_total(*zip(*entries), energy)

    matrix = coo_matrix((matrix_values, (matrix_rows, matrix_cols)),
                        shape=(len(rhs), len(bounds))).tocsr()
    cost = np.array(cost)
    def optimize(objective):
        result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs-ipm")
        if result.status not in (0, 2):
            result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds,
                             method="highs-ds", options={"presolve": False})
        return result

    low = optimize(cost)
    if low.status == 2:
        return None
    if not low.success:
        raise RuntimeError(low.message)
    if not runs:
        return 0.0, 0.0
    high = optimize(-cost)
    if not high.success:
        raise RuntimeError(high.message)
    return low.fun, -high.fun


def audit(path, price, load, pv):
    plan, battery, emergency = read_export(path)
    issues, daily = [], []
    previous_soc = None

    def compare(name, residual, rounding_limit, location, units):
        if residual > TOL:
            issues.append({"date": date_key, "check": name, "location": location,
                           "residual": residual, "rounding_limit": rounding_limit,
                           "units": units,
                           "status": "within_rounding" if residual <= rounding_limit + TOL
                           else "inconsistent"})

    for date_key in DATES:
        plan_row, values = plan[date_key]
        q, reported_energy, reported_fee = values[:STEPS], *values[STEPS:]
        calc_fee = price @ q
        compare("plan_nonnegative", max(0, -min(q)), 0, f"计划购电量!B{plan_row}:EO{plan_row}", "kWh")
        compare("plan_energy", abs(sum(q) - reported_energy), (STEPS + 1) * ROUND,
                f"计划购电量!EP{plan_row}", "kWh")
        compare("plan_fee", abs(calc_fee - reported_fee), (1 + sum(price)) * ROUND,
                f"计划购电量!EQ{plan_row}", "元")

        rows = battery[date_key]
        expected = [interval(b.start, b.stop) for b in BLOCKS]
        if [values[0] for _, values in rows] != expected:
            raise ValueError(f"{date_key} 充放电 4 小时分段不齐或乱序")
        if [values[3] for _, values in rows] != ["0:00", "24:00", None, None, None, None]:
            raise ValueError(f"{date_key} SOC 时刻标签不符")
        charge, discharge = np.array([[number(v[1]), number(v[2])] for _, v in rows]).T
        soc_start, soc_end = (number(v[4]) for _, v in rows[:2])
        soc = np.r_[soc_start, soc_start + np.cumsum(ETA * charge - discharge / ETA)]
        soc_error = abs(soc[-1] - soc_end)
        compare("soc_day_recurrence", soc_error, ROUND * (2 + 6 * (ETA + 1 / ETA)),
                f"充放电量!C{rows[0][0]}:F{rows[-1][0]}", "kWh")
        for j, value in enumerate(soc):
            compare("soc_block_boundary", max(0, SOC_MIN - value, value - SOC_MAX),
                    ROUND * (1 + j * (ETA + 1 / ETA)), f"{j * 4}:00", "kWh")
        compare("soc_end_bound", max(0, SOC_MIN - soc_end, soc_end - SOC_MAX),
                ROUND, "24:00", "kWh")
        cross_day = None if previous_soc is None else abs(previous_soc - soc_start)
        if cross_day is not None:
            compare("soc_cross_day", cross_day, 2 * ROUND, "0:00", "kWh")
        previous_soc = soc_end

        surplus = q + pv[date_key] - load[date_key]
        runs = emergency.get(date_key, [])
        for a, b, energy in runs:
            compare("emergency_positive", max(0, -energy), 0, interval(a, b), "kWh")
        for b, c, d in zip(BLOCKS, charge, discharge):
            label = interval(b.start, b.stop)
            compare("battery_nonnegative", max(0, -c, -d), 0, label, "kWh")
            compare("block_power_exclusion", max(0, c + d - 24 * CAP), 2 * ROUND, label, "kWh")

        emergency_total = sum(e for _, _, e in runs)
        spill = sum(surplus) + sum(discharge) - sum(charge) + emergency_total
        spill_uncertainty = (STEPS + 12 + len(runs)) * ROUND
        compare("implied_daily_spill_nonnegative", max(0, -spill), spill_uncertainty, "全天", "kWh")
        try:
            bounds = compatible_ledger(surplus, charge, discharge, soc_start, soc_end, runs, price)
        except RuntimeError as error:
            raise RuntimeError(f"{date_key}：{error}") from error
        if bounds is None:
            issues.append({"date": date_key, "check": "slot_constraints", "location": "全天",
                           "residual": "", "rounding_limit": "", "units": "",
                           "status": "inconsistent"})
        e_low, e_high = bounds if bounds is not None else (None, None)
        plan_uncertainty = sum(price) * ROUND
        daily.append({
            "date": date_key, "soc_start_kwh": soc_start, "soc_end_kwh": soc_end,
            "soc_recurrence_abs_kwh": soc_error, "soc_cross_day_abs_kwh": cross_day,
            "plan_energy_delta_kwh": sum(q) - reported_energy, "plan_fee_recomputed_yuan": calc_fee,
            "plan_fee_reported_yuan": reported_fee, "plan_fee_delta_yuan": calc_fee - reported_fee,
            "emergency_kwh": emergency_total, "emergency_groups": len(runs),
            "emergency_fee_lower_yuan": e_low, "emergency_fee_upper_yuan": e_high,
            "total_fee_lower_yuan": None if bounds is None else calc_fee - plan_uncertainty + e_low,
            "total_fee_upper_yuan": None if bounds is None else calc_fee + plan_uncertainty + e_high,
            "implied_spill_kwh": spill, "implied_spill_uncertainty_kwh": spill_uncertainty,
            "slot_relaxation_feasible": bounds is not None,
        })
    return daily, issues


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(daily, issues):
    categories = defaultdict(Counter)
    for entry in issues:
        categories[entry["check"]][entry["status"]] += 1
    summary = {
        "days": len(daily), "slots": len(daily) * STEPS,
        "days_within_relaxation": sum(row["slot_relaxation_feasible"] for row in daily),
        "issues": categories,
    }
    for field in ("soc_recurrence_abs_kwh", "soc_cross_day_abs_kwh",
                  "plan_energy_delta_kwh", "plan_fee_delta_yuan"):
        worst_day = max((r for r in daily if r[field] is not None), key=lambda r: abs(r[field]))
        summary[f"max_abs_{field}"] = {"date": str(worst_day["date"]), "value": abs(worst_day[field])}
    for field in ("plan_fee_recomputed_yuan", "plan_fee_reported_yuan", "emergency_kwh",
                  "emergency_fee_lower_yuan", "emergency_fee_upper_yuan", "total_fee_lower_yuan",
                  "total_fee_upper_yuan", "implied_spill_kwh", "implied_spill_uncertainty_kwh"):
        values = [r[field] for r in daily]
        summary[field] = None if any(v is None for v in values) else sum(values)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=ROOT / "results/q2/result2_baseline.xlsx")
    parser.add_argument("--attachment1", type=Path, default=ATTACHMENTS / "附件1.xlsx")
    parser.add_argument("--attachment2", type=Path, default=ATTACHMENTS / "附件2.xlsx")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    price, _, _ = attachment1(args.attachment1)
    load, pv = attachment2(args.attachment2)
    daily, issues = audit(args.workbook, price, load, pv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "q2_daily.csv", daily, list(daily[0]))
    write_csv(args.out_dir / "q2_issues.csv", issues,
              ["date", "check", "location", "residual", "rounding_limit", "units", "status"])
    print(json.dumps(summarize(daily, issues), indent=2, ensure_ascii=False))
    return int(any(entry["status"] == "inconsistent" for entry in issues))


if __name__ == "__main__":
    raise SystemExit(main())
