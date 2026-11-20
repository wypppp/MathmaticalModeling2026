"""问题 4：保留 R25 的指派，在全候选路线集上重做路线与出发日（evidence V35）。

R25 的问题 4 搜索（`f_run_p4.py`，12 次 × 600 s）用的是帕累托剪枝后的候选路线；R31 发现剪枝会漏掉更好的路线。
在全候选集上重做整个改派搜索每步要贵约 9 倍，故这里只固定指派，重做路线与出发日（同问题 3 的 search）。
用法：python src/f_run_p4_reroute.py
输出：覆盖 results/F/p4/summary.csv（第 1 行问题 3 新主结果、第 2 行本方案，其后保留 R25 的 12 个搜索终点）、batches/steps/wh_load_main.csv、
      batch_id_map.csv、问题4_附件6格式.xlsx、问题4_results.xlsx；R25 的旧汇总另存 summary_R25.csv
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_export  # noqa: E402
import f_p2  # noqa: E402
import f_p3  # noqa: E402
import f_p4  # noqa: E402
import f_parse as fp  # noqa: E402
import f_run_p3  # noqa: E402
from f_run_p3 import REF25, load_assign  # noqa: E402

OUT = ROOT / "results" / "F" / "p4"


def main():
    t0 = time.time()
    cap, D = fp.load_cap(), fp.load_dist()
    batches, blocks = fb.build(4)
    a3 = load_assign(ROOT / "results" / "F" / "p2" / "assign_main.csv", blocks)
    a4 = load_assign(OUT / "assign_main.csv", blocks)
    # R25 的问题 4 方案：在剪枝实例上取路线，映射到全候选实例
    old = pd.read_csv(OUT / "batches_main_R25.csv")  # R25 方案的台账（路线编号对应剪枝候选集）；batches_main.csv 已是本脚本的输出
    instp = f_p3.Instance(a4, batches, blocks, cap, D, prune=True)
    inst = f_p3.Instance(a4, batches, blocks, cap, D)
    init = {}
    for r in old.itertuples():
        steps = instp.cands[r.batch][int(r.route)]["steps"]
        idx = [i for i, c in enumerate(inst.cands[r.batch]) if c["steps"] == steps]
        init[r.batch] = (idx[0], int(r.start)) if idx else (inst.base_idx[r.batch], int(r.start))
    ev0 = inst.evaluate(init)
    print(f"R25 问题 4 方案在新规则下：可行={ev0['feasible']} {ev0['viol'][:3]} tau={ev0['tau']} L={ev0['L']:.3f} delta={ev0['delta']} D={ev0['D']}")
    ref = REF25
    _, _, sol, ev = f_run_p3.search(inst, ref, init=init if ev0["feasible"] else None)
    assert ev["feasible"], ev["viol"]
    print("问题 4 重做路线", dict(tau=ev["tau"], L=round(ev["L"], 3), delta=ev["delta"], V=ev["V"], D=ev["D"]), f"{time.time() - t0:.0f}s")
    # 合成分（与 R25 相同的标尺：z3 用 J1，E、W 用 R25 的区间）
    _, tot3, _ = f_p2.summarize(a3, batches, blocks, cap)
    rW = f_p2.solve(batches, blocks, cap, D, fix_batches=tot3["B"], levels=("U9", "W", "A"))
    P = f_p4.P4(batches, blocks, cap, D, tot3["B"], ref, (0.0, tot3["E"]), (rW["stats"]["W"], tot3["pairs"]), u9_min=5)
    s3_df = pd.read_csv(ROOT / "results" / "F" / "p3" / "batches_main.csv")
    inst3 = f_p3.Instance(a3, batches, blocks, cap, D)
    sol3 = {}
    for r in s3_df.itertuples():
        sol3[r.batch] = (int(r.route), int(r.start))
    ev3 = inst3.evaluate(sol3)
    assert ev3["feasible"], "问题 3 台账与当前实例不一致，请先运行 f_run_p3.py"
    sc3, d3 = P.score(a3, ev3)
    sc4, d4 = P.score(a4, ev)
    if (OUT / "summary.csv").exists() and not (OUT / "summary_R25.csv").exists():
        shutil.copy(OUT / "summary.csv", OUT / "summary_R25.csv")
    oldsum = pd.read_csv(OUT / "summary_R25.csv")
    ends = oldsum[oldsum["方案"].str.startswith("搜索终点")].copy()
    ends["方案"] = ends["方案"].str.replace("搜索终点：", "搜索终点（R25，剪枝候选）：", regex=False)
    rows = []
    for nm, dd, s in (("问题3方案", d3, sc3), ("问题4方案（R25 指派，全候选重做路线）", d4, sc4)):
        rows.append(dict(方案=nm, 合成分=s, 调运总批次=dd["B"], 调运总车数=dd["N"], 出动总人数=dd["P"], 代领代交等效车数=dd["A"], 人员调动执行总时间=dd["tau"],
                         开始偏离=dd["delta"], 调运总里程=dd["D"], 载货车辆总行驶距离=dd["L"], 失衡度=dd["E"], 批次仓库对=dd["pairs"], 车公里=dd["veh_km"], V=dd["V"]))
    sdf = pd.concat([pd.DataFrame(rows), ends], ignore_index=True)
    sdf.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(sdf.head(2).T.to_string())
    f_run_p3.OUT = OUT
    f_run_p3.dump("main", inst, sol, ev)
    rws, tot, _ = f_p2.summarize(a4, batches, blocks, cap)
    new_id = f_export.renumber(inst.ids, {b: sol[b][1] for b in inst.ids})
    pd.DataFrame([dict(new_batch=new_id[b], orig_batch=b, unit=batches[b].unit) for b in sorted(inst.ids, key=lambda x: new_id[x])]).to_csv(
        OUT / "batch_id_map.csv", index=False, encoding="utf-8-sig")
    tnp = {x["batch"]: (x["T"], x["N"], x["P"]) for x in rws}
    f_export.write_p2(ROOT / "results" / "F" / "问题4_附件6格式.xlsx", a4, batches, blocks, cap, new_id, tnp)
    f_export.write_p3(ROOT / "results" / "F" / "问题4_results.xlsx", 8, inst, sol, ev, new_id)
    print(f"总用时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
