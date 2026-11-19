"""确定性日调度 LP / MILP（Q1、Q2 计划器、神谕下界共用）。

变量顺序：q(n)、c(n)、d(n)、S(n+1)。目标 min Σ p·q。
约束：S_{t+1} = S_t + η c_t − d_t/η；q + d − c ≥ L − G（允许富余消纳）；
      0 ≤ c,d ≤ pmax；smin ≤ S ≤ smax；q ≥ 0。
初值：S0=None 表示自由（取值 smin–smax）。日末：'cyclic'（S_n=S_0）、
      数值 x（S_n = x）、('ge', x)（S_n ≥ x）、None（不约束）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack, vstack

from .sim import ETA, PMAX, SMAX, SMIN


@dataclass
class LPResult:
    cost: float
    q: np.ndarray
    c: np.ndarray
    d: np.ndarray
    S: np.ndarray
    status: str
    soc_dual: np.ndarray | None = None  # SOC 递推等式的对偶值（元/kWh）
    mip_gap: float | None = None


def _build(p, L, G, S0, S_end, eta, pmax, smin, smax):
    n = len(p)
    nq, nc, nd, ns = n, n, n, n + 1
    N = nq + nc + nd + ns
    iq, ic, idd, isS = 0, n, 2 * n, 3 * n
    # SOC 递推：S_{t+1} - S_t - eta c_t + d_t/eta = 0
    r, cidx, v = [], [], []
    for t in range(n):
        r += [t, t, t, t]
        cidx += [isS + t + 1, isS + t, ic + t, idd + t]
        v += [1.0, -1.0, -eta, 1.0 / eta]
    Aeq = coo_matrix((v, (r, cidx)), shape=(n, N)).tocsr()
    beq = np.zeros(n)
    extra_eq, extra_b = [], []
    if S_end == "cyclic":
        row = np.zeros(N); row[isS + n] = 1; row[isS] = -1
        extra_eq.append(row); extra_b.append(0.0)
    elif isinstance(S_end, (int, float)):
        row = np.zeros(N); row[isS + n] = 1
        extra_eq.append(row); extra_b.append(float(S_end))
    if extra_eq:
        Aeq = vstack([Aeq, csr_matrix(np.array(extra_eq))]).tocsr()
        beq = np.concatenate([beq, extra_b])
    # 平衡：-q - d + c <= G - L
    r, cidx, v = [], [], []
    for t in range(n):
        r += [t, t, t]; cidx += [iq + t, idd + t, ic + t]; v += [-1.0, -1.0, 1.0]
    Aub = coo_matrix((v, (r, cidx)), shape=(n, N)).tocsr()
    bub = np.asarray(G, float) - np.asarray(L, float)
    if isinstance(S_end, tuple) and S_end[0] == "ge":
        row = np.zeros(N); row[isS + n] = -1
        Aub = vstack([Aub, csr_matrix(row)]).tocsr(); bub = np.concatenate([bub, [-S_end[1]]])
    lb = np.zeros(N); ub = np.full(N, np.inf)
    ub[ic:ic + n] = pmax; ub[idd:idd + n] = pmax
    lb[isS:] = smin; ub[isS:] = smax
    if S0 is not None:
        lb[isS] = ub[isS] = float(S0)
    cvec = np.zeros(N); cvec[:n] = p
    return cvec, Aeq, beq, Aub, bub, lb, ub, (iq, ic, idd, isS, n)


def solve_day(p, L, G, S0=None, S_end="cyclic", eta=ETA, pmax=PMAX, smin=SMIN, smax=SMAX,
              lexicographic=True) -> LPResult:
    cvec, Aeq, beq, Aub, bub, lb, ub, (iq, ic, idd, isS, n) = _build(p, L, G, S0, S_end, eta, pmax, smin, smax)
    res = linprog(cvec, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=list(zip(lb, ub)), method="highs")
    if res.status != 0:
        return LPResult(np.nan, *(np.full(n, np.nan) for _ in range(3)), np.full(n + 1, np.nan), res.message)
    duals = res.eqlin.marginals[:n].copy()
    x = res.x
    cost = float(res.fun)
    if lexicographic:  # 第二阶段：在最优费用面上最小化充放吞吐量，得到唯一、干净的轨迹
        tol = 1e-6  # 绝对容差（元），避免第二阶段抬高费用
        c2 = np.zeros_like(cvec); c2[ic:ic + n] = 1.0; c2[idd:idd + n] = 1.0
        Aub2 = vstack([Aub, csr_matrix(cvec)]).tocsr(); bub2 = np.concatenate([bub, [cost + tol]])
        res2 = linprog(c2, A_ub=Aub2, b_ub=bub2, A_eq=Aeq, b_eq=beq, bounds=list(zip(lb, ub)), method="highs")
        if res2.status == 0:
            x = res2.x
    q, c, d, S = x[iq:iq + n], x[ic:ic + n], x[idd:idd + n], x[isS:isS + n + 1]
    q = np.maximum(q, 0.0); c = np.maximum(c, 0.0); d = np.maximum(d, 0.0)
    return LPResult(float(p @ q), q, c, d, S, "optimal", soc_dual=duals)


def solve_day_milp(p, L, G, S0=None, S_end="cyclic", eta=ETA, pmax=PMAX, smin=SMIN, smax=SMAX) -> LPResult:
    """加入充放互斥 0-1 变量的 MILP，用于校验 LP（evidence P6）。"""
    cvec, Aeq, beq, Aub, bub, lb, ub, (iq, ic, idd, isS, n) = _build(p, L, G, S0, S_end, eta, pmax, smin, smax)
    N = len(cvec)
    # 追加 z_t：c_t <= pmax z_t ; d_t <= pmax (1 - z_t)
    Z = csr_matrix((n, n))
    r, cidx, v = [], [], []
    for t in range(n):
        r += [t, t]; cidx += [ic + t, N + t]; v += [1.0, -pmax]
    A1 = coo_matrix((v, (r, cidx)), shape=(n, N + n)).tocsr()
    r, cidx, v = [], [], []
    for t in range(n):
        r += [t, t]; cidx += [idd + t, N + t]; v += [1.0, pmax]
    A2 = coo_matrix((v, (r, cidx)), shape=(n, N + n)).tocsr()
    Aeq2 = hstack([Aeq, csr_matrix((Aeq.shape[0], n))]).tocsr()
    Aub2 = hstack([Aub, csr_matrix((Aub.shape[0], n))]).tocsr()
    cons = [LinearConstraint(Aeq2, beq, beq), LinearConstraint(Aub2, -np.inf, bub),
            LinearConstraint(A1, -np.inf, 0.0), LinearConstraint(A2, -np.inf, pmax)]
    c_full = np.concatenate([cvec, np.zeros(n)])
    integ = np.concatenate([np.zeros(N), np.ones(n)])
    bnds = Bounds(np.concatenate([lb, np.zeros(n)]), np.concatenate([ub, np.ones(n)]))
    res = milp(c_full, constraints=cons, integrality=integ, bounds=bnds, options={"mip_rel_gap": 0.0})
    x = res.x
    q, c, d, S = x[iq:iq + n], x[ic:ic + n], x[idd:idd + n], x[isS:isS + n + 1]
    gap = getattr(res, "mip_gap", None)
    return LPResult(float(res.fun), q, c, d, S, res.message, mip_gap=gap)
