"""论文表格：从结果台账生成 Markdown 表，输出 paper/tables/*.md。

用法：python tools/make_tables.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results" / "F"
OUT = ROOT / "paper" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")
CASE = {"R1": "代领①", "R2": "代领②", "R3": "代领③", "R4": "代领④", "R5": "代领⑤", "R6": "代交①", "R7": "代交②", "R8": "代交③"}


def table_6_1():
    t = pd.read_csv(R / "p1/trace.csv")
    t = t[t.how != "自办"].sort_values(["executor", "owner", "batch3"])
    lines = ["| # | 货主 | 附件 2 批次 | 执行方 | 附件 3 批次 | 货物流向 | 方向 | 方式 | 情形 | 等效车数（执行方车型） |",
             "|---:|---|---:|---|---:|---|---|---|---|---:|"]
    for i, r in enumerate(t.itertuples(), 1):
        how = {"代领": "代领", "代交": "代交", "反转代交": "内部互转反转为代交"}[r.how]
        flow = f"{r.w}→{r.h}" if r.dir == "领" else f"{r.h}→{r.w}"  # 货物流向
        lines.append(f"| {i} | {r.owner} | {int(r.batch2)} | {r.executor} | {int(r.batch3)} | {flow} | {r.dir} | {how} | "
                     f"{CASE.get(r.case, r.case)} | {r.s_exec:.3f} |")
    (OUT / "表6-1_Y1转移清单.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("写出 表6-1，", len(t), "行")
    return "\n".join(lines)


if __name__ == "__main__":
    table_6_1()
