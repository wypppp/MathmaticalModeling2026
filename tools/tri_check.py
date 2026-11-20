"""附件 1 距离矩阵的三角不等式核查：每对节点的表列值与最短中转路径（Floyd）之差。
输出 results/F/checks/tri_violations.csv（每对一行）并打印汇总；用于正文第二章“借道”说明与 X1 的依据。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from f_parse import load_dist  # noqa: E402

D = load_dist()
names = list(D.index)
M = D.loc[names, names].to_numpy(float)
F, via = M.copy(), np.full(M.shape, -1)
for k in range(len(names)):
    alt = F[:, [k]] + F[[k], :]
    better = alt < F - 1e-9
    F, via = np.where(better, alt, F), np.where(better, k, via)
rows = [dict(i=names[i], j=names[j], table=M[i, j], shortest=F[i, j], gap=M[i, j] - F[i, j],
             first_via=names[via[i, j]] if via[i, j] >= 0 else "")
        for i in range(len(names)) for j in range(i + 1, len(names))]
df = pd.DataFrame(rows)
out = ROOT / "results" / "F" / "checks"
out.mkdir(parents=True, exist_ok=True)
df.to_csv(out / "tri_violations.csv", index=False, encoding="utf-8-sig")
v = df[df.gap > 1e-9]
print(f"节点对 {len(df)}，表列值大于中转最短路的 {len(v)} 对（{len(v) / len(df):.1%}）；差值中位数 {v.gap.median():.0f} km，"
      f"最大 {v.gap.max():.0f} km（{v.loc[v.gap.idxmax(), 'i']}–{v.loc[v.gap.idxmax(), 'j']}）；不含 WL 的最大差 {v[(v.i != 'WL') & (v.j != 'WL')].gap.max():.0f} km")
