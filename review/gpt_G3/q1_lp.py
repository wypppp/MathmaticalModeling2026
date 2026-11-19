"""Independently solve Q1, with an exact charge/discharge MILP cross-check."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import hstack, lil_matrix

from inputs import ATTACHMENTS, CAP, ETA, SOC_MAX, SOC_MIN, STEPS, attachment1

R1 = 35118.5986
TOL = 1e-6


def solve(price, load, pv, *, fixed_soc=None, exclusive=False):
    n = STEPS
    # Flat blocks: q, charge, discharge, spill, and n+1 SOC boundaries.
    variables = 5 * n + 1
    matrix = lil_matrix((2 * n + 1, variables))
    for t in range(n):
        matrix[t, [t, n + t, 2 * n + t, 3 * n + t]] = [1, -1, 1, -1]
        matrix[n + t, [n + t, 2 * n + t, 4 * n + t, 4 * n + t + 1]] = [
            -ETA, 1 / ETA, -1, 1
        ]
    matrix[2 * n, [4 * n, 5 * n]] = [-1, 1]
    rhs = np.r_[load - pv, np.zeros(n + 1)]
    cost = np.r_[price, np.zeros(variables - n)]
    lower = np.zeros(variables)
    lower[4 * n:] = SOC_MIN
    upper = np.r_[np.full(n, np.inf), np.full(2 * n, CAP),
                  np.full(n, np.inf), np.full(n + 1, SOC_MAX)]
    if fixed_soc is not None:
        lower[4 * n] = upper[4 * n] = fixed_soc

    if exclusive:
        mode = lil_matrix((2 * n, variables + n))
        for t in range(n):
            mode[t, [n + t, variables + t]] = [1, -CAP]
            mode[n + t, [2 * n + t, variables + t]] = [1, CAP]
        result = milp(
            np.r_[cost, np.zeros(n)],
            integrality=np.r_[np.zeros(variables), np.ones(n)],
            bounds=Bounds(np.r_[lower, np.zeros(n)], np.r_[upper, np.ones(n)]),
            constraints=[
                LinearConstraint(hstack([matrix, lil_matrix((2 * n + 1, n))]), rhs, rhs),
                LinearConstraint(mode.tocsr(), -np.inf, np.r_[np.zeros(n), np.full(n, CAP)]),
            ],
            options={"mip_rel_gap": 0},
        )
    else:
        result = linprog(cost, A_eq=matrix.tocsr(), b_eq=rhs,
                         bounds=list(zip(lower, upper)), method="highs")
    if not result.success:
        raise RuntimeError(result.message)

    q, charge, discharge, spill, soc = np.split(result.x[:variables], [n, 2*n, 3*n, 4*n])
    # Cancel any overlap in the relaxed LP without changing SOC or purchased energy.
    if not exclusive:
        cancelled_charge = np.minimum(charge, discharge / ETA**2)
        charge = charge - cancelled_charge
        discharge = discharge - ETA**2 * cancelled_charge
        spill = spill + (1 - ETA**2) * cancelled_charge

    residuals = {
        "balance_kwh": np.max(abs(q + pv + discharge - charge - spill - load)),
        "soc_step_kwh": np.max(abs(np.diff(soc) - ETA * charge + discharge / ETA)),
        "soc_cycle_kwh": abs(soc[0] - soc[-1]),
        "soc_bound_kwh": max(0, SOC_MIN - min(soc), max(soc) - SOC_MAX),
        "power_bound_kwh": max(0, max(charge) - CAP, max(discharge) - CAP),
        "nonnegative_kwh": max(0, -min(q), -min(charge), -min(discharge), -min(spill)),
        "overlap_kwh": max(0, np.max(np.minimum(charge, discharge))),
        "objective_yuan": abs(price @ q - result.fun),
    }
    if max(residuals.values()) > TOL:
        raise RuntimeError(f"Q1 解未通过残差检查：{residuals}")

    return {
        "cost_yuan": result.fun,
        "soc_start_kwh": soc[0],
        "soc_end_kwh": soc[-1],
        "charge_cap_slots": int(np.count_nonzero(charge >= CAP - TOL)),
        "solver_status": result.message,
        "mip_gap": result.mip_gap if exclusive else None,
        "max_residuals": {k: float(v) for k, v in residuals.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attachment1", type=Path, default=ATTACHMENTS / "附件1.xlsx")
    args = parser.parse_args()
    inputs = attachment1(args.attachment1)
    lp = solve(*inputs)
    fixed = solve(*inputs, fixed_soc=6000)
    integer = solve(*inputs, exclusive=True)
    delta = lp["cost_yuan"] - R1
    gap = integer["cost_yuan"] - lp["cost_yuan"]
    penalty = fixed["cost_yuan"] - lp["cost_yuan"]
    print(json.dumps({"lp": lp, "fixed_soc_lp": fixed, "exclusive_milp": integer,
                      "r1_yuan": R1, "lp_minus_r1_yuan": delta,
                      "milp_minus_lp_yuan": gap, "fixed_soc_extra_yuan": penalty},
                     ensure_ascii=False, indent=2))
    return int(abs(delta) > 0.01 or abs(gap) > TOL or integer["mip_gap"] != 0
               or penalty < -TOL)


if __name__ == "__main__":
    raise SystemExit(main())
