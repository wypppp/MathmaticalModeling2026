"""独立检查器：只依赖台账与输入，不调用回测器或求解器代码（evidence P1–P4）。"""
from __future__ import annotations

import numpy as np

_SMIN, _SMAX, _ETA = 1200.0, 10800.0, 0.9
_P = 5000.0 / 6.0


def check_ledger(b, L, G, c, d, e, w, S, price, reported_cost=None, b_cost=None, tol=1e-6):
    """返回违规信息列表；为空表示通过。"""
    errs = []
    b, L, G, c, d, e, w, S, price = (np.asarray(x, float) for x in (b, L, G, c, d, e, w, S, price))
    n = len(b)
    if len(S) != n + 1:
        errs.append("S 长度应为 n+1")
        return errs
    # P1 储能台账
    rec = S[:-1] + _ETA * c - d / _ETA
    if np.max(np.abs(rec - S[1:])) > tol:
        errs.append(f"P1 SOC 递推误差 {np.max(np.abs(rec - S[1:])):.3e}")
    if S.min() < _SMIN - tol or S.max() > _SMAX + tol:
        errs.append(f"P1 SOC 越界 [{S.min():.3f}, {S.max():.3f}]")
    for name, x in (("c", c), ("d", d)):
        if x.min() < -tol or x.max() > _P + tol:
            errs.append(f"P1 {name} 越界 [{x.min():.4f}, {x.max():.4f}]")
    if np.max(np.minimum(c, d)) > tol:
        errs.append(f"P1 同时充放 {np.max(np.minimum(c, d)):.3e}")
    # P2 平衡
    bal = b + e + G + d - c - w - L
    if np.max(np.abs(bal)) > tol:
        errs.append(f"P2 平衡误差 {np.max(np.abs(bal)):.3e}")
    if min(e.min(), w.min(), b.min()) < -tol:
        errs.append("P2 存在负的 b/e/w")
    if np.max(np.minimum(e, w)) > tol:
        errs.append("P2 同一时段既有紧急购电又有富余")
    # P3 紧急购电量等于剩余缺口
    gap = np.maximum(0.0, L - G - b - d + c)
    if np.max(np.abs(gap - e)) > tol:
        errs.append(f"P3 紧急购电量与缺口不符 {np.max(np.abs(gap - e)):.3e}")
    # P4 费用
    if reported_cost is not None:
        base = (price * b).sum() if b_cost is None else np.asarray(b_cost, float).sum()
        cost = base + 5.0 * (price * e).sum()
        if abs(cost - reported_cost) > max(tol, 1e-9 * abs(cost)) and abs(cost - reported_cost) > 1e-6:
            errs.append(f"P4 费用不符：重算 {cost:.6f}，报告 {reported_cost:.6f}")
    return errs
