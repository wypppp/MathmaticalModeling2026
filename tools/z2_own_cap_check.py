"""裁 Z2（R47）：删去 H13（自用队属仓也计日容量）对现有方案的影响。
问题 3、4：只读 steps 台账，独立重算每个 (仓库, 日) 的台次与单位数（含自用仓）。
若所有 (仓库, 日) 都 ≤ 20 台次、≤ 3 支，则新规则下回放与原回放逐步相同（计数单调，额度从未触发）。
问题 1：引擎开关 own_cap 回放，输出写到 scratch。"""
import sys
from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path(r"d:\WYP\MM2026\MathmaticalModeling2026")
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa

SCR = ROOT / "results/F/checks/z2_p1"
SCR.mkdir(parents=True, exist_ok=True)


def split(sd, sh, c):
    d, h, rem, out = sd, sh, float(c), []
    while rem > 1e-9:
        if h >= 8 - 1e-9:
            d, h = d + 1, 0.0
        do = min(rem, (8 - h) * 2.5)
        out.append((d, do))
        h += do / 2.5
        rem -= do
    return out, (d, h)


def recount(path, tag):
    st = pd.read_csv(path)
    veh, units, own_veh, own_units = defaultdict(float), defaultdict(set), defaultdict(float), defaultdict(set)
    mism = 0
    for r in st.itertuples():
        c = r.c_unload + r.c_load
        if not str(r.node).startswith("W") or c <= 0:
            continue
        pieces, (ed, eh) = split(r.start_day, r.start_h, c)
        if (ed, round(eh, 6)) != (r.end_day, round(r.end_h, 6)) and not (eh >= 8 - 1e-9 and r.end_day == ed + 1 and r.end_h == 0):
            mism += 1
        own = r.node in fb.H[r.unit]
        for d, do in pieces:
            veh[(r.node, d)] += do
            units[(r.node, d)].add(r.unit)
            if own:
                own_veh[(r.node, d)] += do
                own_units[(r.node, d)].add(r.unit)
    over_v = {k: v for k, v in veh.items() if v > 20 + 1e-6}
    over_u = {k: sorted(v) for k, v in units.items() if len(v) > 3}
    shared = {k for k in own_veh if veh[k] - own_veh[k] > 1e-9 or len(units[k] - own_units[k]) > 0 or len(own_units[k]) > 1}
    mx = max(veh.items(), key=lambda kv: kv[1])
    mxu = max(units.items(), key=lambda kv: len(kv[1]))
    print(f"[{tag}] 步数 {len(st)}；按 8 小时窗拆分与台账结束时刻不符 {mism} 步（>0 说明有因额度暂停，需细看）")
    print(f"  含自用仓后 >20 台次的 (仓,日)：{len(over_v)} {over_v}")
    print(f"  含自用仓后 >3 支的 (仓,日)：{len(over_u)} {over_u}")
    print(f"  最大台次 {mx}；最多单位 {mxu[0]} {sorted(mxu[1])}；自用仓与他人同日作业的 (仓,日) {len(shared)} 个")


for tag, p in (("问题3主方案", "p3/steps_main.csv"), ("问题3规则基线", "p3/steps_baseline.csv"), ("问题4主方案", "p4/steps_main.csv")):
    f = ROOT / "results/F" / p
    if f.exists():
        recount(f, tag)

# 问题 1：开关回放
import f_engine as fe  # noqa
import f_p1  # noqa
res = {}
for flag in (False, True):
    fe.OPT["own_cap"] = flag
    f_p1.OUT = SCR / f"p1_owncap_{int(flag)}"
    f_p1.OUT.mkdir(exist_ok=True)
    f_p1.main()
    res[flag] = pd.read_csv(f_p1.OUT / "summary.csv")
fe.OPT["own_cap"] = False
print(pd.concat({"默认": res[False].T, "own_cap": res[True].T}, axis=1).to_string())
for t in ("before", "after"):
    a = pd.read_csv(SCR / "p1_owncap_0" / f"batches_{t}.csv")
    b = pd.read_csv(SCR / "p1_owncap_1" / f"batches_{t}.csv")
    d = a[["batch", "tau_sim", "end_sim"]].merge(b[["batch", "tau_sim", "end_sim"]], on="batch", suffixes=("", "_own"))
    print(t, "天数变化的批次：", d[(d.tau_sim != d.tau_sim_own) | (d.end_sim != d.end_sim_own)].to_dict("records"))
