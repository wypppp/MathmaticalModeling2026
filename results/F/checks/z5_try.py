"""Z5 试算：去掉 V0 后 (U9,B,A) 的 12 个并列解中按 (N, P) 最小者，问题 3 单起点 + 多起点搜索（启发式，仅供裁决参考）。"""
import sys, time; sys.path.insert(0, 'src')
import pandas as pd, f_blocks as fb, f_p2, f_parse as fp, f_p3
from f_run_p2 import solve_checked
from f_run_p3 import search
cap, D = fp.load_cap(), fp.load_dist(); batches, blocks = fb.build(4)
lv = ("U9", "B", "A")
r0, _, forbid = solve_checked(batches, blocks, cap, D, levels=lv)
r = f_p2.solve(batches, blocks, cap, D, forbid=forbid, levels=lv, alternatives=300)
sols = [r["assign"]] + r["alts"]
tots = [f_p2.summarize(a, batches, blocks, cap)[1] for a in sols]
i = min(range(len(sols)), key=lambda j: (tots[j]["N"], tots[j]["P"]))
a = sols[i]
print("选中并列解", i, "N/P/E/pairs", tots[i]["N"], tots[i]["P"], round(tots[i]["E"], 4), tots[i]["pairs"], flush=True)
main = {k: v for k, v in pd.read_csv('results/F/p2/assign_tie2.csv').set_index('block').option.items()}
import f_run_p3
a2 = f_run_p3.load_assign(__import__('pathlib').Path('results/F/p2/assign_tie2.csv'), blocks)
print("与现主指派（并列 2）不同的块", sorted(k for k in a if a[k] != a2[k]), flush=True)
inst = f_p3.Instance(a, batches, blocks, cap, D)
b0 = inst.baseline(); eb = inst.evaluate(b0)
print(f"孤立下界 τ≥{inst.lb_tau} L≥{inst.lb_L:.3f}；规则基线 τ={eb['tau']} L={eb['L']:.3f} δ={eb['delta']} 可行={eb['feasible']}", flush=True)
ref = dict(l=(inst.lb_tau, inst.lb_L, 0.0), u=(eb['tau'], eb['L'], max(eb['delta'], 5)))
t0 = time.time()
_, _, sol, ev = search(inst, ref, log=lambda *x: None, multistart=True)
print(f"搜索结果 τ={ev['tau']} L={ev['L']:.3f} δ={ev['delta']} V={ev['V']} D={ev['D']} 可行={ev['feasible']}  {time.time()-t0:.0f}s", flush=True)
