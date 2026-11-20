"""问题 3 主方案与孤立下界的逐批差距分解（正文 8.3 节“距下界的 4 天来自……”）。

对每批：所选路线的 τ、L̄；孤立最少天数 min τ 及该天数下的最小 L̄；最小 L̄ 及该 L̄ 下的最少天数。
输出 results/F/p3/gap_decomp.csv。用法：python tools/p3_gap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_p3  # noqa: E402
import f_parse as fp  # noqa: E402
from f_run_p3 import load_assign  # noqa: E402

R = ROOT / "results" / "F"


def main():
    batches, blocks = fb.build(4)
    inst = f_p3.Instance(load_assign(R / "p2" / "assign_main.csv", blocks), batches, blocks, fp.load_cap(), fp.load_dist())
    m = pd.read_csv(R / "p3" / "batches_main.csv").set_index("batch")
    rows = []
    for b in inst.ids:
        c = inst.cands[b]
        x = c[int(m.at[b, "route"])]
        mt = min(r["tau"] for r in c)
        mL = min(r["Lbar"] for r in c)
        rows.append(dict(
            batch=b, unit=m.at[b, "unit"], start=int(m.at[b, "start"]), a=int(m.at[b, "a"]),
            tau=int(m.at[b, "tau"]), iso_tau=x["tau"], Lbar=x["Lbar"], D=x["D"],
            min_tau=mt, Lbar_at_min_tau=min(r["Lbar"] for r in c if r["tau"] == mt),
            min_Lbar=mL, tau_at_min_Lbar=min(r["tau"] for r in c if abs(r["Lbar"] - mL) < 1e-9),
            n_cands=len(c)))
    df = pd.DataFrame(rows)
    df["extra_tau"] = df.tau - df.min_tau
    df["extra_L"] = df.Lbar - df.min_Lbar
    df["L_saved_vs_min_tau_route"] = df.Lbar_at_min_tau - df.Lbar
    df.to_csv(R / "p3" / "gap_decomp.csv", index=False, encoding="utf-8-sig")
    print(df[(df.extra_tau > 0) | (df.extra_L > 1e-6)].to_string())
    print("两项都达孤立最优的批数", int(((df.extra_tau == 0) & (df.extra_L < 1e-6)).sum()), "；超额天数", int(df.extra_tau.sum()), "；超额载货距离", df.extra_L.sum())


if __name__ == "__main__":
    main()
