"""核实 Gemini A5 第 3 轮（代码审计）指出的放松，在已提交的问题 3、4 方案里是否真的发生过。

只读结果台账（results/F/p3、p4 的 steps_main.csv、assign），不调用求解代码；队属仓库归属取 f_blocks.H。
用法：python tools/a5_verify.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")
import f_blocks as fb  # noqa: E402

EPS = 1e-9


def groups(cell):
    if not isinstance(cell, str) or not cell:
        return []
    return [g.split(":")[0] for g in cell.split(";") if g]


def check(tag, steps_path, assign_path, batches_path):
    st = pd.read_csv(steps_path)
    asg = pd.read_csv(assign_path)
    bt = pd.read_csv(batches_path).set_index("batch")
    out = dict(S12=[], LIFO=[], R5=[], S10=[], R4_strict=[], R4_touch=[])
    for b, s in st.groupby("batch"):
        s = s.sort_values("seq").reset_index(drop=True)
        u = s.unit.iloc[0]
        own = set(fb.H[u])
        # S12：自有送交货（从自己可用的队属仓库装、卸到外面）须在到访任何外部仓库作业之前装车
        first_ext = next((i for i, r in s.iterrows() if r.node.startswith("W") and r.node not in own
                          and (groups(r.load) or groups(r.unload))), None)
        for i, r in s.iterrows():
            for g in groups(r.load):
                a, z = g.split(">")
                if a in own and z not in own and first_ext is not None and i > first_ext:
                    out["S12"].append((b, u, g, f"第 {i} 站才装，首个外部作业在第 {first_ext} 站"))
        # S11：多站留置须按相反顺序汇合
        stack = []
        for i, r in s.iterrows():
            if r.rejoin:
                if not stack or stack[-1] != r.node:
                    out["LIFO"].append((b, u, r.node, f"栈 {stack}"))
                if r.node in stack:
                    stack.remove(r.node)
            if isinstance(r.leave, str) and r.leave:
                stack.append(r.node)
        # S10：留置车整日闲置 ≤ 1 天（含汇合车队 16:00 才到的那一天）
        left_end = {}
        for i, r in s.iterrows():
            if r.rejoin and r.node in left_end:
                d0 = left_end.pop(r.node)
                idle = (r.arrive_day - d0 - 1) + (1 if r.arrive_h >= 8 - EPS else 0)
                if idle > 1:
                    out["S10"].append((b, u, r.node, f"留在第 {d0} 天，汇合 {r.arrive_day} 日 h={r.arrive_h:.3f}，整日闲置 {idle}"))
            if isinstance(r.leave, str) and r.leave:
                left_end[r.node] = r.end_day
    for k in asg.itertuples():
        case = getattr(k, "case", "")
        if not isinstance(case, str):
            continue
        beta = int(k.to_batch)
        s = st[st.batch == beta].sort_values("seq").reset_index(drop=True)
        if case == "R5":
            # 先到 h_k 装代交货，之后才到 w_k 代领
            i_h = next((i for i, r in s.iterrows() if r.node == k.h and groups(r.load)), None)
            i_w = next((i for i, r in s.iterrows() if r.node == k.w and any(g.startswith(f"{k.w}>") for g in groups(r.load))), None)
            ok = i_h is not None and i_w is not None and i_h < i_w
            out["R5"].append((k.block, beta, k.owner, k.w, k.h, "先 h_k 后 w_k" if ok else f"顺序不符 h@{i_h} w@{i_w}"))
        if case == "R4":
            import ast
            bp = ast.literal_eval(k.aux)[1] if isinstance(k.aux, str) else None  # aux = (h_x, β′)
            if bp is None or bp not in bt.index:
                continue
            e_beta, s_bp = int(bt.at[beta, "end"]), int(bt.at[bp, "start"])
            if s_bp <= e_beta:
                out["R4_strict"].append((k.block, beta, bp, f"β 结束 {e_beta}，β′ 开始 {s_bp}"))
            if s_bp < e_beta:
                out["R4_touch"].append((k.block, beta, bp))
    print(f"== {tag}")
    for key, v in out.items():
        print(f"  {key}: {len(v)} 条", *(f"\n    {x}" for x in v))
    return out


if __name__ == "__main__":
    check("问题 3", ROOT / "results/F/p3/steps_main.csv", ROOT / "results/F/p2/assign_main.csv", ROOT / "results/F/p3/batches_main.csv")
    check("问题 4", ROOT / "results/F/p4/steps_main.csv", ROOT / "results/F/p4/assign_main.csv", ROOT / "results/F/p4/batches_main.csv")
