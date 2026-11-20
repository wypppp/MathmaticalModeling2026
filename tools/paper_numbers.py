"""从结果台账生成论文数字表 paper/numbers.csv（键、值、来源文件、evidence 编号、复核状态）。

论文正文只从这张表取数。每次重跑后重新生成，用 git diff 看哪些数变了。
用法：python tools/paper_numbers.py
"""
import csv
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results" / "F"
sys.stdout.reconfigure(encoding="utf-8")
rows = []

# 复核状态：A = 已由 GPT 对当前版本复核；B = GPT 复核过上一版、当前版只用其脚本或检查器验证；C = 单方结果
STATUS_P1, STATUS_P2, STATUS_P34, STATUS_X = "B", "A", "B", "C"


def put(key, val, src, ev, st, note=""):
    if isinstance(val, float):
        val = round(val, 6)
    rows.append(dict(key=key, value=val, source=src, evidence=ev, status=st, note=note))


p1 = pd.read_csv(R / "p1/summary.csv").set_index("方案")
for col, k in [("批次", "batches"), ("运力合计", "T"), ("总车数_统一口径", "N"), ("总人数_统一口径", "P"), ("批次仓库对", "pairs"),
               ("调运总里程", "D"), ("载货总行驶距离", "L"), ("执行总时间_回放", "tau_replay"), ("开始偏离", "delta"), ("越窗批次数", "out_window")]:
    for tag in ("before", "after"):
        put(f"P1.{tag}.{k}", p1.at[tag, col], "p1/summary.csv", "R10/R25", STATUS_P1)
put("P1.after.A", p1.at["after", "代领代交等效车数"], "p1/summary.csv", "R10", "A")
put("P1.after.E", p1.at["after", "失衡度"], "p1/summary.csv", "R10", "A")
put("P1.after.tau_table", p1.at["after", "执行总时间_表列"], "p1/summary.csv", "R10", "A")
put("P1.after.n_tab_lt_replay", p1.at["after", "表列天数少于回放的批次"], "p1/summary.csv", "R16/R21", "A")
ym = pd.read_csv(R / "p1/y1_model.csv").set_index("方案")
put("P1.model.batches", ym.at["模型最优", "批次"], "p1/y1_model.csv", "R9", "C")
put("P1.model.batches_noR4", ym.at["禁用R4", "批次"], "p1/y1_model.csv", "R9", "C")
dur = pd.read_csv(R / "checks/A2_duration.csv")
put("P1.n_days_eq_submitted", int(dur.same_len.sum()), "checks/A2_duration.csv", "R16/R21", "A", f"共 {len(dur)} 批")

p2 = pd.read_csv(R / "p2/summary.csv").set_index("variant")
for k, col in [("B", "B"), ("N", "N"), ("P", "P"), ("A", "A"), ("pairs", "pairs"), ("E", "E"), ("V0", "V0"), ("U9", "U9_to_U6")]:
    put(f"P2.main.{k}", p2.at["main", col], "p2/summary.csv", "R3/R4", STATUS_P2)
for v in ("noR4", "shared_only", "c6_literal"):
    put(f"P2.{v}.B", p2.at[v, "B"], "p2/summary.csv", "R3/R4", STATUS_P2)
for b in range(32, 46):
    put(f"P2.curve.{b}.A", p2.at[f"curve_B{b}", "A"], "p2/summary.csv", "R3/R4", STATUS_P2)

p3 = pd.read_csv(R / "p3/summary.csv").set_index("name")
for row, tag in [("下界（各批孤立最优）", "lb"), ("基线", "base"), ("主路线（加成对邻域）", "main")]:
    for k, col in [("tau", "tau"), ("L", "L"), ("delta", "delta")]:
        put(f"P3.{tag}.{k}", p3.at[row, col], "p3/summary.csv", "R25", STATUS_P34)
    if tag != "lb":
        put(f"P3.{tag}.D", p3.at[row, "D"], "p3/summary.csv", "R25", STATUS_P34)
        put(f"P3.{tag}.V", p3.at[row, "V"], "p3/summary.csv", "R25", STATUS_P34)

p4 = pd.read_csv(R / "p4/summary.csv")
for i, tag in [(0, "p3"), (1, "main")]:
    r = p4.iloc[i]
    for k, col in [("B", "调运总批次"), ("N", "调运总车数"), ("P", "出动总人数"), ("A", "代领代交等效车数"), ("tau", "人员调动执行总时间"),
                   ("delta", "开始偏离"), ("D", "调运总里程"), ("L", "载货车辆总行驶距离"), ("E", "失衡度"), ("pairs", "批次仓库对"),
                   ("vehkm", "车公里"), ("V", "V"), ("score", "合成分")]:
        put(f"P4.{tag}.{k}", r[col], "p4/summary.csv", "R25", STATUS_P34)
ends = p4[p4["方案"].str.startswith("搜索终点")]["合成分"]
put("P4.search.score_min", float(ends.min()), "p4/summary.csv", "R25", STATUS_P34, f"{len(ends)} 次搜索终点")
put("P4.search.score_max", float(ends.max()), "p4/summary.csv", "R25", STATUS_P34)

ab = pd.read_csv(R / "extra/p3_ablation.csv").set_index("方案")
for row, tag in [("关闭留置", "noleave"), ("关闭途经（每段只走直达）", "nopass"), ("关闭留置和途经", "none"),
                 ("合成方式：先比最差项", "minimax"), ("合成方式：权重 0.4/0.4/0.2", "w442")]:
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离")]:
        put(f"X.ablation.{tag}.{k}", ab.at[row, col], "extra/p3_ablation.csv", "R26", STATUS_X)
put("X.ablation.noearly.feasible", bool(ab.at["不允许提前出发", "可行"]), "extra/p3_ablation.csv", "R26/R25", "A", "GPT 第二批复算给出证明")

rl = pd.read_csv(R / "extra/p3_rules.csv").set_index("读法")
for row, tag in [("spec 默认", "spec"), ("split_long（G6 备选）", "split_long"), ("split_legs（D11 的 b）", "split_legs"),
                 ("load_anytime", "load_anytime"), ("split_long+load_anytime", "long_anytime"), ("split_legs+load_anytime", "legs_anytime")]:
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离")]:
        put(f"X.rules.{tag}.{k}", rl.at[row, col], "extra/p3_rules.csv", "R26", STATUS_X)

pb = pd.read_csv(R / "extra/p4_batches.csv")
pb = pb[pb["方案"] == "联合搜索"].set_index("批次")
for nb in (33, 34):
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离"), ("E", "失衡度"), ("pairs", "批次仓库对"), ("A", "代领代交等效车数")]:
        put(f"X.p4b.{nb}.{k}", pb.at[nb, col], "extra/p4_batches.csv", "R26", STATUS_X)

out = ROOT / "paper" / "numbers.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"写出 {len(rows)} 个数字 → {out.relative_to(ROOT)}")
