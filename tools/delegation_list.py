"""把指派中的每一笔代领代交写成白话清单，附原题情形原文，供人对照原题（F.docx 录 2.5）逐笔核对。

只读指派台账（results/F/p2/assign_main.csv 或 p4）与附件 1 距离、附表 1 队属仓库；不调用求解代码。
用法：python tools/delegation_list.py [p2|p4]（默认 p2）
输出：review/human_delegation_<p2|p4>.md
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import f_check as fc  # noqa: E402

H = fc.H
CASE = {  # 情形名与原题原文（problem/F/F.md 第 181–199 行）
    "R1": ("代领①", "Ux 和 Uy 共用队属货物仓库，且 Uy 的被代领货物所在仓库位于 Ux 的目标货物仓库之中"),
    "R2": ("代领②", "Ux 和 Uy 不共用队属货物仓库，但 Uy 的被代领货物所在仓库和 Uy 的队属货物仓库均位于 Ux 的目标货物仓库之中"),
    "R3": ("代领③", "……Ux 将代领货物运输到 Ux 的队属货物仓库，这时若 Uy 驻地与 Ux 的该队属货物仓库之间距离不超过 150 公里，则可进行代领"),
    "R4": ("代领④", "……Ux 的队属货物仓库正好位于 Uy 的某批次调运任务的目标货物仓库中，这时若 Uy 执行该批次任务的实施时间在 Ux 执行代领 Uy 货物任务的实施时间之后，则可进行代领，由 Ux 先将代领的 Uy 的货物放置在 Ux 的队属货物仓库中，待 Uy 执行货物调运到达 Ux 队属仓库时领回"),
    "R5": ("代领⑤", "……但若 Ux 驻地与 Uy 队属仓库之间距离不超过 150 公里，Ux 需帮助 Uy 代交货物，则 Ux 也可帮助 Uy 在其后续目标货物仓库开展代领"),
    "R6": ("代交①", "Ux 和 Uy 共用队属货物仓库，且 Uy 被代交货物送达的仓库位于 Ux 的目标货物仓库之中"),
    "R7": ("代交②", "Ux 和 Uy 不共用队属货物仓库，但 Ux 的驻地与 Uy 的队属货物仓库之间距离不超过 150 公里，且 Uy 被代交货物送达的仓库位于 Ux 的目标货物仓库之中"),
    "R8": ("代交③", "Ux 和 Uy 不共用队属货物仓库，但 Uy 的队属货物仓库和被代领货物送达的仓库均位于 Ux 的目标货物仓库之中"),
}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "p2"
    a = pd.read_csv(ROOT / "results" / "F" / tag / "assign_main.csv")
    D = fc.read_dist()
    own_w = a[a.option == "own"].groupby("batch").w.apply(set).to_dict()  # 各原批次保留的自有块所到的仓库
    own_h = a[a.option == "own"].groupby("batch").h.apply(set).to_dict()
    moved = a[a.option != "own"].reset_index(drop=True)
    title = "问题 2" if tag == "p2" else "问题 4"
    out = [f"# {title}：代领代交逐笔清单（请对照原题录 2.5 核对）", "",
           f"> 由 `tools/delegation_list.py {tag}` 从 `results/F/{tag}/assign_main.csv` 生成。共 {len(moved)} 笔。",
           "> 每笔写明：谁替谁、什么方向、货在哪个仓库、要到哪个仓库、执行方这一批本来要去哪些仓库，以及本文判定的情形和该情形的原文。",
           "> 请逐笔回答“是否符合所写情形”（是 / 否，否请写原因）。批次号是附件 4 的原批次号。“就近”一栏只供参考（本文按裁决 D2/W5 不另行要求）。",
           "> **“共用”的口径（裁决 X3）**：有多个可用队属仓库的单位（U7：WQ、WU；U11：WO、WS），按该笔货物在附件 4 中指定的存放仓库判定是否与执行方共用（附件 3 官方方案即如此区分）。", ""]
    for k, r in moved.iterrows():
        x, y = r.to_unit, r.owner
        tb = int(r.to_batch)
        tgt = sorted(w for w in own_w.get(tb, set()) | own_h.get(tb, set()) if w not in H[x] and w.startswith("W"))
        near = bool(set(H[x]) & set(H[y])) or any(D[(x, h)] <= 150 for h in H[y]) or any(D[(y, h)] <= 150 for h in H[x])
        if r.option == "REV":
            name, text = CASE[r.case]
            what = f"内部互转反转：原为 {y} 到 {r.h} 领取自己存在 {r.w} 的货，改为由 {x} 从 {r.w} 装上送到 {r.h}（按代交处理，{name}）"
        else:
            name, text = CASE[r.case]
            if r.dir == "领":
                what = f"{x}（原批 {tb}）替 {y} **代领**：货在 {r.w}，要送到 {y} 的仓库 {r.h}"
            else:
                what = f"{x}（原批 {tb}）替 {y} **代交**：货在 {y} 的仓库 {r.h}，要送到 {r.w}"
        extra = ""
        if r.case == "R3":
            hx = r.aux
            extra = f"；卸在 {x} 的队属仓库 {hx}，{y} 驻地到 {hx} 为 {D[(y, hx)]:.0f} km，由 {y} 自取"
        elif r.case == "R4":
            hx, b2 = ast.literal_eval(r.aux)
            extra = f"；先暂存在 {x} 的队属仓库 {hx}，由 {y} 的原批 {b2} 到 {hx} 领回（须在本批回驻地之后出发）"
        elif r.case in ("R5", "R7"):
            extra = f"；{x} 驻地到 {y} 的队属仓库：" + "、".join(f"{h} {D[(x, h)]:.0f} km" for h in H[y])
        unit_share = bool(set(H[x]) & set(H[y]))
        if unit_share and r.case not in ("R1", "R6"):
            extra += f"（注：{x} 与 {y} 在单位层面共用 {'、'.join(sorted(set(H[x]) & set(H[y])))}，但这笔货指定存放在 {r.h if r.dir == '领' else r.h}，与 {x} 不共用，按 X3 口径判定）"
        out += [f"**{k + 1}. 块 {r.block}**：{what}{extra}",
                f"- {x} 的队属仓库：{'、'.join(H[x])}；{y} 的队属仓库：{'、'.join(H[y])}；{x} 这一批保留的外部目标仓库：{'、'.join(tgt) or '无'}",
                f"- 本文判定：**{name}**。原文：“{text}”",
                f"- 就近（参考）：{'是' if near else '否'}",
                "- 是否符合所写情形？　答：", ""]
    out += ["## 其他意见", "", ""]
    (ROOT / "review" / f"human_delegation_{tag}.md").write_text("\n".join(out), encoding="utf-8")
    print(f"写出 review/human_delegation_{tag}.md（{len(moved)} 笔）")


if __name__ == "__main__":
    main()
