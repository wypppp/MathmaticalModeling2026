"""问题 2 最优解唯一性诊断（指南 B 节）：字典序四级 (U9, B, A, V0) 都取最优值后，是否还有别的块指派。

做法：先按主流程得到 ≤2000 km 回查割 forbid，再在同一模型上逐个加 no-good 割（f_p2.solve(alternatives=N)），
每个替代指派再回查是否每批都有合规路线；报告替代解个数、与主解不同的块、以及车数、人数、仓库对、失衡度等次要指标。
用法：python src/f_p2_alt.py [N=200]
输出：results/F/p2/alternatives.csv
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
import f_routes as fr  # noqa: E402
from f_run_p2 import solve_checked  # noqa: E402

OUT = ROOT / "results" / "F" / "p2"


def routable(assign, batches, blocks, cap, D):
    groups = fr.batch_groups(assign, batches, blocks, cap)
    return all(fr.candidates(b, batches[b].unit, fr.batch_T(gs, batches[b].unit)[0], gs, D)[0] for b, gs in groups.items())


def main(n=200):
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    r0, _, forbid = solve_checked(batches, blocks, cap, D)
    r = f_p2.solve(batches, blocks, cap, D, forbid=forbid, alternatives=n)
    assert r["assign"] == r0["assign"], "带 forbid 重解的主解与主流程不同"
    rows = []
    for i, a in enumerate([r["assign"]] + r["alts"]):
        _, tot, _ = f_p2.summarize(a, batches, blocks, cap)
        diff = sorted(k for k in a if a[k] != r["assign"][k])
        rows.append(dict(sol=i, routable=routable(a, batches, blocks, cap, D), n_diff_blocks=len(diff),
                         diff_blocks=" ".join(map(str, diff)), **{k: v for k, v in tot.items() if not isinstance(v, (dict, list))}))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "alternatives.csv", index=False, encoding="utf-8-sig")
    print(f"字典序最优值 {r['stats']}；no-good 上限 {n}，找到替代指派 {len(r['alts'])} 个"
          f"（{'已穷尽' if len(r['alts']) < n else '未穷尽'}），其中可排路线 {int(df.routable[1:].sum())} 个")
    print(df.drop(columns=["diff_blocks"]).describe().T.to_string())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
