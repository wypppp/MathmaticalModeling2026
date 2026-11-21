"""F 题问题 1：附件 2 → 附件 3 的逐块追溯、情形判定、统一口径指标与回放。

用法：python src/f_p1.py
输出 results/F/p1/：trace.csv（每个原始需求块由谁执行、属于哪种情形）、batches_{before,after}.csv、summary.csv、y1_model.csv
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_engine as fe  # noqa: E402
import f_p2  # noqa: E402
import f_parse as fp  # noqa: E402
import f_routes as fr  # noqa: E402

OUT = ROOT / "results" / "F" / "p1"


def load3():
    """附件 3 的货物行：(批次, 执行单位, 外部节点, 方向(执行单位视角), 货物, 数量, 备注, 行号)。"""
    df = fp.load(3)
    df = df[~df.is_sub].copy()
    rows = []
    for r in df.itertuples():
        u = r.unit
        if r.dst_node == u:
            d_, w = "领", r.src_node
        else:
            d_, w = "交", r.dst_node
        rows.append(dict(batch=int(r.batch), unit=u, w=w, dir=d_, item=r.item, qty=float(r.qty),
                         remark="" if pd.isna(r.remark) else str(r.remark), row=r.row, start=fb.day(eval(str(r.start))), end=fb.day(eval(str(r.end)))))
    return rows


def trace(blocks2, rows3):
    """把附件 2 的每个块对应到附件 3 的执行批次。返回 {块id: (批次3, 执行单位, 方式)}，以及未用完的附件 3 余量。"""
    pool = defaultdict(list)
    for r in rows3:
        pool[(r["w"], r["dir"], r["item"])].append(dict(r, left=r["qty"]))

    def take(key, qty, prefer_unit):
        got = defaultdict(float)
        ents = [e for e in pool.get(key, []) if prefer_unit is None or e["unit"] == prefer_unit]
        ents = sorted(ents, key=lambda e: e["left"] < qty - 1e-9)
        need = qty
        for e in ents:
            if need <= 1e-9:
                break
            t = min(e["left"], need)
            if t > 1e-9:
                e["left"] -= t
                need -= t
                got[(e["batch"], e["unit"])] += t
        return got, need

    res = {}
    # 先配自办（同单位），再配被代的，避免把代领的行抢走
    for own_first in (True, False):
        for k in blocks2:
            if k.id in res:
                continue
            keys = [(k.w, k.dir)]
            if k.inner and k.dir == "领":
                keys.append((k.h, "交"))  # 内部互转被反转成代交：货送到收方的仓库
            for w, d_ in keys:
                if own_first and not all(sum(e["left"] for e in pool.get((w, d_, it), []) if e["unit"] == k.owner) >= q - 1e-9 for it, q in k.items.items()):
                    continue
                snap = [(e, e["left"]) for it in k.items for e in pool.get((w, d_, it), [])]
                execs, miss = defaultdict(float), 0.0
                for it, q in k.items.items():
                    got, need = take((w, d_, it), q, k.owner if own_first else None)
                    miss += need
                    for kk, v in got.items():
                        execs[kk] += v
                if miss > 1e-6 or (own_first and any(u != k.owner for _, u in execs)):
                    for e, v in snap:
                        e["left"] = v
                    continue
                b3, u3 = max(execs, key=execs.get)
                res[k.id] = (b3, u3, "自办" if u3 == k.owner else ("反转代交" if (w, d_) != (k.w, k.dir) else ("代领" if k.dir == "领" else "代交")), len(execs))
                break
    left = sum(e["left"] for es in pool.values() for e in es)
    return res, left


def table_order_route(unit, T, groups, D, order):
    """录4.3 的口径：按表中仓库顺序、统一行动。确定性构造，不做优化、不检查车上装载量（超载由引擎记录为发现）。
    驻地 → [有自有送交货或专程取货点：先去装] → 表中各目标仓库（到站先卸后装）→ 剩余卸货点（表中未规定次序，取里程最短的排列）→ 驻地。
    返回 (steps, 卸货点次序是否唯一, 另一种次序下的里程或 None)。"""
    import itertools
    order = [w for i, w in enumerate(order) if w not in order[:i]]
    own = set(fb.H[unit])
    gs = list(groups.values())
    pre = []
    for g in gs:  # 需要在到达目标仓库之前装车的点：自己的队属仓库（送交货）或专程取货的仓库
        if g.load not in order and g.load not in pre:
            pre.append(g.load)
    steps, loaded, done = [], set(), set()

    def visit(n):
        un = {g.gid: g.s for g in gs if g.gid in loaded and g.gid not in done and g.unload == n}
        ld = {g.gid: g.s for g in gs if g.gid not in loaded and g.load == n}
        done.update(un)
        loaded.update(ld)
        steps.append(fe.Step(n, unload=un, load=ld))

    for n in pre + order:
        visit(n)
    rest = []
    for g in gs:
        if g.gid not in done and g.unload not in rest:
            rest.append(g.unload)
    last = steps[-1].node if steps else unit

    def length(perm):
        seq = [last] + list(perm) + [unit]
        return sum(float(D.at[a, b]) for a, b in zip(seq, seq[1:]) if a != b)

    perms = sorted(itertools.permutations(rest), key=length)
    for n in perms[0]:
        visit(n)
    steps.append(fe.Step(unit))
    alt = length(perms[-1]) - length(perms[0]) if len(perms) > 1 else 0.0
    return steps, alt


def plan_metrics(tag, assign, batches, blocks, cap, D, start_of, order_of):
    """对一个指派（before：全部自办；after：按追溯结果）回放并汇总。"""
    groups = fr.batch_groups(assign, batches, blocks, cap)
    rows_s, tot, flow = f_p2.summarize(assign, batches, blocks, cap)
    plans, meta = [], {}
    for b, gs in groups.items():
        u = batches[b].unit
        T = fr.batch_T(gs, u)[0]
        steps, alt = table_order_route(u, T, gs, D, order_of[b])
        plans.append(fe.Plan(b, u, start_of[b], T, steps, tuple(fb.H[u])))
        meta[b] = (T, alt, " → ".join([u] + [s.node for s in steps]))
    res, whs = fe.simulate(plans, D)
    out = []
    srow = {x["batch"]: x for x in rows_s}
    for b in sorted(groups):
        r, bt = res[b], batches[b]
        lo, hi = max(1, bt.a - 6), bt.e
        out.append(dict(batch=b, unit=bt.unit, T=srow[b]["T"], N=srow[b]["N"], P=srow[b]["P"], N_tab=bt.N0, P_tab=bt.P0, targets=srow[b]["targets"],
                        n_targets=srow[b]["n_targets"], a=bt.a, e=bt.e, start=start_of[b], end_sim=r.end_day, tau_sim=r.tau, D=r.D, Lbar=r.Lbar,
                        veh_km=r.veh_km, delta=abs(start_of[b] - bt.a), in_window=lo <= start_of[b] <= hi, route=meta[b][2], unload_order_gap_km=meta[b][1], overload=";".join(r.flags),
                        max_wait_h=max([fr.clock_h(lg.arrive, lg.start) for lg in r.logs if lg.c_unload + lg.c_load > 0] or [0.0]),
                        s10_viol=sum(1 for lg in r.logs if lg.c_unload + lg.c_load > 0 and fr.queue_violates(lg))))
    df = pd.DataFrame(out)
    df.to_csv(OUT / f"batches_{tag}.csv", index=False, encoding="utf-8-sig")
    veh_over = sum(1 for w in whs.values() for d, v in w.veh.items() if v > 20 + 1e-6)
    summ = dict(方案=tag, 批次=len(df), 运力合计=int(df["T"].sum()), 总车数_统一口径=int(df["N"].sum()), 总人数_统一口径=int(df["P"].sum()),
                代领代交等效车数=tot["A"], 失衡度=tot["E"], 批次仓库对=int(df.n_targets.sum()), 调运总里程=df.D.sum(), 载货总行驶距离=df.Lbar.sum(),
                车公里=df.veh_km.sum(), 执行总时间_回放=int(df.tau_sim.sum()), 开始偏离=int(df.delta.sum()), 越窗批次数=int((~df.in_window).sum()),
                超2000km批次=int((df.D > 2000).sum()), 最大里程=df.D.max(),
                卸货次序取最长时的总里程=df.D.sum() + df.unload_order_gap_km.sum(), 按表中顺序会超载的批次=int((df.overload.fillna("") != "").sum()), 等待超24小时的批次=int((df.s10_viol > 0).sum()), 最长等待_小时=float(df.max_wait_h.max()))
    return summ, df, flow


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cap, D = fp.load_cap(), fp.load_dist()
    B2, K2 = fb.build(2, unit_wh={"U11": "WS"})  # 附件 2 的“U4转U11”未写仓库；附件 3 显示这批货送到 WS
    rows3 = load3()
    tr, left = trace(K2, rows3)
    print(f"追溯：{len(tr)}/{len(K2)} 个块已对应，附件 3 余量 {left}")
    # 附件 3 批次 → 附件 2 原批次（按执行单位自办的块）
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
    # 逐块：情形判定
    assign_after, tr_rows = {}, []
    for k in K2:
        b3, u3, how, nsplit = tr.get(k.id, (None, None, "未对应", 0))
        row = dict(block=k.id, batch2=k.batch, owner=k.owner, w=k.w, dir=k.dir, h=k.h, inner=k.inner, s_owner=k.s(cap, k.owner),
                   batch3=b3, executor=u3, how=how, split=nsplit)
        if how == "自办":
            if b3_to_b2.get(b3) != k.batch:
                row["note"] = f"并入同单位的另一批（原批 {b3_to_b2.get(b3)}）"
            assign_after[k.id] = ("own",) if b3_to_b2.get(b3) == k.batch else None
            row["case"] = ""
        elif how in ("代领", "代交", "反转代交"):
            beta = b3_to_b2.get(b3)
            opts = [o for o in f_p2.options(k, B2, K2, cap, D) if o[1] == beta and ((o[0] == "REV") == (how == "反转代交"))]
            row["case"] = "/".join(sorted({o[2] for o in opts})) or "无对应情形"
            row["s_exec"] = k.s(cap, u3)
            assign_after[k.id] = opts[0] if opts else None
            row["exec_batch2"] = beta
        tr_rows.append(row)
    tdf = pd.DataFrame(tr_rows)
    tdf.to_csv(OUT / "trace.csv", index=False, encoding="utf-8-sig")
    print(tdf.how.value_counts().to_dict(), "情形:", tdf[tdf.how != "自办"].case.value_counts().to_dict())
    bad = [k for k, v in assign_after.items() if v is None]
    print("无法按 spec 情形表达的块:", [(K2[i].batch, K2[i].owner, K2[i].w, tr.get(i)) for i in bad])
    # 回放：before = 全部自办、按提报开始日；after = 追溯指派、按附件 3 实施开始日
    assign_before = {k.id: ("own",) for k in K2}
    order2 = {b: [k.w for k in bt.blocks] for b, bt in B2.items()}
    sb, dfb, _ = plan_metrics("before", assign_before, B2, K2, cap, D, {b: bt.a for b, bt in B2.items()}, order2)
    summ = [sb]
    if not bad:
        b2_to_b3 = {v: k for k, v in b3_to_b2.items()}
        sa, dfa, flow = plan_metrics("after", assign_after, B2, K2, cap, D, {b: start3[b2_to_b3[b]] for b in b2_to_b3},
                                     {b: order3[b2_to_b3[b]] for b in b2_to_b3})
        dfa["batch3"] = dfa.batch.map(b2_to_b3)
        dfa["tab_days"] = dfa.batch3.map(lambda x: end3[x] - start3[x] + 1)
        dfa.to_csv(OUT / "batches_after.csv", index=False, encoding="utf-8-sig")
        sa["执行总时间_表列"] = int(dfa.tab_days.sum())
        sa["表列天数少于回放的批次"] = int((dfa.tab_days < dfa.tau_sim).sum())
        summ.append(sa)
        pd.DataFrame([dict(executor=x, owner=y, s=v) for (x, y), v in sorted(flow.items())]).to_csv(OUT / "flow_after.csv", index=False, encoding="utf-8-sig")
    sdf = pd.DataFrame(summ)
    sdf.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
    print(sdf.T.to_string())
    # 把问题 2 的模型用于 Y1
    ym = []
    for tag, kw in (("模型最优", {}), ("禁用R4", dict(allow_R4=False))):
        r = f_p2.solve(B2, K2, cap, D, **kw)
        _, tot, _ = f_p2.summarize(r["assign"], B2, K2, cap)
        ym.append(dict(方案=tag, 批次=tot["B"], 批次下界=r["stats"].get("B_bound"), 代领代交等效车数=tot["A"], 总车数=tot["N"], 总人数=tot["P"], 批次仓库对=tot["pairs"], 失衡度=tot["E"],
                       U9交U6块数=r["stats"].get("U9")))
    pd.DataFrame(ym).to_csv(OUT / "y1_model.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(ym).to_string(index=False))


if __name__ == "__main__":
    main()
