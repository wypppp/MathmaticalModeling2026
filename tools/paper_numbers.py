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
STATUS_P1, STATUS_P2, STATUS_P34, STATUS_X = "A", "A", "B", "C"  # spec v2.6：问题 2 的四级目标、3 个并列指派及其 N/P/E/仓库对经 GPT 第六批第 1 项独立确认（R45）；问题 3、4 新版待第六批第 2、3 项


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
put("P1.before.tau_submitted", 122, "review/gpt_v23b/README.md（附件 2 提报时段合计）", "R29", "A")
put("P1.before.n_sub_lt_replay", 15, "review/gpt_v23b/README.md", "R29", "A", "附件 2 提报时长短于按表执行所需天数的批数")
put("P1.n_days_eq_submitted", int(dur.same_len.sum()), "checks/A2_duration.csv", "R16/R21", "A", f"共 {len(dur)} 批")

p2 = pd.read_csv(R / "p2/summary.csv").set_index("variant")
for k, col in [("B", "B"), ("N", "N"), ("P", "P"), ("A", "A"), ("pairs", "pairs"), ("E", "E"), ("V0", "V0"), ("U9", "U9_to_U6")]:
    put(f"P2.main.{k}", p2.at["main", col], "p2/summary.csv", "R3/R4", STATUS_P2)
for v in ("noR4", "shared_only", "c6_literal"):
    put(f"P2.{v}.B", p2.at[v, "B"], "p2/summary.csv", "R3/R4", STATUS_P2)
for b in range(32, 46):
    put(f"P2.curve.{b}.A", p2.at[f"curve_B{b}", "A"], "p2/summary.csv", "R3/R4", STATUS_P2)

p3 = pd.read_csv(R / "p3/summary.csv").set_index("name")
for row, tag in [("下界（各批孤立最优）", "lb"), ("基线", "base"), ("主路线（加多起点与打磨）", "main"), ("消融：剪枝候选（R25 做法）", "pruned")]:
    for k, col in [("tau", "tau"), ("L", "L"), ("delta", "delta")]:
        put(f"P3.{tag}.{k}", p3.at[row, col], "p3/summary.csv", "R38", STATUS_P34)
    if tag != "lb":
        put(f"P3.{tag}.D", p3.at[row, "D"], "p3/summary.csv", "R38", STATUS_P34)
        put(f"P3.{tag}.V", p3.at[row, "V"], "p3/summary.csv", "R38", STATUS_P34)

# spec v2.6 Y1/Y2：问题 2 的并列最优指派与各自的问题 3 结果
t2 = pd.read_csv(R / "p2/ties.csv")
put("P2.ties.n", len(t2), "p2/ties.csv", "R43/R45", STATUS_P2, "四级目标同值的并列最优指派个数（V38；GPT 独立枚举一致）")
for r in t2.itertuples():
    for k in ("N", "P", "E", "pairs"):
        put(f"P2.tie{r.tie}.{k}", getattr(r, k), "p2/ties.csv", "R43/R45", STATUS_P2)
t3 = pd.read_csv(R / "p3/ties.csv")
for r in t3.itertuples():
    for k in ("tau", "L", "delta", "V", "D", "score", "lb_tau", "lb_L", "base_tau", "base_L", "base_delta"):
        put(f"P3.tie{r.tie}.{k}", getattr(r, k), "p3/ties.csv", "R43", STATUS_P34)
put("P3.choice", int(t3[t3.chosen].tie.iloc[0]), "p3/ties.csv", "R43", STATUS_P34, "第 5 级选中的并列指派编号")
rf = pd.read_csv(R / "p3/ref.csv").iloc[0]
for k in ("l_tau", "l_L", "u_tau", "u_L", "u_delta"):
    put(f"P3.ref.{k}", rf[k], "p3/ref.csv", "R43", STATUS_P34, "J1 共用标尺（Y2）")
d2 = pd.read_csv(R / "extra/d2b.csv").set_index("variant")
for k in ("B", "N", "P", "A", "pairs", "E"):
    put(f"X.d2b.{k}", d2.at["near_all", k], "extra/d2b.csv", "R32", STATUS_X, "D2 读法 b：每笔代办另须“就近”")
y1n = pd.read_csv(R / "extra/d2b_y1.csv")
put("X.d2b.y1_not_near", int((~y1n.nearby).sum()), "extra/d2b_y1.csv", "R32", STATUS_X, "附件 3 跨单位转移中不满足“就近”的笔数")
p4 = pd.read_csv(R / "p4/summary.csv")
for i, tag in [(0, "p3"), (1, "main")]:
    r = p4.iloc[i]
    for k, col in [("B", "调运总批次"), ("N", "调运总车数"), ("P", "出动总人数"), ("A", "代领代交等效车数"), ("tau", "人员调动执行总时间"),
                   ("delta", "开始偏离"), ("D", "调运总里程"), ("L", "载货车辆总行驶距离"), ("E", "失衡度"), ("pairs", "批次仓库对"),
                   ("vehkm", "车公里"), ("V", "V"), ("score", "合成分")]:
        put(f"P4.{tag}.{k}", r[col], "p4/summary.csv", "R39", STATUS_P34)
ends = p4[p4["方案"].str.startswith("搜索终点")]["合成分"]
put("P4.search.score_min", float(ends.min()), "p4/summary.csv", "R39", STATUS_P34, f"{len(ends)} 次搜索终点")
put("P4.search.score_max", float(ends.max()), "p4/summary.csv", "R39", STATUS_P34)

gp = pd.read_csv(R / "p3/gap_decomp.csv").set_index("batch")
put("P3.gap.n_both_min", int(((gp.extra_tau == 0) & (gp.extra_L < 1e-6)).sum()), "p3/gap_decomp.csv", "R44", STATUS_P34, "tools/p3_gap.py")
put("P3.gap.extra_tau", int(gp.extra_tau.sum()), "p3/gap_decomp.csv", "R44", STATUS_P34)
put("P3.gap.b7.L_saved", gp.at[7, "L_saved_vs_min_tau_route"], "p3/gap_decomp.csv", "R44", STATUS_P34, "批 7 比其最少天数路线少的载货距离")
put("P3.gap.b13.extra_L", gp.at[13, "extra_L"], "p3/gap_decomp.csv", "R44", STATUS_P34)
put("P3.gap.b13.tau_at_min_L", int(gp.at[13, "tau_at_min_Lbar"]), "p3/gap_decomp.csv", "R44", STATUS_P34)
put("P3.gap.b1_30_32.extra_L", float(gp.loc[[1, 30, 32], "extra_L"].sum()), "p3/gap_decomp.csv", "R44", STATUS_P34)

ab = pd.read_csv(R / "extra/p3_ablation.csv").set_index("方案")
for row, tag in [("关闭留置", "noleave"), ("关闭途经（每段只走直达）", "nopass"), ("关闭留置和途经", "none"), ("不允许提前出发", "noearly"),
                 ("合成方式：先比最差项", "minimax"), ("合成方式：权重 0.4/0.4/0.2", "w442")]:
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离")]:
        put(f"X.ablation.{tag}.{k}", ab.at[row, col], "extra/p3_ablation.csv", "R44", STATUS_X)
via = pd.read_csv(R / "extra/p3_via.csv").iloc[0]
for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离"), ("D", "调运总里程")]:
    put(f"X.via.{k}", via[col], "extra/p3_via.csv", "R44", STATUS_X, "X1 反面：允许经本批次站点中转（v2.6 其余规则）")
put("X.ablation.noearly.feasible", bool(ab.at["不允许提前出发", "可行"]), "extra/p3_ablation.csv", "R44", STATUS_X, "指派 2 下可行；指派 0 下不可行由 GPT 第二批证明（R25）")
put("X.ablation.noleave.lb_tau", ab.at["关闭留置", "孤立下界_天"], "extra/p3_ablation.csv", "R44", STATUS_X)
put("X.ablation.noleave.lb_L", ab.at["关闭留置", "孤立下界_km"], "extra/p3_ablation.csv", "R44", STATUS_X)
put("X.ablation.noleave.D", ab.at["关闭留置", "调运总里程"], "extra/p3_ablation.csv", "R44", STATUS_X)

rl = pd.read_csv(R / "extra/p3_rules.csv").set_index("读法")
for row, tag in [("spec 默认", "spec"), ("split_long（G6 备选）", "split_long"), ("split_legs（D11 的 b）", "split_legs"),
                 ("load_anytime", "load_anytime"), ("split_long+load_anytime", "long_anytime"), ("split_legs+load_anytime", "legs_anytime")]:
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离")]:
        put(f"X.rules.{tag}.{k}", rl.at[row, col], "extra/p3_rules.csv", "R44", STATUS_X)
    put(f"X.rules.{tag}.lb_tau", rl.at[row, "孤立下界_天"], "extra/p3_rules.csv", "R44", STATUS_X)

pb = pd.read_csv(R / "extra/p4_batches.csv")
pb = pb[pb["方案"] == "联合搜索"].set_index("批次")
for nb in (33, 34):
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离"), ("E", "失衡度"), ("pairs", "批次仓库对"), ("A", "代领代交等效车数")]:
        put(f"X.p4b.{nb}.{k}", pb.at[nb, col], "extra/p4_batches.csv", "R44", STATUS_X)

sn = pd.read_csv(R / "extra/sens.csv").set_index("方案")
for row, tag in [("G1 保障车分界 T≥26（问题2/3 指派）", "G1.p2"), ("G1 保障车分界 T≥26（问题4 指派）", "G1.p4")]:
    put(f"X.sens.{tag}.N", sn.at[row, "总车数"], "extra/sens.csv", "R44", STATUS_X)
    put(f"X.sens.{tag}.P", sn.at[row, "总人数"], "extra/sens.csv", "R44", STATUS_X)
for row, tag in [("G2 里程上限 2200 km", "G2_2200"), ("G2 里程上限 2500 km", "G2_2500"), ("G7 装卸不取整", "G7"), ("G8 下的问题 3", "G8.p3"), ("G14 留置不受等待限制", "G14")]:
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离")]:
        put(f"X.sens.{tag}.{k}", sn.at[row, col], "extra/sens.csv", "R44", STATUS_X)
g8 = "G8 问题2 要求双方时段相容（V⁰ 优先）"
for k, col in [("B", "批次"), ("A", "代领代交等效车数"), ("N", "总车数"), ("P", "总人数")]:
    put(f"X.sens.G8.p2.{k}", sn.at[g8, col], "extra/sens.csv", "R44", STATUS_X)
put("X.sens.G16.feasible", bool(sn.at["G16 每个外部仓库只到访一次", "可行"]), "extra/sens.csv", "R44", STATUS_X, str(sn.at["G16 每个外部仓库只到访一次", "说明"]))

r3 = pd.read_csv(R / "extra/r3_study.csv").set_index("项目")
for row, k in [("问题4方案：代领③的块数", "p4.n"), ("问题4方案：自取货量（按货主车型的等效车数）", "p4.s"), ("问题4方案：自取往返里程（每个货主-仓库对计一次往返，km）", "p4.km"),
               ("禁用③：问题 2 最少批次", "noR3.p2.B"), ("禁用③：问题 3（天/载货距离/偏离/里程）", "noR3.p3"),
               ("禁用③：问题 4（批次/天/载货距离/偏离/失衡度/仓库对/代领代交/里程）", "noR3.p4")]:
    put(f"X.r3.{k}", r3.at[row, "值"], "extra/r3_study.csv", "R44", "A" if k == "noR3.p2.B" else STATUS_X)

pr = pd.read_csv(R / "extra/p4_rules.csv")
for i, tag in [(0, "p3"), (1, "p4")]:
    for k, col in [("tau", "执行总时间"), ("L", "载货总行驶距离"), ("delta", "开始偏离"), ("E", "失衡度"), ("pairs", "批次仓库对"), ("A", "代领代交等效车数")]:
        put(f"X.p4rules.{tag}.{k}", pr.iloc[i][col], "extra/p4_rules.csv", "R44", STATUS_X)

sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
for tag in ("p3", "p4"):
    st = pd.read_csv(R / f"{tag}/steps_main.csv")
    st = st[st.node.str.startswith("W")]
    st = st[[n not in fb.H[u] for n, u in zip(st.node, st.unit)]]
    put(f"{tag.upper()}.arrivals_ext", len(st), f"{tag}/steps_main.csv", "R38/R39", STATUS_P34, "到达 H(x) 以外仓库的总次数（含重复到访）")
    b = pd.read_csv(R / f"{tag}/batches_main.csv")
    put(f"{tag.upper()}.n_leave_batches", int((b.n_leave > 0).sum()), f"{tag}/batches_main.csv", "R38/R39", STATUS_P34)
    put(f"{tag.upper()}.n_pass_batches", int((b.n_pass > 0).sum()), f"{tag}/batches_main.csv", "R38/R39", STATUS_P34)
b3 = pd.read_csv(R / "p3/batches_main.csv")
put("P3.n_both_iso_opt", int(((b3.tau == b3.min_iso_tau) & ((b3.Lbar - b3.min_Lbar).abs() < 1e-6)).sum()), "p3/batches_main.csv", "R38", STATUS_P34, "同时达到孤立最少天数与最小载货距离的批次")
put("P3.n_cands", int(b3.n_cands.sum()), "p3/batches_main.csv", "R38", STATUS_P34)

for tag, path in (("P2", "p2/assign_main.csv"), ("P4", "p4/assign_main.csv")):
    a = pd.read_csv(R / path)
    t = a[a.option != "own"]
    put(f"{tag}.n_delegated", len(t), path, "R25", "A" if tag == "P2" else STATUS_P34)
    for c, n in t.case.value_counts().items():
        put(f"{tag}.case.{c}", int(n), path, "R25", "A" if tag == "P2" else STATUS_P34)
    put(f"{tag}.n_removed_batches", len(set(a.batch)) - len(set(a[a.option == "own"].batch)), path, "R25", "A" if tag == "P2" else STATUS_P34)
a4 = pd.read_csv(R / "p4/assign_main.csv")
put("P4.n_changed_vs_p3", int(a4.changed_vs_p3.sum()), "p4/assign_main.csv", "R38", STATUS_P34)
tr = pd.read_csv(R / "p1/trace.csv")
put("P1.n_blocks", len(tr), "p1/trace.csv", "R10", "A")
for h, n in tr.how.value_counts().items():
    put(f"P1.how.{h}", int(n), "p1/trace.csv", "R10", "A")
for c, n in tr[tr.how != "自办"].case.value_counts().items():
    put(f"P1.case.{c}", int(n), "p1/trace.csv", "R10", "A")
put("P1.table.N_before_after", "363→374", "R1（附件 2、3 表列合计）", "R1", "A")
put("P1.table.P_before_after", "962→963", "R1（附件 2、3 表列合计）", "R1", "A")
put("P2.n_options", 197, "f_p2.options 计数（本脚本外算得，2026-11-20）", "R27", STATUS_P2)

out = ROOT / "paper" / "numbers.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"写出 {len(rows)} 个数字 → {out.relative_to(ROOT)}")
