"""D2 读法 b 的敏感性（evidence V33）：每笔代领代交都另须满足录 2.5 的“就近”。

① 附件 3（Y1 统筹后）的 16 笔转移逐笔判断是否“就近”；② 问题 2 在读法 b 下的最少批次（同一四级字典序、同一 2000 km 回查）。
主结果不用读法 b。用法：python src/f_d2b.py；输出 results/F/extra/d2b.csv、d2b_y1.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_p2  # noqa: E402
import f_parse as fp  # noqa: E402
from f_run_p2 import ledger, solve_checked  # noqa: E402

OUT = ROOT / "results" / "F" / "extra"


def main():
    cap, D = fp.load_cap(), fp.load_dist()
    tr = pd.read_csv(ROOT / "results" / "F" / "p1" / "trace.csv")
    moved = tr[tr.how != "自办"]
    y1 = []
    for r in moved.itertuples():
        y1.append(dict(block=r.block, executor=r.executor, owner=r.owner, w=r.w, dir=r.dir, h=r.h, case=r.case, how=r.how,
                       shared=bool(set(fb.H[r.executor]) & set(fb.H[r.owner])), nearby=f_p2.nearby(r.executor, r.owner, D)))
    y1 = pd.DataFrame(y1)
    y1.to_csv(OUT / "d2b_y1.csv", index=False, encoding="utf-8-sig")
    print(f"附件 3 跨单位转移 {len(y1)} 笔，其中不满足“就近” {int((~y1.nearby).sum())} 笔：")
    print(y1[~y1.nearby][["executor", "owner", "w", "dir", "h", "case"]].to_string(index=False))
    batches, blocks = fb.build(4)
    rows = []
    for tag, kw in (("main", {}), ("near_all", dict(near_all=True))):
        r, routes, forbid = solve_checked(batches, blocks, cap, D, **kw)
        _, tot, _ = ledger(tag, r, routes, batches, blocks, cap)
        st = r["stats"]
        rows.append(dict(variant=tag, B=tot["B"], B_bound=st.get("B_bound"), N=tot["N"], P=tot["P"], A=tot["A"], pairs=tot["pairs"], E=tot["E"],
                         U9_to_U6=st.get("U9"), n_cuts=len(forbid)))
        print(rows[-1])
    pd.DataFrame(rows).to_csv(OUT / "d2b.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
