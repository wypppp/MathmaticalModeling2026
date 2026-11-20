"""补充实验：问题 3 的消融与合成方式敏感性；代领③的对照与自取量；问题 4 的批次数折衷；口径灵敏度。

用法：python src/f_run_extra.py [p3|r3|p4b|rules|p4rules|sens|all]
输出：results/F/extra/*.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_engine as fe  # noqa: E402
import f_p2  # noqa: E402
import f_p3  # noqa: E402
import f_p4  # noqa: E402
import f_parse as fp  # noqa: E402
from f_run_p3 import load_assign  # noqa: E402

OUT = ROOT / "results" / "F" / "extra"
cap, D = fp.load_cap(), fp.load_dist()
batches, blocks = fb.build(4)
a3 = load_assign(ROOT / "results" / "F" / "p2" / "assign_main.csv", blocks)


def run3(assign, **kw):
    inst = f_p3.Instance(assign, batches, blocks, cap, D, **kw)
    if not inst.routable:
        return None
    base = inst.baseline()
    evb = inst.evaluate(base)
    return inst, base, evb


def p3_ablation():
    inst, base, evb = run3(a3)
    ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
    rows = []

    def solve(tag, **kw):
        r = run3(a3, **kw)
        if r is None:
            rows.append(dict(方案=tag, 可行=False))
            return
        ins, b, eb = r
        start = b if eb["feasible"] else None
        if start is None:
            rows.append(dict(方案=tag, 可行=False, 说明="基线规则排不出"))
            return
        sol, _ = ins.improve(start, ref)
        ev = ins.evaluate(sol)
        z = sum((ev[k] - l) / ((u - l) if u - l > 1e-9 else 1) for k, l, u in zip(("tau", "L", "delta"), ref["l"], ref["u"]))
        rows.append(dict(方案=tag, 可行=ev["feasible"], 执行总时间=ev["tau"], 载货总行驶距离=ev["L"], 开始偏离=ev["delta"], 调运总里程=ev["D"], 车公里=ev["veh_km"],
                         V=ev["V"], 等权合成分=z, 留置批次=sum(ins.cands[x][sol[x][0]]["n_leave"] > 0 for x in ins.ids),
                         途经批次=sum(ins.cands[x][sol[x][0]]["n_noop"] > 0 for x in ins.ids), 孤立下界_天=ins.lb_tau, 孤立下界_km=ins.lb_L))
        print(rows[-1])

    solve("主路线（全部开启）")
    solve("关闭留置", cand_filter=lambda e: e["n_leave"] == 0)
    solve("关闭途经（每段只走直达）", cand_filter=lambda e: e["n_noop"] == 0)
    solve("关闭留置和途经", cand_filter=lambda e: e["n_leave"] == 0 and e["n_noop"] == 0)
    solve("不允许提前出发", early=0)
    solve("合成方式：先比最差项", agg="minimax")
    solve("合成方式：权重 0.4/0.4/0.2", agg=(0.4, 0.4, 0.2))
    pd.DataFrame(rows).to_csv(OUT / "p3_ablation.csv", index=False, encoding="utf-8-sig")


def r3_study():
    rows = []
    # 自取量：问题 3、问题 4 主方案
    for tag, path in (("问题3方案", ROOT / "results/F/p2/assign_main.csv"), ("问题4方案", ROOT / "results/F/p4/assign_main.csv")):
        a = load_assign(path, blocks)
        n = s = km = 0.0
        for k in blocks:
            o = a[k.id]
            if o[0] == "T" and o[2] == "R3":
                n += 1
                s += k.s(cap, k.owner)
                km += 0  # 往返里程按 (货主, 仓库) 去重后另计
        trips = {(blocks[kid].owner, o[3]) for kid, o in a.items() if o[0] == "T" and o[2] == "R3"}
        km = sum(2 * float(D.at[u, h]) for u, h in trips)
        rows.append(dict(项目=tag + "：代领③的块数", 值=n))
        rows.append(dict(项目=tag + "：自取货量（按货主车型的等效车数）", 值=s))
        rows.append(dict(项目=tag + "：自取往返里程（每个货主-仓库对计一次往返，km）", 值=km))
        rows.append(dict(项目=tag + "：自取的货主-仓库对", 值=";".join(f"{u}-{h}" for u, h in sorted(trips))))
    # 禁用③的问题 2
    r = f_p2.solve(batches, blocks, cap, D, allow_R3=False)
    _, tot, _ = f_p2.summarize(r["assign"], batches, blocks, cap)
    rows.append(dict(项目="禁用③：问题 2 最少批次", 值=tot["B"]))
    rows.append(dict(项目="禁用③：问题 2 代领代交等效车数", 值=tot["A"]))
    rows.append(dict(项目="禁用③：问题 2 总车数/总人数/仓库对", 值=f"{tot['N']}/{tot['P']}/{tot['pairs']}"))
    aN = r["assign"]
    # 禁用③的问题 3、问题 4（同一套标尺）
    inst0, base0, evb0 = run3(a3)
    ref = dict(l=(inst0.lb_tau, inst0.lb_L, 0.0), u=(evb0["tau"], evb0["L"], evb0["delta"]))
    instN = f_p3.Instance(aN, batches, blocks, cap, D)
    bN = instN.baseline()
    solN, _ = instN.improve(bN, ref)
    evN = instN.evaluate(solN)
    rows.append(dict(项目="禁用③：问题 3（天/载货距离/偏离/里程）", 值=f"{evN['tau']}/{evN['L']:.3f}/{evN['delta']}/{evN['D']:.0f}", 可行=evN["feasible"]))
    _, tot3, _ = f_p2.summarize(a3, batches, blocks, cap)
    rW = f_p2.solve(batches, blocks, cap, D, fix_batches=tot["B"], levels=("U9", "W", "A"), allow_R3=False)
    P = f_p4.P4(batches, blocks, cap, D, tot["B"], ref, (0.0, tot3["E"]), (42, tot3["pairs"]), u9_min=5, log=lambda *x: None, allow_R3=False)
    best = None
    for sd in range(6):
        a, sol, inst, sc, hist = P.search(aN, solN, seed=sd, time_limit=600)
        if best is None or sc < best[0]:
            best = (sc, a, sol, inst)
    sc, a, sol, inst = best
    ev = inst.evaluate(sol)
    _, det = P.score(a, ev)
    rows.append(dict(项目="禁用③：问题 4（批次/天/载货距离/偏离/失衡度/仓库对/代领代交/里程）",
                     值=f"{det['B']}/{det['tau']}/{det['L']:.3f}/{det['delta']}/{det['E']:.4f}/{det['pairs']}/{det['A']:.3f}/{det['D']:.0f}", 可行=ev["feasible"]))
    rows.append(dict(项目="禁用③：该批次数下仓库对最小值", 值=rW["stats"]["W"]))
    pd.DataFrame(rows).to_csv(OUT / "r3_study.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(rows).to_string(index=False))


def p4_batches():
    """问题 4 的批次数折衷：32（主）、33、34 批；每个批次数从“该批次数下代领代交最少”的指派出发搜索。"""
    inst0, base0, evb0 = run3(a3)
    ref = dict(l=(inst0.lb_tau, inst0.lb_L, 0.0), u=(evb0["tau"], evb0["L"], evb0["delta"]))
    _, tot3, _ = f_p2.summarize(a3, batches, blocks, cap)
    rows = []
    for nb in (33, 34):
        r = f_p2.solve(batches, blocks, cap, D, fix_batches=nb, levels=("U9", "A", "V0"))
        a0 = r["assign"]
        ins = f_p3.Instance(a0, batches, blocks, cap, D)
        s0 = ins.baseline()
        if not ins.evaluate(s0)["feasible"]:
            rows.append(dict(批次=nb, 说明="起点排不出"))
            continue
        s0, _ = ins.improve(s0, ref)
        e0 = ins.evaluate(s0)
        _, t0, _ = f_p2.summarize(a0, batches, blocks, cap)
        rows.append(dict(批次=nb, 方案="先指派后排程（代领代交最少）", 执行总时间=e0["tau"], 载货总行驶距离=e0["L"], 开始偏离=e0["delta"], 失衡度=t0["E"], 批次仓库对=t0["pairs"],
                         代领代交等效车数=t0["A"], 总车数=t0["N"], 总人数=t0["P"], 调运总里程=e0["D"], 车公里=e0["veh_km"], V=e0["V"]))
        P = f_p4.P4(batches, blocks, cap, D, nb, ref, (0.0, tot3["E"]), (42, tot3["pairs"]), u9_min=5, log=lambda *x: None)
        best = None
        for sd in range(6):
            a, sol, inst, sc, hist = P.search(a0, s0, seed=sd, time_limit=600)
            if best is None or sc < best[0]:
                best = (sc, a, sol, inst)
        sc, a, sol, inst = best
        ev = inst.evaluate(sol)
        _, det = P.score(a, ev)
        rows.append(dict(批次=nb, 方案="联合搜索", 合成分=sc, 执行总时间=det["tau"], 载货总行驶距离=det["L"], 开始偏离=det["delta"], 失衡度=det["E"], 批次仓库对=det["pairs"],
                         代领代交等效车数=det["A"], 总车数=det["N"], 总人数=det["P"], 调运总里程=det["D"], 车公里=det["veh_km"], V=det["V"]))
        print(rows[-2], rows[-1], sep="\n")
    pd.DataFrame(rows).to_csv(OUT / "p4_batches.csv", index=False, encoding="utf-8-sig")


def p3_rules():
    """A2 的后续：时间规则换成备选读法后，问题 3（同一指派）重新搜索的结果。只读分析，不改主结果。"""
    rows = []
    for tag, opt in (("spec 默认", {}), ("split_long（G6 备选）", dict(split_long=True)), ("split_legs（D11 的 b）", dict(split_legs=True)),
                     ("load_anytime", dict(load_anytime=True)), ("split_long+load_anytime", dict(split_long=True, load_anytime=True)),
                     ("split_legs+load_anytime", dict(split_legs=True, load_anytime=True))):
        saved = dict(fe.OPT)
        fe.OPT.update(opt)
        try:
            inst, base, evb = run3(a3)
            ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
            sol, _ = inst.improve(base, ref)
            ev = inst.evaluate(sol)
        finally:
            fe.OPT.clear()
            fe.OPT.update(saved)
        rows.append(dict(读法=tag, 可行=ev["feasible"], 执行总时间=ev["tau"], 载货总行驶距离=ev["L"], 开始偏离=ev["delta"], 调运总里程=ev["D"], V=ev["V"],
                         基线_天=evb["tau"], 基线_km=evb["L"], 基线_偏离=evb["delta"], 孤立下界_天=inst.lb_tau, 孤立下界_km=inst.lb_L))
        print(rows[-1])
    pd.DataFrame(rows).to_csv(OUT / "p3_rules.csv", index=False, encoding="utf-8-sig")


def p4_rules(opt=None):
    """T3：在备选时间规则（默认 split_legs）下，按 f_run_p4 的同一流程重做问题 3 方案与问题 4 搜索，检验“问题 4 优于问题 3”是否保持。只读分析。"""
    opt = opt or dict(split_legs=True)
    saved = dict(fe.OPT)
    fe.OPT.update(opt)
    try:
        inst3, base, evb = run3(a3)
        ref3 = dict(l=(inst3.lb_tau, inst3.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
        sol3, _ = inst3.improve(base, ref3)
        ev3 = inst3.evaluate(sol3)
        _, tot3, _ = f_p2.summarize(a3, batches, blocks, cap)
        nB = tot3["B"]
        rW = f_p2.solve(batches, blocks, cap, D, fix_batches=nB, levels=("U9", "W", "A"))
        P = f_p4.P4(batches, blocks, cap, D, nB, ref3, (0.0, tot3["E"]), (rW["stats"]["W"], tot3["pairs"]), u9_min=5, log=lambda *x: None)
        runs = []
        for sd in range(6):
            a, sol, inst, sc, _ = P.search(a3, sol3, seed=sd, time_limit=600)
            runs.append((f"自问题3出发/种子{sd}", a, sol, inst, sc))
        aW = rW["assign"]
        instW = P.instance(aW)
        if instW.routable:
            sW = instW.baseline()
            if instW.evaluate(sW)["feasible"]:
                sW, _ = instW.improve(sW, ref3)
                for sd in range(6):
                    a, sol, inst, sc, _ = P.search(aW, sW, seed=sd, time_limit=600)
                    runs.append((f"自仓库对最少解出发/种子{sd}", a, sol, inst, sc))
        name, a, sol, inst, sc = min(runs, key=lambda r: r[4])
        sol, _ = inst.improve(sol, ref3)
        ev = inst.evaluate(sol)
        sc, det = P.score(a, ev)
        s3, d3 = P.score(a3, ev3)
        rows = []
        for nm, dd, z in (("问题3方案", d3, s3), ("问题4方案（" + name + "）", det, sc)):
            rows.append(dict(读法="+".join(opt), 方案=nm, 合成分=z, 调运总批次=dd["B"], 总车数=dd["N"], 总人数=dd["P"], 代领代交等效车数=dd["A"], 执行总时间=dd["tau"],
                             开始偏离=dd["delta"], 调运总里程=dd["D"], 载货总行驶距离=dd["L"], 失衡度=dd["E"], 批次仓库对=dd["pairs"], 可行=ev["feasible"] and P.static_ok(a)))
        for nm, a_, sol_, inst_, z in runs:
            _, dd = P.score(a_, inst_.evaluate(sol_))
            rows.append(dict(读法="+".join(opt), 方案="搜索终点：" + nm, 合成分=z, 执行总时间=dd["tau"], 载货总行驶距离=dd["L"], 开始偏离=dd["delta"], 失衡度=dd["E"], 批次仓库对=dd["pairs"]))
    finally:
        fe.OPT.clear()
        fe.OPT.update(saved)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "p4_rules.csv", index=False, encoding="utf-8-sig")
    print(df.to_string(index=False))


def s12_ok(e):
    """S12：自有送交货（从执行单位可用的队属仓库装、送到外面）必须在到访任何外部仓库作业之前装车。"""
    steps = e["steps"]
    u = steps[-1].node
    own = set(fb.H[u])
    first_ext = next((i for i, st in enumerate(steps) if st.node.startswith("W") and st.node not in own and (st.load or st.unload)), None)
    if first_ext is None:
        return True
    for i, st in enumerate(steps):
        for g in st.load:
            a, z = str(g).split(">")[:2]
            z = z.split("#")[0]
            if a in own and z not in own and i > first_ext:
                return False
    return True


def p3_s12():
    """Gemini A5 第 3 轮：路线枚举未执行 S12。在同一指派下只保留满足 S12 的路线，重做问题 3，量化影响。只读分析。"""
    rows = []
    for tag, flt, r4 in (("现行（未执行 S12）", None, "phys"), ("执行 S12", s12_ok, "phys"), ("D15 整批先后", None, "batch"), ("执行 S12 + D15 整批先后", s12_ok, "batch")):
        f_p3.R4_RULE = r4
        inst = f_p3.Instance(a3, batches, blocks, cap, D, cand_filter=flt)
        if not inst.routable:
            bad = [b for b in inst.ids if not inst.cands[b]]
            rows.append(dict(方案=tag, 可行=False, 排不出的批次=" ".join(map(str, bad))))
            print(rows[-1])
            continue
        base = inst.baseline()
        evb = inst.evaluate(base)
        ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
        sol, _ = inst.improve(base, ref)
        ev = inst.evaluate(sol)
        rows.append(dict(方案=tag, 可行=ev["feasible"], 执行总时间=ev["tau"], 载货总行驶距离=ev["L"], 开始偏离=ev["delta"], 调运总里程=ev["D"], V=ev["V"],
                         基线_天=evb["tau"], 基线_km=evb["L"], 基线_偏离=evb["delta"], 孤立下界_天=inst.lb_tau, 孤立下界_km=inst.lb_L,
                         最长批里程=max(min(c["D"] for c in inst.cands[b]) for b in inst.ids)))
        print(rows[-1])
    f_p3.R4_RULE = "phys"
    pd.DataFrame(rows).to_csv(OUT / "p3_s12.csv", index=False, encoding="utf-8-sig")


def _p3_once(assign, tag, cand_filter=None):
    inst = f_p3.Instance(assign, batches, blocks, cap, D, cand_filter=cand_filter)
    if not inst.routable:
        return dict(方案=tag, 可行=False, 说明="有批次无合规路线：" + " ".join(str(b) for b in inst.ids if not inst.cands[b]))
    base = inst.baseline()
    evb = inst.evaluate(base)
    if not evb["feasible"]:
        return dict(方案=tag, 可行=False, 说明="基线排不出")
    ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(evb["tau"], evb["L"], evb["delta"]))
    sol, _ = inst.improve(base, ref)
    ev = inst.evaluate(sol)
    return dict(方案=tag, 可行=ev["feasible"], 执行总时间=ev["tau"], 载货总行驶距离=ev["L"], 开始偏离=ev["delta"], 调运总里程=ev["D"],
                基线_天=evb["tau"], 基线_km=evb["L"], 孤立下界_天=inst.lb_tau, 孤立下界_km=inst.lb_L)


def once_per_stop(e):
    """G16 敏感性：每个外部仓库只到访一次。驻地和自己的队属仓库可以重复（S12 要求出发先装、返程再卸，队属仓库必到两次）。"""
    u = e["steps"][-1].node
    ext = [st.node for st in e["steps"][:-1] if st.node.startswith("W") and st.node not in fb.H[u]]
    return len(ext) == len(set(ext))


def sens():
    """spec §6 标“做”的口径敏感性：G1、G2、G7、G8、G14、G16。只读分析，主结果不变。"""
    import math
    import f_engine as fe_
    import f_routes as fr_
    rows = []
    # G1：保障车分界改为 T ≥ 26 取 2 台（只影响车数、人数）
    for tag, path in (("问题2/3 指派", ROOT / "results/F/p2/assign_main.csv"), ("问题4 指派", ROOT / "results/F/p4/assign_main.csv")):
        a = load_assign(path, blocks)
        rs, tot, _ = f_p2.summarize(a, batches, blocks, cap)
        N = sum(r["T"] + 1 + (1 if r["T"] <= 25 else 2) + min(2, math.ceil(r["T"] / 10)) for r in rs)
        P = sum(2 * (r["T"] + 1 + (1 if r["T"] <= 25 else 2) + min(2, math.ceil(r["T"] / 10))) + 3 + 2 * math.ceil(r["T"] / 5) for r in rs)
        rows.append(dict(方案=f"G1 保障车分界 T≥26（{tag}）", 可行=True, 总车数=N, 总人数=P, 原总车数=tot["N"], 原总人数=tot["P"]))
        print(rows[-1])
    # G2：里程上限 2200、2500 km（问题 2 的里程割在主方案中没有起作用，只影响问题 3 的路线空间）
    for km in (2200.0, 2500.0):
        old = fr_.MAX_KM
        fr_.MAX_KM = km
        try:
            rows.append(_p3_once(a3, f"G2 里程上限 {km:.0f} km"))
        finally:
            fr_.MAX_KM = old
        print(rows[-1])
    # G7：装卸用时不取整
    fe_.OPT["no_ceil"] = True
    try:
        rows.append(_p3_once(a3, "G7 装卸不取整"))
    finally:
        fe_.OPT["no_ceil"] = False
    print(rows[-1])
    # G8：问题 2 要求代领代交双方的允许出发区间相交（V⁰ 放到批次数之前）
    r = f_p2.solve(batches, blocks, cap, D, levels=("U9", "V0", "B", "A"))
    _, tot8, _ = f_p2.summarize(r["assign"], batches, blocks, cap)
    rows.append(dict(方案="G8 问题2 要求双方时段相容（V⁰ 优先）", 可行=True, 批次=tot8["B"], 代领代交等效车数=tot8["A"], 总车数=tot8["N"], 总人数=tot8["P"],
                     V0=r["stats"].get("V0")))
    print(rows[-1])
    rows.append(_p3_once(r["assign"], "G8 下的问题 3"))
    print(rows[-1])
    # G14：留置不受“等待 1 天”限制
    fr_.LEAVE_WAIT_LIMIT = False
    try:
        rows.append(_p3_once(a3, "G14 留置不受等待限制"))
    finally:
        fr_.LEAVE_WAIT_LIMIT = True
    print(rows[-1])
    # G16：每站只到访一次
    rows.append(_p3_once(a3, "G16 每个外部仓库只到访一次", once_per_stop))
    print(rows[-1])
    pd.DataFrame(rows).to_csv(OUT / "sens.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    if what in ("p3", "all"):
        p3_ablation()
    if what in ("r3", "all"):
        r3_study()
    if what in ("p4b", "all"):
        p4_batches()
    if what in ("rules", "all"):
        p3_rules()
    if what in ("sens", "all"):
        sens()
    if what == "s12":
        p3_s12()
    if what in ("p4rules", "all"):
        p4_rules()
    print(f"用时 {time.time() - t0:.0f}s")
