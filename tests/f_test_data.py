"""F 题第一批检验：V1–V5、V19（evidence.md 预注册）。直接运行：python tests/f_test_data.py

输出 results/F/checks/V1_V5_V19.csv（未舍入的逐批台账）。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_parse as fp  # noqa: E402

cap, D = fp.load_cap(), fp.load_dist()
out, rows = {}, []

# V1 货物总量与逐货号守恒
tot, by_item = {}, {}
for k in (2, 3, 4):
    d = fp.load(k)
    d = d[~d.is_sub].copy()
    d["qty"] = pd.to_numeric(d.qty)
    tot[k] = d.qty.sum()
    by_item[k] = d.groupby("item").qty.sum()
diff = (by_item[2].reindex(by_item[2].index.union(by_item[3].index), fill_value=0)
        - by_item[3].reindex(by_item[2].index.union(by_item[3].index), fill_value=0)).abs().sum()
out["V1"] = (tot[2] == 5971074 and tot[3] == 5971074 and tot[4] == 10727184 and diff == 0,
             f"总量 {tot}，件2/件3 逐货号绝对差之和 {diff}，货种数 {len(by_item[2])}/{len(by_item[3])}/{len(by_item[4])}")

# V2、V3、V4 逐批
agg = {}
n_bad_T = n_bad_P = n_batches = 0
for k in (2, 3, 4):
    d = fp.load(k)
    d = d[~d.is_sub].copy()
    d["qty"] = pd.to_numeric(d.qty)
    sT = sN = sP = uN = uP = 0
    for b, g in d.groupby("batch", sort=True):
        u = g.unit.iloc[0]
        g = g.assign(s=[q / cap.at[it, u] for it, q in zip(g["item"], g.qty)])
        recv, send = g[g.dst_node == u].s.sum(), g[g.src_node == u].s.sum()
        T = math.ceil(max(recv, send) - 1e-9)
        T0 = int(sum(float(x) for x in g.drop_duplicates("T_block")["T"]))
        N0 = int(float(g.N.iloc[0]))
        Praw = g.P.iloc[0]
        P0 = 2 * N0 + 3 + 2 * math.ceil(T0 / 5) if isinstance(Praw, str) and Praw.startswith("=") else int(float(Praw))
        Pf = 2 * N0 + 3 + 2 * math.ceil(T0 / 5)
        Nu, Pu = fb.tnp(T0)
        n_batches += 1
        n_bad_T += T != T0
        n_bad_P += Pf != P0
        sT += T0; sN += N0; sP += P0; uN += Nu; uP += Pu
        rows.append(dict(src=k, batch=b, unit=u, s_recv=recv, s_send=send, T_calc=T, T_tab=T0,
                         N_tab=N0, P_tab=P0, P_formula=Pf, N_unified=Nu, P_unified=Pu))
    agg[k] = (sT, sN, sP, uN, uP)
out["V2"] = (n_bad_T == 0 and n_batches == 105, f"{n_batches} 批，T 不符 {n_bad_T}")
out["V3"] = (n_bad_P == 0, f"P 不符 {n_bad_P}（件2 批3 的人数单元格是公式 =I29*2+5，按公式取值）")
out["V4"] = (agg[2][3:] == (392, 1020) and agg[3][3:] == (374, 963) and agg[4][3:] == (527, 1382),
             f"表列 T/N/P 与统一口径 N/P：件2 {agg[2]}，件3 {agg[3]}，件4 {agg[4]}")

# V5 需求块
batches, blocks = fb.build(4)
n_r = sum(k.dir == "领" for k in blocks)
pairs = sum(len(fb.targets(b)) for b in batches.values())
out["V5"] = (len(batches) == 46 and len(blocks) == 90 and n_r == 72 and pairs == 73,
             f"批 {len(batches)}，块 {len(blocks)}（领 {n_r}、交 {len(blocks) - n_r}），批次-仓库对 {pairs}")


# V19 邻近对
def near_pairs(th):
    n = 0
    for i, a in enumerate(fb.UNITS):
        for b in fb.UNITS[i + 1:]:
            share = set(fb.H[a]) & set(fb.H[b])
            dm = min([D.at[a, w] for w in fb.H[b]] + [D.at[b, w] for w in fb.H[a]])
            n += bool(share) or dm <= th
    return n


np_ = {th: near_pairs(th) for th in (149, 150, 151)}
out["V19"] = (np_ == {149: 13, 150: 15, 151: 15}, f"邻近对数 {np_}")

outdir = ROOT / "results" / "F" / "checks"
outdir.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_csv(outdir / "V1_V5_V19.csv", index=False, encoding="utf-8-sig")
ok = True
for k, (passed, msg) in out.items():
    print(("通过" if passed else "失败"), k, msg)
    ok &= bool(passed)
sys.exit(0 if ok else 1)
