"""Gemini 包 3（v2.3 增量代码审计）的触发条件探测：在给定方案中逐条查找 9 个问题描述的情形是否真的出现。

只读结果 xlsx（附件 7/8 格式）、对应的逐站台账 csv（引擎输出，含未舍入时刻）和指派 csv。
用法：python tools/pack3_probe.py <附件7/8格式.xlsx> <steps.csv 或 -> <assign.csv>
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import f_check as fc  # noqa: E402

H = fc.H


def main(p3, steps_csv, assign_csv):
    D = fc.read_dist()
    P3 = fc.read_p3(p3)
    out = defaultdict(list)
    for bt in P3:
        b, x = bt["id"], bt["unit"]
        own = set(H[x])
        stops = bt["stops"]
        ext_ops = [i for i, st in enumerate(stops) if st["segs"] and st["node"] not in own and st["node"].startswith("W")]
        first_ext = ext_ops[0] if ext_ops else None
        for i, st in enumerate(stops):
            for sg in st["segs"]:
                # 1：在 H(x) 晚装代交货（已到访过外部仓库作业之后）
                if st["node"] in own and sg["flag"] == -1 and sg["eq"] > 0 and first_ext is not None and i > first_ext:
                    out["1 R6/REV 代交货晚装"].append((b, x, st["node"], i, sg["who"]))
                # 2：在外部仓库卸代领货后，又去别的外部仓库作业
                if st["node"] not in own and sg["flag"] == 1 and sg["eq"] < 0 and any(j > i for j in ext_ops):
                    out["2 外仓卸代领货后又去外仓作业"].append((b, x, st["node"], i, sg["who"]))
        # 6：恰好 500 km 的路段
        seq = [x] + [st["node"] for st in stops]
        for u, v in zip(seq, seq[1:]):
            if u != v and abs(float(D[(u, v)]) - 500) < 1e-9:
                out["6 恰好 500 km 路段"].append((b, u, v))
        # 9：同站两次留置
        lefts = [st["node"] for st in stops for sg in st["segs"] if sg["follow"] == "是"]
        if len(lefts) != len(set(lefts)):
            out["9 同站两次留置"].append((b, lefts))
    if steps_csv != "-":
        s = pd.read_csv(steps_csv)
        # 3：留置车的合并整日闲置（留置结束日 → 汇合站开工/离开日）
        for b, g in s.groupby("batch"):
            g = g.sort_values("seq")
            left_end = {}
            for r in g.itertuples():
                if isinstance(r.leave, str) and r.leave:
                    left_end[r.node] = r.end_day
                elif r.rejoin and r.node in left_end:
                    work = r.c_unload + r.c_load > 0
                    resume = r.start_day if work else (r.depart_day if r.depart_h > 1e-9 else r.depart_day - 1 + 1)
                    idle = resume - left_end.pop(r.node) - 1
                    if work and r.start_h > 1e-9 and r.start_day > r.arrive_day:
                        pass
                    if idle > 1:
                        out["3 留置+排队合并闲置 > 1 天"].append((b, r.node, idle))
        # 4：同一仓库两批到达相差不足 1 分钟（舍入到分钟后同刻、或先后可能颠倒）
        s["t"] = s.arrive_day * 8 + s.arrive_h
        ops = s[(s.c_unload + s.c_load) > 0]
        for n, g in ops.groupby("node"):
            g = g.sort_values("t")
            for (b1, t1), (b2, t2) in zip(zip(g.batch, g.t), list(zip(g.batch, g.t))[1:]):
                if b1 != b2 and abs(t2 - t1) < 1 / 60 + 1e-12:
                    out["4 同仓到达相差 < 1 分钟"].append((n, b1, b2, round((t2 - t1) * 60, 3)))
        # 5：时刻离 8:00/16:00 不足 1 分钟但不恰好相等
        for col in ("arrive_h", "start_h", "end_h", "depart_h"):
            for r in s.itertuples():
                h = getattr(r, col)
                for edge in (0.0, 8.0):
                    if 1e-9 < abs(h - edge) < 1 / 60:
                        out["5 时刻贴近 8:00/16:00"].append((r.batch, r.node, col, h))
    # 7、8：指派中的 R5、R4 情形
    a = pd.read_csv(assign_csv)
    for r in a.itertuples():
        if r.option == "T" and r.case in ("R4", "R5"):
            out[f"7/8 指派中的 {r.case}"].append((r.block, r.to_batch, r.aux))
    print(f"== {p3}")
    for k in sorted(out):
        print(f"  {k}：{len(out[k])} 处", out[k][:6])
    if not out:
        print("  无")
    return out


if __name__ == "__main__":
    main(*sys.argv[1:4])
