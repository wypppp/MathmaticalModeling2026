"""把问题 3 主方案中几个批次的逐站台账写成白话时间线，供人对照原题（F.docx）逐句核对。

只读 results/F/p3/steps_main.csv、batch_id_map.csv 与附件 1 距离表；不调用引擎。
用法：python tools/trace_batches.py [原批次号 ...]（默认 1 13 27）
输出：review/human_trace_p3.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_parse as fp  # noqa: E402


def hm(h):
    m = int(round(h * 60))
    return f"{8 + m // 60}:{m % 60:02d}"


def md(d):
    return f"4/{d}" if d <= 30 else (f"5/{d - 30}" if d <= 61 else f"6/{d - 61}")


def main():
    ids = [int(x) for x in sys.argv[1:]] or [1, 13, 27]
    s = pd.read_csv(ROOT / "results/F/p3/steps_main.csv")
    bm = pd.read_csv(ROOT / "results/F/p3/batch_id_map.csv").set_index("orig_batch")
    bt = pd.read_csv(ROOT / "results/F/p3/batches_main.csv").set_index("batch")
    D = fp.load_dist()
    out = ["# 问题 3 主方案：逐站白话时间线（供人对照原题核对）", "",
           "> 由 `tools/trace_batches.py` 从 `results/F/p3/steps_main.csv` 生成。请**对照原题 F.docx**（不是 spec）逐行判断每一步是否符合原题规则；",
           "> 有疑问的行在末尾写“第 x 批第 k 步：……”。时刻均为当天钟点；作业台次 = 卸、装各自向上取整后相加，每台次 0.4 小时（每小时 2.5 台次）。", ""]
    for b in ids:
        r = bt.loc[b]
        out += [f"## 结果表第 {bm.loc[b, 'new_batch']} 批（原批次 {b}，执行单位 {r.unit}，出动 {r['T']} 辆）",
                f"提报开始日 {md(r.a)}，实际出发 {md(r.start)}（偏离 {r.delta} 天），回到驻地 {md(r.end)}，共 {r.tau} 天；里程 {r.D:.0f} km，载货平均距离 {r.Lbar:.3f} km。", "",
                "| 步 | 地点 | 与上一站距离 | 到达 | 开始作业 | 卸 / 装（台次） | 作业结束 | 出发去下一站 | 说明 |", "|---|---|---|---|---|---|---|---|---|"]
        st = s[s.batch == b].sort_values("seq").reset_index(drop=True)
        prev = r.unit
        for i, x in st.iterrows():
            dist = float(D.at[prev, x.node]) if prev != x.node else 0.0
            note = []
            wait = (x.start_day - int(x.arrive_day)) * 8 + (x.start_h - x.arrive_h)
            if x.c_unload + x.c_load > 0 and wait > 1e-6:
                note.append(f"排队等候 {wait:.2f} 小时" if x.start_day == x.arrive_day else f"到达后次日 {hm(x.start_h)} 才开始作业")
            if x.c_unload + x.c_load > 0 and x.end_day > x.start_day:
                note.append("作业跨日（每天只在 8:00–16:00 作业）")
            if i + 1 < len(st):
                nxt = st.loc[i + 1]
                dn = float(D.at[x.node, nxt.node]) if x.node != nxt.node else 0.0
                if x.depart_day > x.end_day or (x.depart_day == x.end_day and x.depart_h - x.end_h > 1e-6):
                    note.append(f"下一段 {dn:.0f} km 需 {dn / 62.5:.2f} 小时，当天 16:00 前到不了，次日 8:00 出发" if dn <= 500 else f"下一段 {dn:.0f} km 超过 500 km，次日 8:00 出发、途中过夜")
            ld = x.load if isinstance(x.load, str) else ""
            ul = x.unload if isinstance(x.unload, str) else ""
            ops = f"{x.c_unload} / {x.c_load}" if x.c_unload + x.c_load > 0 else "—（只经过或返回）"
            goods = "；".join(t for t in (f"卸 {ul}" if ul else "", f"装 {ld}" if ld else "") if t)
            out.append(f"| {i} | {x.node} | {dist:.0f} km | {md(int(x.arrive_day))} {hm(x.arrive_h)} | {md(x.start_day)} {hm(x.start_h)} | {ops} | "
                       f"{md(x.end_day)} {hm(x.end_h)} | {x.depart} | {'；'.join(note)}{'（' + goods + '）' if goods else ''} |")
            prev = x.node
        out.append("")
    out += ["## 人的核对意见", "", "（在此逐条写：第 x 批第 k 步：原题哪一句、哪里不符）", ""]
    (ROOT / "review" / "human_trace_p3.md").write_text("\n".join(out), encoding="utf-8")
    print("写出 review/human_trace_p3.md")


if __name__ == "__main__":
    main()
