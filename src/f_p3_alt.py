"""问题 2 并列最优指派下的问题 3（探索，不覆盖主结果）：对 f_p2_alt 找到的替代指派做同样的问题 3 搜索。

用法：python src/f_p3_alt.py <替代解编号 1|2> [d5]（d5：偏离项分母取 5，与主结果每天权重相同；输出加后缀 _d5，不覆盖）
输出：results/F/p2_alt/p3_alt<k>.csv（基线、搜索结果；同时给出按主结果 J1 标尺与按本实例标尺的合成分）、assign_alt<k>.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_p2  # noqa: E402
import f_p3  # noqa: E402
import f_parse as fp  # noqa: E402
from f_run_p2 import solve_checked  # noqa: E402
from f_run_p3 import search  # noqa: E402

OUT = ROOT / "results" / "F" / "p2_alt"


def main(k, d5=False):
    sfx = "_d5" if d5 else ""
    OUT.mkdir(parents=True, exist_ok=True)
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    _, _, forbid = solve_checked(batches, blocks, cap, D)
    r = f_p2.solve(batches, blocks, cap, D, forbid=forbid, alternatives=k)
    assign = r["alts"][k - 1]
    pd.DataFrame([dict(block=b, option=str(o)) for b, o in sorted(assign.items())]).to_csv(OUT / f"assign_alt{k}{sfx}.csv", index=False, encoding="utf-8-sig")
    t0 = time.time()
    inst = f_p3.Instance(assign, batches, blocks, cap, D)
    base = inst.baseline()
    evb = inst.evaluate(base)
    ref_own = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], 5.0 if d5 else evb["delta"]))
    m = pd.read_csv(ROOT / "results" / "F" / "p3" / "ref.csv").iloc[0]
    ref_main = dict(l=(m.l_tau, m.l_L, m.l_delta), u=(m.u_tau, m.u_L, m.u_delta))
    print(f"替代解 {k}：块 43 → {assign[43]}；下界 τ≥{inst.lb_tau} L≥{inst.lb_L:.3f}；基线 {evb['feasible']} τ={evb['tau']} L={evb['L']:.3f} δ={evb['delta']}")
    _, ev1, sol, ev = search(inst, ref_own)
    rows = []
    for name, e in (("下界", None), ("基线", evb), ("搜索", ev)):
        if e is None:
            rows.append(dict(name=name, tau=inst.lb_tau, L=inst.lb_L, delta=0))
            continue
        rows.append(dict(name=name, feasible=e["feasible"], tau=e["tau"], L=e["L"], delta=e["delta"], V=e["V"], D=e["D"],
                         score_own=inst.score(e, ref_own)[0], score_mainref=inst.score(e, ref_main)[0]))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"p3_alt{k}{sfx}.csv", index=False, encoding="utf-8-sig")
    import f_p3_cert2 as c2
    c2.OUT = OUT
    c2.export_candidate(inst, sol, f"alt{k}{sfx}")  # 附件 6、7 格式，供 tools/f_check.py 核验
    print(df.to_string(), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(int(sys.argv[1]), len(sys.argv) > 2 and sys.argv[2] == "d5")
