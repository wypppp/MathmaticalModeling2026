"""裁 Z2（R47）：证书能否搬到“删去 H13”口径的静态判别。
对每个并列指派、每个出发日向量（δ ≤ dmax 全部）：用证书自己的 E、候选集 cand、区间 iv，
数每个 (仓库 W, 日 t) 上“可能在 W 作业、且区间含 t”的不同单位；若某 (W,t) ≥ 4 支且其中有人以 W 为自用队属仓，记为“可能受影响”。
无受影响向量 ⇒ 两种口径下证书枚举的每个被接受组合回放逐步相同（20 台次由 8 小时排队自动满足；3 支只有 ≥4 支同仓同日才起作用）。"""
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"d:\WYP\MM2026\MathmaticalModeling2026")
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa
import f_p3_cert2 as c2  # noqa
import f_p3_cert3 as c3  # noqa

R, insts, pick, inc, ev, z, V = c3.setup()
print(f"z* = {z:.12f}  V = {V}  指派 {list(insts)}  主方案指派 {pick}")
for t, inst in insts.items():
    p = c3.plan(inst, z)
    reps, _ = c2.collapse(inst)
    by_d = defaultdict(lambda: [0, 0, 0])  # δ -> [向量数, E≥0 的向量数, 可能受影响的向量数]
    worst = []
    for vi, v in enumerate(p["vecs"]):
        dlt, budget, E, _ = c3.vec_params(inst, v, z, p["off"])
        by_d[dlt][0] += 1
        if E < 0:
            continue
        by_d[dlt][1] += 1
        cls, cand, iv, ok = c2.clusters(inst, v, E, p["mt"], reps)
        cnt = defaultdict(set)
        for b in inst.ids:
            u = inst.batches[b].unit
            for w in c2.ops_nodes(inst, b, cand[b]):
                if not str(w).startswith("W"):
                    continue
                for d in range(iv[b][0], iv[b][1] + 1):
                    cnt[w, d].add(u)
        hit = [(w, d, sorted(us)) for (w, d), us in cnt.items() if len(us) >= 4 and any(w in fb.H[x] for x in us)]
        mx = max((len(us) for us in cnt.values()), default=0)
        if hit:
            by_d[dlt][2] += 1
            if len(worst) < 5:
                worst.append((vi, dlt, E, hit[:3]))
    print(f"指派 {t}: dmax = {p['dmax']}，向量 {len(p['vecs'])}（complete={p['complete']}）")
    for d, (n, ne, nh) in sorted(by_d.items()):
        print(f"  δ={d}: 向量 {n}，E≥0 {ne}，可能受影响 {nh}")
    for w in worst:
        print("   例：", w)
