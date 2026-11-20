"""F 题独立检查器：只读结果 xlsx（附件 6、7/8 格式）与原始附件 1、4、5，重算指标并核约束。

不导入 src/ 下的任何模块。用法：
    python tools/f_check.py results/F/问题2_results.xlsx results/F/问题3_results.xlsx [--out results/F/checks/p3_check]
输出：终端汇总；<out>_metrics.csv（逐批未舍入指标）；<out>_violations.csv。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
ATT = ROOT / "problem" / "F" / "original" / "附件"
H = {"U8": ["WO"], "U11": ["WO", "WS"], "U12": ["WO"], "U6": ["WP"], "U9": ["WP"], "U3": ["WQ"], "U7": ["WQ", "WU"],
     "U4": ["WR"], "U10": ["WS"], "U2": ["WS"], "U5": ["WS"], "U1": ["WT"]}  # 题面附表 1
UNITS = [f"U{i}" for i in range(1, 13)]
TEAM = {"WO", "WP", "WQ", "WR", "WS", "WT", "WU"}
EPS = 1e-9
TOL = dt.timedelta(seconds=61)


def ceil_(x):
    return int(math.ceil(x - 1e-9))


def att(k):
    return glob.glob(str(ATT / f"附件{k} *.xlsx"))[0]


def read_dist():
    rows = list(openpyxl.load_workbook(att(1)).worksheets[0].iter_rows(values_only=True))
    names = [str(x) for x in rows[0][1:]]
    return {(str(r[0]), n): float(v) for r in rows[1:] for n, v in zip(names, r[1:])}


def read_cap():
    rows = list(openpyxl.load_workbook(att(5)).worksheets[0].iter_rows(values_only=True))
    us = [str(h).split("\n")[0] for h in rows[0][1:13]]
    return {(str(r[0]).strip(), u): float(v) for r in rows[1:] if r[0] is not None for u, v in zip(us, r[1:13])}


def md_day(m, d):
    return {4: 0, 5: 30, 6: 61}[m] + d


def read_demand():
    """附件 4 → 逐货物行需求：(原批次, 单位, 外部仓库 w, 方向, 存放仓库 h, 货物, 数量)，及原批次的 (a, e, T0)。"""
    ws = openpyxl.load_workbook(att(4)).worksheets[0]
    val = {(c.row, c.column): c.value for row in ws.iter_rows(max_col=11) for c in row}
    top = {}
    for rg in ws.merged_cells.ranges:
        for r in range(rg.min_row, rg.max_row + 1):
            for c in range(rg.min_col, rg.max_col + 1):
                top[(r, c)] = (rg.min_row, rg.min_col)
    g = lambda r, c: val.get(top.get((r, c), (r, c)))
    dem, info, seenT = [], {}, set()
    for r in range(2, ws.max_row + 1):
        b, item = g(r, 1), g(r, 6)
        if not isinstance(b, (int, float)) or item is None or not re.fullmatch(r"D\d+", str(item).strip()):
            continue
        b, u = int(b), g(r, 3)
        t = g(r, 2)
        if isinstance(t, (dt.datetime, dt.date)):
            a = e = md_day(t.month, t.day)
        elif isinstance(t, (int, float)):
            d0 = dt.date(1899, 12, 30) + dt.timedelta(days=int(t))
            a = e = md_day(d0.month, d0.day)
        else:
            mm = re.findall(r"(\d+)\s*月\s*(\d+)", str(t))  # 不依赖“日”字（有“4月14至4月20日”的写法）
            if len(mm) == 1:
                mm = mm * 2
            a, e = md_day(int(mm[0][0]), int(mm[0][1])), md_day(int(mm[1][0]), int(mm[1][1]))
        info.setdefault(b, dict(unit=u, a=a, e=e, T0=0))
        tk = top.get((r, 8), (r, 8))
        if tk not in seenT and isinstance(val.get(tk), (int, float)):
            seenT.add(tk)
            info[b]["T0"] += int(val[tk])
        fl = str(g(r, 5)).replace(" ", "").replace("(", "（").replace(")", "）")
        m = re.match(r"^(\w+?)（发）-(\w+?)（收）$", fl)
        src, dst = m.group(1), m.group(2)
        rm = str(g(r, 11) or "")
        w, dr = (src, "领") if dst == u else (dst, "交")
        ms = re.search(r"(?:存放至|放置于)(W[A-Z])|从(W[A-Z])装载", rm)
        h = (ms.group(1) or ms.group(2)) if ms else (H[u][0] if len(H[u]) == 1 else None)
        dem.append(dict(batch=b, unit=u, w=w, dir=dr, h=h, item=str(item).strip(), qty=float(g(r, 7))))
    return dem, info


def read_p3(path):
    """附件 7/8 格式 → [批次 dict]。只取各合并块左上角的值。"""
    ws = openpyxl.load_workbook(path).worksheets[0]
    out, cur, stop, seg = [], None, None, None
    for row in ws.iter_rows(min_row=2, max_col=14, values_only=True):
        if all(v is None for v in row):
            continue
        if row[0] is not None:
            cur = dict(id=int(row[0]), period=row[1], unit=row[2], stops=[])
            out.append(cur)
        if row[3] is not None:
            stop = dict(node=row[3], arrive=row[4], depart=row[12], segs=[], note=row[13])
            cur["stops"].append(stop)
        if row[5] is not None:
            seg = dict(io=row[5], flag=int(row[8]), who=row[9], eq=float(row[10]), follow=row[11], note=row[13] or "", items=[])
            stop["segs"].append(seg)
        if row[6] is not None:
            seg["items"].append((str(row[6]), float(row[7])))
    return out


def read_p2(path):
    ws = openpyxl.load_workbook(path).worksheets[0]
    out = {}
    for row in ws.iter_rows(min_row=2, max_col=11, values_only=True):
        if row[0] is not None:
            out[int(row[0])] = dict(unit=row[1], T=int(row[8]), N=int(row[9]), P=int(row[10]))
    return out


def day_of(t):
    return md_day(t.month, t.day)


def hours(t):
    return (t.hour - 8) + t.minute / 60 + t.second / 3600


def mk(day, h, year):
    m, d = (4, day) if day <= 30 else ((5, day - 30) if day <= 61 else (6, day - 61))
    return dt.datetime(year, m, d, 8) + dt.timedelta(hours=h)


def travel(t, dist):
    """独立实现 S5/S6：返回 (出发, 到达)。"""
    if dist <= EPS:
        return t, t
    d, h = day_of(t), hours(t)
    hrs = dist / 62.5
    if dist <= 500 + EPS:
        if h + hrs <= 8 + 1e-6:
            return t, t + dt.timedelta(hours=hrs)
        s = mk(d + 1, 0, t.year)
        return s, s + dt.timedelta(hours=hrs)
    if h > 1e-6:
        d += 1
    n = ceil_(dist / 500)
    return mk(d, 0, t.year), mk(d + n - 1, (dist - 500 * (n - 1)) / 62.5, t.year)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("p2")
    ap.add_argument("p3")
    ap.add_argument("--out", default=str(ROOT / "results" / "F" / "checks" / "p3_check"))
    args = ap.parse_args()
    D, CAP = read_dist(), read_cap()
    dem, info = read_demand()
    P2, P3 = read_p2(args.p2), read_p3(args.p3)
    viol, metrics = [], []
    V = lambda code, b, msg: viol.append(dict(code=code, batch=b, msg=msg))

    # ---- 把每个结果批次对应回原始批次（按执行单位自有货的 (仓库, 货物, 数量) 投票）
    key2b = defaultdict(list)
    for r in dem:
        key2b[(r["unit"], r["w"], r["item"], r["qty"])].append(r["batch"])
    orig = {}
    for bt in P3:
        votes = defaultdict(int)
        for st in bt["stops"]:
            for sg in st["segs"]:
                if sg["flag"] == 0 and st["node"] not in H[bt["unit"]]:
                    for it, q in sg["items"]:
                        for ob in key2b.get((bt["unit"], st["node"], it, q), []):
                            votes[ob] += 1
        if not votes:
            V("映射", bt["id"], "找不到对应的原始批次")
            continue
        orig[bt["id"]] = max(votes, key=votes.get)
    if len(set(orig.values())) != len(orig):
        V("C批次", None, "两个结果批次对应同一个原始批次（批次数增加或同单位合并）")

    # ---- 逐批：等效车数、装载量、里程、载货距离、时间一致性
    services = defaultdict(list)  # 仓库 -> [(到达, 批次, 单位, 台次, 报告的离开/下一站依据)]
    moves = defaultdict(lambda: defaultdict(float))  # (属主, 货物) -> 节点 -> 净流出（装 +，卸 −）
    act = defaultdict(lambda: defaultdict(int))
    flowHR = defaultdict(float)
    A_tot = 0.0
    stage_un, stage_ld = {}, {}  # R4：(属主, 货物, 仓库) -> 时间
    for bt in P3:
        b, x = bt["id"], bt["unit"]
        T = P2.get(b, {}).get("T")
        if T is None or P2[b]["unit"] != x:
            V("表间", b, "附件6 中无此批次或执行单位不一致")
            continue
        own = set(H[x])
        onboard = []  # [属主, 货物, 数量, 等效, 已走距离, 装车节点, 是否代办, 是否送交侧]
        left = {}  # 节点 -> [货行]
        movT, Dtot, pos, prev_end = T, 0.0, x, None
        start = bt["stops"][0]["arrive"]
        done = []
        targets, special = set(), set()
        recv = send = 0.0
        start_day = None
        first_ext = None  # S12：第一个有作业的外部仓库的站序
        dj_load = defaultdict(list)  # R5：(属主, 节点) -> 代交货装车的站序
        act_nodes = {x} | own | {s_["node"] for s_ in bt["stops"] if s_["segs"]}
        for i, st in enumerate(bt["stops"]):
            n = st["node"]
            if n not in act_nodes:
                V("S15", b, f"第 {i} 站经过与本批无关的节点 {n}")
            if first_ext is None and n.startswith("W") and n not in own and st["segs"]:
                first_ext = i
            d = D[(pos, n)] if pos != n else 0.0
            if i == 0:
                # 出发时刻 = 出发日 8:00；由首站到达时刻反推出发日
                dep0 = None
                for cand_day in range(day_of(st["arrive"]) - 4, day_of(st["arrive"]) + 1):
                    if cand_day >= 1 and abs(travel(mk(cand_day, 0, st["arrive"].year), d)[1] - st["arrive"]) <= TOL:
                        dep0 = cand_day
                if dep0 is None:
                    V("S5/S6", b, f"首站 {n} 的到达时刻无法由某天 8:00 出发得到")
                    dep0 = day_of(st["arrive"])
                start_day = dep0
            Dtot += d
            for g in onboard:
                g[4] += d
            pos = n
            if n in left and not any(sg["follow"] == "否" for sg in st["segs"]):
                if n != list(left)[-1]:
                    V("S11", b, f"在 {n} 汇合，但最近一次留置在 {list(left)[-1]}（应按相反顺序汇合）")
                grp = left.pop(n)
                onboard += grp
                movT += ceil_(sum(g[3] for g in grp))
            su = sl = 0.0
            new_left = []
            for sg in st["segs"]:
                owner = sg["who"] if sg["flag"] != 0 else x
                eq = sum(q / CAP[(it, x)] for it, q in sg["items"])
                if abs(abs(sg["eq"]) - eq) > 1e-4:
                    V("等效车数", b, f"{n} {sg['io']} 表中 {sg['eq']}，重算 {eq:.6f}")
                if owner == "U9" and x not in ("U9", "U6"):
                    V("C6", b, "U9 的货由 U6 以外的单位执行")
                for it, q in sg["items"]:
                    e1 = q / CAP[(it, x)]
                    if sg["io"] == "发":
                        sl += e1
                        moves[(owner, it)][n] += q
                        row = [owner, it, q, e1, 0.0, n, sg["flag"], False, i]
                        if sg["flag"] == -1:
                            dj_load[(owner, n)].append(i)
                        (new_left if sg["follow"] == "否" else onboard).append(row)
                        if n in TEAM and n not in own and sg["flag"] == 0 and "领回" in sg["note"]:
                            stage_ld[(owner, it, n, q)] = (st["arrive"], b)
                    else:
                        su += e1
                        moves[(owner, it)][n] -= q
                        hit = next((g for g in onboard if g[0] == owner and g[1] == it and abs(g[2] - q) < 1e-6), None)
                        if hit is None:
                            V("装卸匹配", b, f"{n} 卸 {owner} 的 {it}×{q} 时车上没有")
                            continue
                        onboard.remove(hit)
                        done.append(hit)
                        if hit[6] == 0 and hit[5] in own and n not in own and first_ext is not None and hit[8] > first_ext:
                            V("S12", b, f"自有送交货 {it} 在第 {hit[8]} 站（{hit[5]}）才装车，第 {first_ext} 站已在外部仓库作业")
                        if hit[6] == 1 and n in TEAM and n not in own and dj_load.get((owner, n)) and hit[8] < min(dj_load[(owner, n)]):
                            V("R5先后", b, f"代 {owner} 领的 {it} 在第 {hit[8]} 站装车，早于在 {n} 装代交货（第 {min(dj_load[(owner, n)])} 站）")
                        if sg["flag"] != 0:
                            A_tot += e1
                            flowHR[(x, owner)] += e1
                        if "暂存" in sg["note"]:
                            stage_un[(owner, it, n, q)] = (st, b)
                        is_send = (hit[5] in own and n not in own and sg["flag"] == 0) or sg["flag"] == -1
                        if is_send:
                            send += e1
                        else:
                            recv += e1
                if n not in own and n != x:
                    if sg["flag"] == 0 and "领回" not in sg["note"]:
                        targets.add(n)
                    else:
                        special.add(n)
            if new_left:
                left[n] = new_left
                movT -= ceil_(sum(g[3] for g in new_left))
            load_now = sum(g[3] for g in onboard)
            if load_now > movT + 1e-6:
                V("S14", b, f"离开 {n} 时装载 {load_now:.3f} > 行驶车队 {movT} 辆")
            c = ceil_(su) + ceil_(sl)
            st["_c"], st["_su"], st["_sl"] = c, su, sl
            queued = n.startswith("W") and n not in own
            if c > 0 and queued:
                services[n].append(st | dict(_b=b, _u=x, _idx=i))
            if c > 0 and not queued:
                # 自己的队属仓库：不排队，直接按工作时间推进
                t, rem = st["arrive"], float(c)
                while rem > EPS:
                    if hours(t) >= 8 - 1e-6:
                        t = mk(day_of(t) + 1, 0, t.year)
                    do = min(rem, (8 - hours(t)) * 2.5)
                    t += dt.timedelta(hours=do / 2.5)
                    rem -= do
                st["_end"] = t
            if c == 0:
                st["_end"] = st["arrive"]
            prev_end = st.get("_end")  # 排队仓库的 _end 稍后统一算；先占位
            st["_idx"] = i
            bt["_stops_ref"] = bt["stops"]
        if onboard or left:
            V("S11", b, "批次结束时车上仍有货或留置未汇合")
        if pos != x:
            V("S12", b, "最后一站不是驻地")
        bt.update(_T=T, _D=Dtot, _done=done, _targets=targets, _special=special - targets, _recv=recv, _send=send, _start=start_day)

    # ---- 排队仓库：按到达时刻先到先服务（独立实现），算出每次作业的结束时刻
    for w, lst in services.items():
        lst.sort(key=lambda s: (s["arrive"], s["_b"]))
        free = None
        units_day, veh_day = defaultdict(set), defaultdict(float)
        for s in lst:
            t = s["arrive"] if free is None or s["arrive"] > free else free
            rem, first = float(s["_c"]), None
            while rem > EPS:
                if hours(t) >= 8 - 1e-6:
                    t = mk(day_of(t) + 1, 0, t.year)
                d = day_of(t)
                if s["_u"] not in units_day[d] and len(units_day[d]) >= 3:
                    t = mk(d + 1, 0, t.year)
                    continue
                units_day[d].add(s["_u"])
                first = first or t
                do = min(rem, (8 - hours(t)) * 2.5)
                t += dt.timedelta(hours=do / 2.5)
                rem -= do
                veh_day[d] += do
            free = t
            s["_end_q"], s["_first"] = t, first
            idle = day_of(first) - day_of(s["arrive"]) - 1 + (1 if hours(s["arrive"]) < 1e-6 and day_of(first) > day_of(s["arrive"]) else 0)
            if idle > 1:
                V("S10", s["_b"], f"在 {w} 排队整日等待 {idle} 天")
        for d, v in veh_day.items():
            if v > 20 + 1e-6:
                V("S8", None, f"{w} 第 {d} 天 {v:.1f} 台次")
            if len(units_day[d]) > 3:
                V("S8", None, f"{w} 第 {d} 天 {len(units_day[d])} 支单位")
    endq = {(s["_b"], s["_idx"]): s["_end_q"] for lst in services.values() for s in lst}

    # ---- 用排队结果复核每批后续时刻、天数、等待、时间窗
    tau_sum = delta_sum = D_sum = L_sum = vk_sum = 0.0
    Vpairs = 0
    pairs_cnt = 0
    for bt in P3:
        if "_T" not in bt:
            continue
        b, x = bt["id"], bt["unit"]
        stops = bt["stops"]
        prev_end = None
        left_day = {}
        for i, st in enumerate(stops):
            end = endq.get((b, i), st.get("_end"))
            if i + 1 < len(stops):
                nx = stops[i + 1]
                d = D[(st["node"], nx["node"])] if st["node"] != nx["node"] else 0.0
                exp_dep, exp_arr = travel(end, d)
                if st["depart"] is not None and abs(st["depart"] - exp_dep) > TOL:
                    V("离开时刻", b, f"{st['node']} 应于 {exp_dep:%m/%d %H:%M} 离开，表中 {st['depart']:%m/%d %H:%M}")
                if abs(exp_arr - nx["arrive"]) > TOL:
                    V("时刻", b, f"{st['node']}→{nx['node']}：作业应于 {end:%m/%d %H:%M} 结束，应到 {exp_arr:%m/%d %H:%M}，表中 {nx['arrive']:%m/%d %H:%M}")
            if any(sg["follow"] == "否" for sg in st["segs"]):
                left_day[st["node"]] = day_of(end)
            elif st["node"] in left_day and day_of(st["arrive"]) - left_day.pop(st["node"]) - 1 + (1 if hours(st["arrive"]) >= 8 - 1e-6 else 0) > 1:
                V("S10", b, f"留置在 {st['node']} 的车整日等待超过 1 天")
        s_day, e_day = bt["_start"], day_of(stops[-1]["arrive"])
        if e_day > 91 or s_day < 1:
            V("S1", b, "超出 4/1–6/30")
        ob = orig.get(b)
        a, e = info[ob]["a"], info[ob]["e"]
        if not (max(1, a - 6) <= s_day <= e):
            V("S2", b, f"出发日 {s_day} 不在 [{a - 6}, {e}]")
        T0 = info[ob]["T0"]
        Tc = ceil_(max(bt["_recv"], bt["_send"]))
        if Tc != bt["_T"]:
            V("运力", b, f"附件6 T={bt['_T']}，重算 {Tc}")
        if bt["_T"] > 30 or bt["_T"] - T0 > 3:
            V("C2/C3", b, f"T={bt['_T']} T0={T0}")
        N = bt["_T"] + 1 + (1 if bt["_T"] <= 20 else 2) + min(2, ceil_(bt["_T"] / 10))
        P = 2 * N + 3 + 2 * ceil_(bt["_T"] / 5)
        if (N, P) != (P2[b]["N"], P2[b]["P"]):
            V("车数人数", b, f"附件6 N/P={P2[b]['N']}/{P2[b]['P']}，重算 {N}/{P}")
        for d in range(s_day, e_day + 1):
            act[x][d] += 1
        if len(bt["_targets"]) > 4:
            V("C1", b, "目标仓库超过 4 个")
        if bt["_D"] > 2000 + 1e-6:
            V("C4", b, f"里程 {bt['_D']:.0f}")
        for n in bt["_special"]:
            if n in TEAM and D[(x, n)] > 150 + 1e-9 and not any(n == t for t in bt["_targets"]):
                V("R5/R7", b, f"专程到访 {n}，距驻地 {D[(x, n)]:.0f} km")
        stot = sum(g[3] for g in bt["_done"])
        vk = sum(g[3] * g[4] for g in bt["_done"])
        Lbar = vk / stot if stot > 0 else 0.0
        tau = e_day - s_day + 1
        delta = abs(s_day - a)
        # 被代方时段
        owners = {(g[0]) for g in bt["_done"] if g[6] != 0}
        for st in stops:
            for sg in st["segs"]:
                if sg["flag"] != 0:
                    for it, q in sg["items"]:
                        cands = [r["batch"] for r in dem if r["unit"] == sg["who"] and r["item"] == it and abs(r["qty"] - q) < 1e-6]
                        sg.setdefault("_ob", set()).update(cands[:1])
        obs = set().union(*[sg.get("_ob", set()) for st in stops for sg in st["segs"]]) if stops else set()
        for o2 in obs:
            if not (max(1, info[o2]["a"] - 6) <= s_day <= info[o2]["e"]):
                Vpairs += 1
        bt["_e_day"] = e_day
        metrics.append(dict(batch=b, orig=ob, unit=x, T=bt["_T"], N=N, P=P, start=s_day, end=e_day, tau=tau, delta=delta, D=bt["_D"],
                            Lbar=Lbar, veh_km=vk, n_targets=len(bt["_targets"]), targets="/".join(sorted(bt["_targets"]))))
        tau_sum += tau; delta_sum += delta; D_sum += bt["_D"]; L_sum += Lbar; vk_sum += vk
        pairs_cnt += len(bt["_targets"])
    for u, days in act.items():
        if max(days.values()) > 2:
            V("S4", None, f"{u} 同一天执行超过 2 个批次")

    # ---- R4 先后：暂存卸完 ≤ 货主到达装车
    for key, (t_ld, b2) in stage_ld.items():
        if key not in stage_un:
            V("R4", b2, f"领回 {key} 但找不到暂存记录")
            continue
        st, b1 = stage_un[key]
        t_un = endq.get((b1, st["_idx"]), st.get("_end"))
        if t_ld < t_un - TOL:
            V("R4", b2, f"领回早于暂存完成：{t_ld} < {t_un}")
        bb = {bt["id"]: bt for bt in P3}
        if bb[b2]["_start"] <= bb[b1].get("_e_day", 0):  # 【裁U2】整批先后：货主批次出发日 > 暂存批次回驻地日
            V("R4整批", b2, f"货主批次 {b2} 出发日 {bb[b2]['_start']} 不晚于暂存批次 {b1} 回驻地日 {bb[b1].get('_e_day')}")

    # ---- 守恒：每个 (属主, 货物) 在各节点的净流出与附件 4 的需求一致（R3 的落仓允许 ≤150 km 的替代仓库）
    need = defaultdict(lambda: defaultdict(float))
    for r in dem:
        src, dst = (r["w"], r["h"]) if r["dir"] == "领" else (r["h"], r["w"])
        need[(r["unit"], r["item"])][src] += r["qty"]
        need[(r["unit"], r["item"])][dst] -= r["qty"]
    n_mis = 0
    for key in set(need) | set(moves):
        nodes = set(need[key]) | set(moves[key])
        diff = {n: moves[key][n] - need[key][n] for n in nodes if abs(moves[key][n] - need[key][n]) > 1e-6}
        if not diff:
            continue
        ok = False
        if len(diff) == 2:
            (n1, v1), (n2, v2) = diff.items()
            if abs(v1 + v2) < 1e-6 and n1 in TEAM and n2 in TEAM and min(D[(key[0], n1)], D[(key[0], n2)]) <= 150:
                ok = True  # 货落在距货主驻地 ≤150 km 的另一队属仓库（R3，货主自取）
        if not ok:
            n_mis += 1
            V("守恒", None, f"{key} 净流出不符 {diff}")

    Hs, Rs = defaultdict(float), defaultdict(float)
    for (x, y), v in flowHR.items():
        Hs[x] += v; Rs[y] += v
    E = sum(abs(Hs[u] - Rs[u]) for u in UNITS) / (2 * A_tot) if A_tot > 0 else 0.0
    tot = dict(批次=len(P3), 总车数=sum(m["N"] for m in metrics), 总人数=sum(m["P"] for m in metrics), 代领代交等效车数=A_tot,
               执行总时间=tau_sum, 开始偏离=delta_sum, 总里程=D_sum, 载货总行驶距离=L_sum, 失衡度=E, 批次仓库对=pairs_cnt, 车公里=vk_sum, V=Vpairs)
    import pandas as pd
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(metrics).to_csv(args.out + "_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(viol or [dict(code="无", batch=None, msg="")]).to_csv(args.out + "_violations.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([tot]).to_csv(args.out + "_totals.csv", index=False, encoding="utf-8-sig")
    print("重算指标：", {k: (round(v, 6) if isinstance(v, float) else v) for k, v in tot.items()})
    print(f"违例 {len(viol)} 条")
    by = defaultdict(int)
    for v in viol:
        by[v["code"]] += 1
    print(dict(by))
    for v in viol[:25]:
        print("  ", v)
    sys.exit(0 if not viol else 1)


if __name__ == "__main__":
    main()
