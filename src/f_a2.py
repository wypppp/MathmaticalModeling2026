"""A 层检查 A2：用出题人给的附件 3（业务人员的真实方案）当裁判，切换时间规则的读法，看哪种读法与表列数据最吻合。

预注册：evidence.md V20（表列天数 < 回放天数的批次能否从 11 降到 ≤ 3）、V21（越窗 16 批是否稳定）。
“表列 < 孤立最少天数”一列是看过 V20 结果后加的检验（按表中顺序回放不是下界，换顺序可能更快），不属于预注册。
只读分析：不改主结果。开关见 f_engine.OPT，默认值 = spec v2.2。
用法：python src/f_a2.py [dur]   → results/F/checks/A2_*.csv（dur：只做表列天数是否沿用提报时长的检查）
"""
from __future__ import annotations

import itertools
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_engine as fe  # noqa: E402
import f_p1  # noqa: E402
import f_p2  # noqa: E402
import f_parse as fp  # noqa: E402
import f_routes as fr  # noqa: E402

OUT = ROOT / "results" / "F" / "checks"
SWITCHES = ["split_legs", "split_long", "no_ceil", "load_anytime", "no_wh_cap"]


def setup():
    """复现 f_p1.main 中“统筹后”方案的构造（指派、出发日、表中仓库顺序），不写任何文件。"""
    cap, D = fp.load_cap(), fp.load_dist()
    B2, K2 = fb.build(2, unit_wh={"U11": "WS"})
    rows3 = f_p1.load3()
    tr, _ = f_p1.trace(K2, rows3)
    b3_to_b2 = {}
    for k in K2:
        if k.id in tr and tr[k.id][2] == "自办":
            b3_to_b2.setdefault(tr[k.id][0], defaultdict(int))[k.batch] += 1
    b3_to_b2 = {b3: max(v, key=v.get) for b3, v in b3_to_b2.items()}
    start3 = {r["batch"]: r["start"] for r in rows3}
    end3 = {r["batch"]: r["end"] for r in rows3}
    order3 = defaultdict(list)
    for r in rows3:
        if r["w"] not in order3[r["batch"]]:
            order3[r["batch"]].append(r["w"])
    assign = {}
    for k in K2:
        b3, u3, how, _ = tr[k.id]
        if how == "自办":
            assign[k.id] = ("own",) if b3_to_b2.get(b3) == k.batch else None
        else:
            beta = b3_to_b2.get(b3)
            opts = [o for o in f_p2.options(k, B2, K2, cap, D) if o[1] == beta and ((o[0] == "REV") == (how == "反转代交"))]
            assign[k.id] = opts[0]
    groups = fr.batch_groups(assign, B2, K2, cap)
    b2_to_b3 = {v: k for k, v in b3_to_b2.items()}
    # 每个附件 3 批次覆盖了哪些附件 2 原批次（自办 + 被代），用于“并集时间窗”读法
    covered = defaultdict(set)
    for k in K2:
        covered[tr[k.id][0]].add(k.batch)
    return dict(cap=cap, D=D, B2=B2, K2=K2, groups=groups, b2_to_b3=b2_to_b3, start3=start3, end3=end3, order3=order3, covered=covered)


def build_plans(S, order_override=None):
    plans = []
    for b, gs in S["groups"].items():
        u = S["B2"][b].unit
        T = fr.batch_T(gs, u)[0]
        b3 = S["b2_to_b3"][b]
        order = (order_override or {}).get(b, S["order3"][b3])
        steps, _ = f_p1.table_order_route(u, T, gs, S["D"], order)
        plans.append(fe.Plan(b, u, S["start3"][b3], T, steps, tuple(fb.H[u])))
    return plans


_ROUTES = {}


def iso_min_days(S, b):
    """该批在 spec S15 路线空间内（任意顺序、途经、留置）孤立执行的最少天数；与表中顺序无关。在当前 fe.OPT 下计算。"""
    gs = S["groups"][b]
    u = S["B2"][b].unit
    T = fr.batch_T(gs, u)[0]
    if b not in _ROUTES:
        _ROUTES[b] = fr.enumerate_routes(u, T, gs, S["D"], max_km=4000)
    st = S["start3"][S["b2_to_b3"][b]]
    taus = [e["tau"] for e in (fr.evaluate(b, u, T, r, S["D"], start_day=st) for r in _ROUTES[b]) if e["ok"]]
    return min(taus) if taus else None


def replay(S, opt):
    saved = dict(fe.OPT)
    fe.OPT.update(opt)
    try:
        res, _ = fe.simulate(build_plans(S), S["D"])
        iso = {b: iso_min_days(S, b) for b in res}
    finally:
        fe.OPT.clear()
        fe.OPT.update(saved)
    rows = []
    for b, r in res.items():
        b3 = S["b2_to_b3"][b]
        tab = S["end3"][b3] - S["start3"][b3] + 1
        last_wh_day = max(lg.depart[0] for lg in r.logs[:-1]) if len(r.logs) > 1 else r.start_day
        rows.append(dict(batch2=b, batch3=b3, tab_days=tab, tau_sim=r.tau, end_sim=r.end_day, end_tab=S["end3"][b3],
                         tau_to_last_wh=last_wh_day - r.start_day + 1, iso_min=iso[b], flags=";".join(r.flags)))
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    S = setup()
    combos = [()] + [(s,) for s in SWITCHES] + list(itertools.combinations(SWITCHES, 2)) + [tuple(SWITCHES)]
    summ, detail = [], []
    for c in combos:
        df = replay(S, {s: True for s in c})
        tag = "+".join(c) or "spec 默认"
        summ.append(dict(读法=tag, 表列少于回放=int((df.tab_days < df.tau_sim).sum()), 表列多于回放=int((df.tab_days > df.tau_sim).sum()),
                         完全相等=int((df.tab_days == df.tau_sim).sum()), 回放总天数=int(df.tau_sim.sum()), 表列总天数=int(df.tab_days.sum()),
                         绝对差之和=int((df.tab_days - df.tau_sim).abs().sum()),
                         表列少于孤立最少天数=int((df.tab_days < df.iso_min).sum()), 孤立最少天数之和=int(df.iso_min.sum()),
                         表列少于回放_回程不计=int((df.tab_days < df.tau_to_last_wh).sum()), 超载批次=int((df["flags"] != "").sum())))
        detail.append(df.assign(读法=tag))
    sdf = pd.DataFrame(summ)
    sdf.to_csv(OUT / "A2_rules.csv", index=False, encoding="utf-8-sig")
    pd.concat(detail).to_csv(OUT / "A2_rules_detail.csv", index=False, encoding="utf-8-sig")
    print(sdf.to_string(index=False))

    # V21：越窗只取决于出发日与时间窗读法，与时间规则无关
    win = []
    for b, gs in S["groups"].items():
        b3 = S["b2_to_b3"][b]
        st, bt = S["start3"][b3], S["B2"][b]
        cov = [S["B2"][x] for x in S["covered"][b3]]
        win.append(dict(batch2=b, batch3=b3, unit=bt.unit, start=st, a=bt.a, e=bt.e,
                        spec_a6=bt.a - 6 <= st <= bt.e, a7=bt.a - 7 <= st <= bt.e, no_early=bt.a <= st <= bt.e,
                        union=any(x.a - 6 <= st <= x.e for x in cov), late_only=st <= bt.e))
    wdf = pd.DataFrame(win)
    wdf.to_csv(OUT / "A2_window.csv", index=False, encoding="utf-8-sig")
    print({c: int((~wdf[c]).sum()) for c in ["spec_a6", "a7", "no_early", "union", "late_only"]}, "（越窗批次数）")

    # 超载：U4 那一批若换一种仓库顺序能否不超载（检验“表中顺序 = 实际路线”这一读法）
    bad = [r for r in detail[0].itertuples() if r.flags]
    for r in bad:
        b, b3 = r.batch2, r.batch3
        ok = []
        for perm in itertools.permutations(S["order3"][b3]):
            res, _ = fe.simulate(build_plans(S, {b: list(perm)}), S["D"])
            ok.append((perm, not res[b].flags, res[b].D))
        print(f"批 {b}（附件3 批 {b3}）表中顺序 {S['order3'][b3]} 超载；各排列：", ok)


def duration_check():
    """区分性检查（看过 V20 结果后加的，不属于预注册）：附件 3 的表列天数是否沿用了附件 2 该批的提报时段长度。
    若是，表列天数不是按时间规则算出来的，对时间规则的哪种读法都不构成证据。读 A2_rules_detail.csv 与 p1/batches_after.csv。"""
    b = pd.read_csv(ROOT / "results/F/p1/batches_after.csv")
    d = pd.read_csv(OUT / "A2_rules_detail.csv")
    x = b[["batch", "batch3", "unit", "a", "e", "start", "tab_days"]].copy()
    x["sub_len"] = x.e - x.a + 1
    x["same_len"] = x.tab_days == x.sub_len
    x["start_eq_a"] = x.start == x.a
    rows = []
    for tag in ("spec 默认", "split_legs"):
        y = d[d["读法"] == tag].set_index("batch3")
        for col, nm in (("tau_sim", "按表中顺序回放"), ("iso_min", "孤立最少天数")):
            bad = x[x.tab_days < x.batch3.map(y[col])]
            rows.append(dict(读法=tag, 口径=nm, 做不到的批数=len(bad), 其中表列天数等于提报时长=int(bad.same_len.sum()), 批次=" ".join(map(str, sorted(bad.batch3)))))
    x.to_csv(OUT / "A2_duration.csv", index=False, encoding="utf-8-sig")
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "A2_duration_summary.csv", index=False, encoding="utf-8-sig")
    print(f"表列天数 = 提报时段长度：{int(x.same_len.sum())}/{len(x)}；出发日 = 提报开始日：{int(x.start_eq_a.sum())}/{len(x)}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dur":
        duration_check()
    else:
        main()
        duration_check()
