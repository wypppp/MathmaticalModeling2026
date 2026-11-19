"""Q2 相关的可证明性质：P5 因果性、P9 报童分位数。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import data, lp, q2  # noqa: E402
from src.sim import execute_day  # noqa: E402


def _chain(L, G, ndays, anchor):
    price, _, _ = data.load_a1()
    fc = q2.P0Forecaster(L, G)
    S0, out = q2.S_INIT, []
    for di in range(ndays):
        Lf, Gf = fc.forecast(di)
        plan = lp.solve_day(price, Lf, Gf, S0=S0, S_end=anchor)
        led = execute_day(plan.q, L[di], G[di], S0, q2.X0Policy(plan, Lf, Gf, price))
        out.append(led)
        S0 = float(led.S[-1])
    return out


def test_causality_prefix_identical():
    """P5：把第 10 天 12:00 以后、以及之后各天的实际值改掉，第 10 天及以前的 q 和 12:00 之前的动作必须完全相同。"""
    _, L, G = data.load_a2()
    anchor = q2.q1_anchor()
    L2, G2 = L.copy(), G.copy()
    k = 72
    rng = np.random.default_rng(0)
    L2[10, k:] *= 1.3; G2[10, k:] *= 0.5
    L2[11:] *= rng.uniform(0.7, 1.3, size=L2[11:].shape)
    a = _chain(L, G, 12, anchor); b = _chain(L2, G2, 12, anchor)
    for di in range(11):
        assert np.array_equal(a[di].b, b[di].b), f"第 {di} 天计划不同"
    for di in range(10):
        assert np.allclose(a[di].c, b[di].c) and np.allclose(a[di].d, b[di].d)
    assert np.allclose(a[10].c[:k], b[10].c[:k]) and np.allclose(a[10].d[:k], b[10].d[:k])
    assert np.allclose(a[10].S[:k + 1], b[10].S[:k + 1])
    assert not np.allclose(a[10].c[k:] - a[10].d[k:], b[10].c[k:] - b[10].d[k:])  # 分叉之后确实不同


def test_newsvendor_quantile():
    """P9：无储能、单时段，min E[p q + 5 p (N-q)+] 的解是 N 的 80% 分位数。"""
    rng = np.random.default_rng(1)
    N = rng.gamma(4.0, 100.0, size=2001)
    qs = np.linspace(0, N.max(), 4001)
    cost = [q + 5 * np.maximum(N - q, 0).mean() for q in qs]
    qstar = qs[int(np.argmin(cost))]
    lo, hi = np.quantile(N, 0.795), np.quantile(N, 0.805)
    assert lo <= qstar <= hi, (qstar, lo, hi)
