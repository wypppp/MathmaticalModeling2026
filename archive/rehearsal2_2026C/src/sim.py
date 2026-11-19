"""因果回测器：按 spec §3.2 的顺序逐时段执行一天。

每个时段：购电 b_t 已锁定 → 观测本时段 L_t、G_t → 策略给出储能净输出 u（放电为正）
→ 裁剪到功率与 SOC 可行域 → 富余电量优先充入储能，或减少放电（弱占优：
不增加任何费用）→ 剩余缺口 e 按 5 倍电价紧急购入，仍有富余则记为 w（无收益消纳）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SMIN, SMAX = 1200.0, 10800.0
PMAX = 5000.0 / 6.0  # 每时段 kWh
ETA = 0.9
EMERG = 5.0


@dataclass
class DayLedger:
    b: np.ndarray
    L: np.ndarray
    G: np.ndarray
    c: np.ndarray = field(default=None)
    d: np.ndarray = field(default=None)
    e: np.ndarray = field(default=None)
    w: np.ndarray = field(default=None)
    S: np.ndarray = field(default=None)  # 145 个，S[0] 为 0:00

    def cost(self, price: np.ndarray, b_cost: np.ndarray | None = None) -> float:
        """普通购电费 + 紧急购电费。b_cost 用于 Q3（已含调整费用的普通费，逐时段）。"""
        base = (price * self.b).sum() if b_cost is None else b_cost.sum()
        return float(base + EMERG * (price * self.e).sum())


def battery_limits(S: float) -> tuple[float, float]:
    """返回 (最大放电量, 最大充电量)，均为母线侧 kWh。"""
    max_d = max(0.0, min(PMAX, (S - SMIN) * ETA))
    max_c = max(0.0, min(PMAX, (SMAX - S) / ETA))
    return max_d, max_c


def execute_day(b, L, G, S0, policy) -> DayLedger:
    """policy(t, S, b_t, L_t, G_t) -> 期望净输出 u（kWh，放电为正）。只能用到当前及过去的信息。"""
    b, L, G = (np.asarray(x, float) for x in (b, L, G))
    n = len(b)
    c, d, e, w = (np.zeros(n) for _ in range(4))
    S = np.empty(n + 1)
    S[0] = S0
    for t in range(n):
        max_d, max_c = battery_limits(S[t])
        need = L[t] - G[t] - b[t]  # 储能需要提供的净输出
        u = float(np.clip(policy(t, S[t], b[t], L[t], G[t]), -max_c, max_d))
        if u > need:  # 有富余：减少放电或增加充电，直到吸收完或充满
            u = max(need, -max_c)
        if u >= 0:
            d[t] = u
        else:
            c[t] = -u
        gap = need - u
        e[t] = max(0.0, gap)
        w[t] = max(0.0, -gap)
        S[t + 1] = S[t] + ETA * c[t] - d[t] / ETA
        # 数值保护：只吸收 1e-7 以内的浮点越界，真正的越界留给检查器报错
        clipped = min(max(S[t + 1], SMIN), SMAX)
        if abs(S[t + 1] - clipped) < 1e-7:
            S[t + 1] = clipped
    return DayLedger(b=b, L=L, G=G, c=c, d=d, e=e, w=w, S=S)
