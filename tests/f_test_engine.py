"""时间引擎检验：V10（五个手算例）、V11（批 46 算例）。运行：python tests/f_test_engine.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f_blocks as fb  # noqa: E402
import f_engine as fe  # noqa: E402
import f_parse as fp  # noqa: E402

cap, D = fp.load_cap(), fp.load_dist()
batches, blocks = fb.build(4)
res = []


def check(name, cond, msg):
    res.append(bool(cond))
    print("通过" if cond else "失败", name, msg)


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


# V10-① 500 km：8:00 出发，16:00 到
dep, arr = fe.travel((1, 0.0), 500)
check("V10-1", dep == (1, 0.0) and arr[0] == 1 and close(arr[1], 8.0), f"{dep}->{arr}")
# V10-② 短路段：12:00 出发，250 km 恰 16:00 到；多 1 分钟路程（约 1.0417 km）则次日 8:00 出发
_, a1 = fe.travel((1, 4.0), 250)
d2, a2 = fe.travel((1, 4.0), 250 + 62.5 / 60)
check("V10-2", a1[0] == 1 and close(a1[1], 8.0) and d2 == (2, 0.0) and a2[0] == 2 and close(a2[1], 4.0 + 1 / 60),
      f"250km->{a1}; 多1分钟->{d2},{a2}")
# V10-③ 705 km：分两天，次日 8:00 + 3.28h 到；若 10:00 才能走，则推到次日 8:00 出发
_, a3 = fe.travel((1, 0.0), 705)
d4, a4 = fe.travel((1, 2.0), 705)
check("V10-3", a3[0] == 2 and close(a3[1], 3.28) and d4 == (2, 0.0) and a4[0] == 3 and close(a4[1], 3.28), f"{a3}; {d4}->{a4}")
# V10-④ 装 30 台：12 小时，跨两天
wh = fe.Warehouse()
s, e = wh.serve(1, "U3", (1, 0.0), 30)
check("V10-4", s == (1, 0.0) and e[0] == 2 and close(e[1], 4.0) and close(wh.veh[1], 20) and close(wh.veh[2], 10), f"{s}->{e} 日台次 {wh.veh}")
# V10-⑤ 批 13（U6）在 WA：卸 ⌈9.23⌉=10，装 ⌈17.83⌉=18，共 28 台次
b13 = batches[13]
su = sum(k.s(cap, "U6") for k in b13.blocks if k.w == "WA" and k.dir == "交")
sl = sum(k.s(cap, "U6") for k in b13.blocks if k.w == "WA" and k.dir == "领")
check("V10-5", fe.ceil_(su) == 10 and fe.ceil_(sl) == 18 and b13.T0 == 18, f"卸 {su:.4f} 装 {sl:.4f} T0={b13.T0}")

# V11 批 46（U12：WE、WF，卸 WO）
b = batches[46]
se = sum(k.s(cap, "U12") for k in b.blocks if k.w == "WE")
sf = sum(k.s(cap, "U12") for k in b.blocks if k.w == "WF")
own = tuple(fb.H["U12"])
A = fe.Plan(46, "U12", 21, 4, [fe.Step("WE", load={"e": se}), fe.Step("WF", load={"f": sf}),
                               fe.Step("WO", unload={"e": se, "f": sf}), fe.Step("U12")], own)
B = fe.Plan(46, "U12", 21, 4, [fe.Step("WF", load={"f": sf}, leave=["f"]), fe.Step("WE", load={"e": se}),
                               fe.Step("WF", rejoin=True), fe.Step("WO", unload={"e": se, "f": sf}), fe.Step("U12")], own)
# K1 的另一种写法：不装货经过 WF，回来再装
C = fe.Plan(46, "U12", 21, 4, [fe.Step("WF"), fe.Step("WE", load={"e": se}), fe.Step("WF", load={"f": sf}),
                               fe.Step("WO", unload={"e": se, "f": sf}), fe.Step("U12")], own)
out = {}
for name, pl in (("A", A), ("B", B), ("C", C)):
    r = fe.simulate([pl], D)[0][46]
    out[name] = r
    print(f"   路线{name}: D={r.D:.0f} km, 天数={r.tau}, L̄={r.Lbar:.3f}, L={ {g: round(v) for g, v in r.L_groups.items()} }, flags={r.flags}")
    for lg in r.logs:
        print(f"      {lg.node:<4} 到 {fe.fmt(lg.arrive)} 离 {fe.fmt(lg.depart)} 卸{lg.c_unload} 装{lg.c_load} 车上 {lg.onboard_after:.3f}/{lg.moving_T}")
check("V11-A", close(out["A"].D, 1238) and out["A"].tau == 4 and close(out["A"].Lbar, 406.275, 1e-3), f"s_e={se:.6f} s_f={sf:.6f}")
check("V11-B", close(out["B"].D, 926) and out["B"].tau == 3 and close(out["B"].Lbar, 406.275, 1e-3) and not out["B"].flags, "留置写法")
check("V13-例", all(close(out["B"].L_groups[g], out["C"].L_groups[g]) for g in ("e", "f")) and close(out["C"].D, 926),
      "留置写法与“经过后再回来装”的写法，各货组载货距离相同")
sys.exit(0 if all(res) else 1)
