"""把问题 3 主方案中几个批次写成“按天的白话时间线 + 是/否核对题”，供人对照原题（F.docx）核对。

货物、货主取自结果表 results/F/问题3_results.xlsx（附件 7 格式）；精确时刻取自引擎台账 results/F/p3/steps_main.csv；
规则原句取自原题“运输车辆和货物仓库的相关数据和要求”第 1–10 条（problem/F/F.md 第 221–239 行）。不调用求解代码。
用法：python tools/trace_batches.py [原批次号 ...]（默认 1 13 25 27；27 含排队等待）
输出：review/human_trace_p3.md
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import f_check as fc  # noqa: E402

RULE = {
    1: "第 1 条：调运梯队每天的出发时间均为 8:00",
    2: "第 2 条：每天工作时长（机动、装卸载及等待）为 8 小时",
    3: "第 3 条：车速 62.5 公里/小时；装卸载 2.5 车/小时",
    4: "第 4 条：装卸完成后剩余工作时间无法到达下一任务地点……则次日进行机动；最多在目标货物仓库等待 1 天",
    9: "第 9 条：一个仓库每天处理的需求单位不超过 3 支、装卸运输车辆不超过 20 台",
    10: "第 10 条：不同需求单位按到达先后装卸，先到者全部装卸完才轮到后到者",
}


def clock(h):
    m = int(round(h * 60))
    return f"{8 + m // 60:02d}:{m % 60:02d}"


def md(d):
    return f"4月{d}日" if d <= 30 else (f"5月{d - 30}日" if d <= 61 else f"6月{d - 61}日")


def dur(h):
    m = int(round(h * 60))
    if m < 60:
        return f"{m} 分钟"
    return f"{m // 60} 小时" + (f" {m % 60} 分" if m % 60 else "")


def goods_text(seg, unit):
    its = [it for it, _ in seg["items"]]
    names = "、".join(its[:3]) + (" 等" if len(its) > 3 else "")
    who = {0: "自己的", 1: f"替 {seg['who']} 代领的", -1: f"替 {seg['who']} 代交的"}[seg["flag"]]
    if seg["flag"] == 0 and "领回" in (seg["note"] or ""):
        who = "自己的、由别的单位代领后暂存在此仓库的"
    return f"{who} {len(its)} 种货，共 {abs(seg['eq']):.3f} 车（{names}）"


def main():
    ids = [int(x) for x in sys.argv[1:]] or [1, 13, 25, 27]
    P3 = {bt["id"]: bt for bt in fc.read_p3(ROOT / "results/F/问题3_results.xlsx")}
    s = pd.read_csv(ROOT / "results/F/p3/steps_main.csv")
    bm = pd.read_csv(ROOT / "results/F/p3/batch_id_map.csv").set_index("orig_batch")
    bt_ = pd.read_csv(ROOT / "results/F/p3/batches_main.csv").set_index("batch")
    D = fc.read_dist()
    H = fc.H
    out = ["# 问题 3 主方案：四个批次的按天时间线（请对照原题核对）", "",
           "> 由 `tools/trace_batches.py` 生成（货物取自 `results/F/问题3_results.xlsx`，时刻取自 `results/F/p3/steps_main.csv`）。",
           "> 读法：每批先看“这一批要办的事”，再按天看时间线；每处停下来的地方都写了依据的是原题哪一条。最后的“核对题”只需回答 是 / 否，",
           "> 答“否”的请在题后写一句原因。规则编号指原题“运输车辆和货物仓库的相关数据和要求”第 1–10 条。", ""]
    for b in ids:
        new = int(bm.loc[b, "new_batch"])
        bt, r = P3[new], bt_.loc[b]
        x, own = bt["unit"], set(H[bt["unit"]])
        st = s[s.batch == b].sort_values("seq").reset_index(drop=True)
        stops = bt["stops"]
        assert len(stops) == len(st), (b, len(stops), len(st))
        # 这一批要办的事：每份货从哪装、到哪卸
        task = defaultdict(lambda: [None, None, None])
        for i, sp in enumerate(stops):
            for sg in sp["segs"]:
                k = (sg["flag"], sg["who"], tuple(sg["items"]))
                task[k][2] = sg
                if sg["io"] == "发":
                    task[k][0] = sp["node"]
                else:
                    task[k][1] = sp["node"]
        out += [f"## 结果表第 {new} 批（原批次 {b}）：{x}，运输车 {r['T']} 台",
                f"提报开始 {md(r.a)}，实际 {md(r.start)} 出发（偏离 {r.delta} 天）、{md(r.end)} 回到驻地，共 **{r.tau} 天**；总里程 {r.D:.0f} km。"
                f"{x} 的队属仓库：{'、'.join(H[x])}。", "", "**这一批要办的事**", ""]
        for (flag, who, items), (ld, ul, sg) in task.items():
            out.append(f"- {goods_text(sg, x)}：在 {ld} 装车 → 在 {ul} 卸车")
        out += ["", "**时间线**", ""]
        qs, cur_day, prev = [], None, x
        seen = set()

        def cite(*ns):
            parts = []
            for n in ns:
                parts.append(RULE[n] if n not in seen else f"第 {n} 条")
                seen.add(n)
            return "；".join(parts)
        out_day = lambda d: out.append(f"**{md(d)}**")
        dep_day = int(r.start)
        out_day(dep_day)
        cur_day = dep_day
        out.append(f"- 08:00 从驻地 {x} 出发（{cite(1)}）")
        for i, (sp, lg) in enumerate(zip(stops, st.itertuples())):
            dist = float(D[(prev, sp["node"])]) if prev != sp["node"] else 0.0
            if int(lg.arrive_day) != cur_day:
                cur_day = int(lg.arrive_day)
                out_day(cur_day)
            kind = "回到驻地" if (i == len(stops) - 1) else ("途经（不作业）" if not sp["segs"] and not lg.rejoin else "到达")
            line = f"- {clock(lg.arrive_h)} {kind} {sp['node']}（距上一站 {dist:.0f} km，行驶 {dur(dist / 62.5)}" +                 ("；超过 500 km，每天开 8 小时、途中过夜" if dist > 500 else "") + "）"
            if sp["node"] == x and 0 < i < len(stops) - 1:
                qs.append(f"途中经过自己驻地 {x}（没有结束本批任务，继续去下一站），原题是否允许？")
            out.append(line)
            c = lg.c_unload + lg.c_load
            if c > 0:
                wait = (lg.start_day - lg.arrive_day) * 8 + (lg.start_h - lg.arrive_h)
                if wait > 1e-6:
                    if lg.start_day == lg.arrive_day:
                        out.append(f"  - 排队等候 {dur(wait)}（前面有别的单位在作业；{cite(10)}）")
                    else:
                        out.append(f"  - 当天轮不到，{md(int(lg.start_day))} {clock(lg.start_h)} 才开始作业（{cite(9, 10)}）")
                    qs.append(f"在 {sp['node']} 排队等候 {dur(wait)}，是否符合第 9、10 条？")
                for sg in sp["segs"]:
                    act = "装上" if sg["io"] == "发" else "卸下"
                    out.append(f"  - {act} {goods_text(sg, x)}")
                drops = [sg["who"] for sg in sp["segs"] if sg["io"] == "收" and sg["flag"] == 1 and sp["node"] not in own]
                if drops and i < len(stops) - 2:
                    qs.append(f"在 {sp['node']} 卸下替 {'、'.join(drops)} 代领的货之后，还继续去别的仓库作业。原题代领情形②（被代领货物所在仓库和货主的队属仓库都在执行方的目标仓库之中）是否允许这样“路过时先卸”？")
                    if sg["follow"] == "否":
                        out.append(f"  - 装了这批货的车**留在 {sp['node']}**（留置），其余车继续走，之后回来汇合")
                span = f"共 {c} 台次 × 0.4 小时 = {dur(c / 2.5)}（{cite(3)}）"
                if lg.end_day > lg.start_day:
                    out.append(f"  - {span}；每天只能作业到 16:00，跨到 {md(int(lg.end_day))} {clock(lg.end_h)} 才做完（{cite(2)}）")
                    qs.append(f"在 {sp['node']} 装卸 {c} 台次，跨日做完（每天 8:00–16:00），是否符合第 2、3 条？")
                else:
                    out.append(f"  - {span}，{clock(lg.end_h)} 做完")
            if lg.rejoin:
                out.append(f"  - 与此前留在 {sp['node']} 的车汇合")
            if i + 1 < len(stops):
                nxt = stops[i + 1]["node"]
                dn = float(D[(sp["node"], nxt)]) if sp["node"] != nxt else 0.0
                if lg.depart_day > lg.end_day or (lg.depart_day == lg.end_day and lg.depart_h - lg.end_h > 1e-6):
                    if dn > 500:
                        why = f"下一段到 {nxt} {dn:.0f} km 超过 500 km，要整天行驶，只能 8:00 出发、途中过夜"
                    else:
                        why = f"下一段到 {nxt} {dn:.0f} km 要开 {dur(dn / 62.5)}，16:00 前到不了"
                    out.append(f"  - **停在 {sp['node']} 过夜**：{why}，所以次日 8:00 再出发（{cite(4)}）")
                    qs.append(f"在 {sp['node']} 做完后因“{why}”而停到次日 8:00，是否符合第 4 条？")
                    cur_day = int(lg.depart_day)
                    out_day(cur_day)
                    out.append(f"- 08:00 从 {sp['node']} 出发，前往 {nxt}" + ("（全天行驶）" if dn > 500 else ""))
            prev = sp["node"]
        qs = list(dict.fromkeys(qs))[:5]
        if len(qs) < 3:
            qs.append(f"本批共 {r.tau} 天（{md(r.start)} 至 {md(r.end)}），按上面的时间线逐日数下来是否一致？")
        out += ["", "**核对题**（答 是 / 否）", ""] + [f"{k + 1}. {q}　答：" for k, q in enumerate(qs)] + [""]
    out += ["## 其他意见", "", "（有原题依据但上面没问到的，写在这里）", ""]
    (ROOT / "review" / "human_trace_p3.md").write_text("\n".join(out), encoding="utf-8")
    print("写出 review/human_trace_p3.md")


if __name__ == "__main__":
    main()
