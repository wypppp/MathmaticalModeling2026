"""cert5 回归：在 v2.7 实例（results/F/p3_cert4 的 bundle）上、以 v2.7 口径（F_SPEC=v2.7）重跑若干已完成任务，
主口径前沿 {超额τ: 最小超额L̄} 与回放次数须与 f_p3_cert4 的 out/ 逐项一致。运行：F_SPEC=v2.7 python tests/f_test_cert5_legacy.py"""
import os
import pickle
import sys
from pathlib import Path

assert os.environ.get("F_SPEC") == "v2.7", "须在 F_SPEC=v2.7 下运行"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd  # noqa: E402
import f_p3_cert5 as c5  # noqa: E402

base = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "F" / "p3_cert4"
B = pickle.load(open(base / "bundle.pkl", "rb"))
tasks = pd.read_csv(base / "tasks.csv")
done = {p.stem for p in (base / "out").glob("*.csv")}
want = sys.argv[2].split(",") if len(sys.argv) > 2 else ["t2_v3_c1_s0of1", "t2_v18_c1_s0of1"]
pick = tasks[tasks.task.isin(want) & tasks.task.isin(done)]
assert len(pick) == len(want), "指定任务未完成或不存在"
ok = True
for r in pick.itertuples():
    d = B["vecdata"][r.tie, r.vec]
    frs, n = c5.cluster_front(B["insts"][r.tie], d["cls"][r.cluster], d["days"], d["cand"], d["iv"], d["mt"], d["mL"], d["E"], d["budget"],
                              B["WT"], B["WL"], r.sub, r.nsub, B["depth2"])
    old = pd.read_csv(base / "out" / f"{r.task}.csv")
    n_old = int(old.n_sim.fillna(0).sum())
    f_old = {int(x.tex): float(x.lex) for x in old[old.tex.notna()].itertuples()}
    f_new = {k: v[0] for k, v in frs["main"].items()}
    same = n == n_old and f_old.keys() == f_new.keys() and all(abs(f_old[k] - f_new[k]) < 1e-9 for k in f_old)
    ok &= same
    print("通过" if same else "失败", r.task, f"回放 {n}/{n_old}", f"前沿 {len(f_new)}/{len(f_old)}")
sys.exit(0 if ok else 1)
