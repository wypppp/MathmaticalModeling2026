"""通用数据摘要：为任意文件夹中的 xlsx/csv 生成 markdown 说明（结构 + 数值统计），供无法读取表格的模型使用。

用法：python tools/data_digest.py <附件文件夹> > problem/<题号>/数据摘要.md
只输出客观数字，不做解读。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import openpyxl


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def numeric_stats(rows):
    if not rows:
        return []
    ncol = max(len(r) for r in rows)
    out = []
    for j in range(ncol):
        col = [r[j] for r in rows if j < len(r)]
        nums = [float(x) for x in col if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if len(nums) >= max(3, 0.5 * len(col)):
            a = np.array(nums)
            out.append((j, len(col), len(nums), a.min(), a.max(), a.mean(), a.std(), len(col) - len(nums)))
    return out


def digest_rows(name, rows):
    print(f"### {name}：{len(rows)} 行 × {max((len(r) for r in rows), default=0)} 列\n")
    print("```")
    for r in rows[:4]:
        print(" | ".join(fmt(v) for v in r[:10]) + (" | …" if len(r) > 10 else ""))
    if len(rows) > 4:
        print("…")
        print(" | ".join(fmt(v) for v in rows[-1][:10]))
    print("```\n")
    st = numeric_stats(rows[1:])
    if st:
        header = rows[0] if rows else []
        print("| 列 | 列名 | 非空数值个数 | 最小 | 最大 | 均值 | 标准差 | 非数值个数 |")
        print("|---|---|---|---|---|---|---|---|")
        for j, n, k, mn, mx, mu, sd, bad in st[:40]:
            hn = fmt(header[j]) if j < len(header) else ""
            print(f"| {j + 1} | {hn} | {k} | {mn:.6g} | {mx:.6g} | {mu:.6g} | {sd:.6g} | {bad} |")
        if len(st) > 40:
            print(f"| … | 另有 {len(st) - 40} 个数值列 | | | | | | |")
        print()


def main(folder):
    folder = Path(folder)
    print(f"# 数据摘要（自动生成，来源：{folder}）\n\n> 只含客观结构与统计，以原始文件为准。\n")
    for f in sorted(folder.rglob("*")):
        if f.suffix.lower() in (".xlsx", ".xlsm"):
            print(f"## {f.relative_to(folder)}\n")
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
            for ws in wb.worksheets:
                digest_rows(f"工作表「{ws.title}」", [list(r) for r in ws.iter_rows(values_only=True)])
        elif f.suffix.lower() == ".csv":
            import csv
            print(f"## {f.relative_to(folder)}\n")
            with open(f, encoding="utf-8-sig", errors="replace") as fh:
                rows = []
                for r in csv.reader(fh):
                    conv = []
                    for x in r:
                        try:
                            conv.append(float(x))
                        except ValueError:
                            conv.append(x)
                    rows.append(conv)
            digest_rows("CSV", rows)


if __name__ == "__main__":
    main(sys.argv[1])
