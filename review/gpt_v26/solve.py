"""Run from any directory. No reference assignments are read."""

from collections import defaultdict
from dataclasses import dataclass, asdict
from fractions import Fraction as F
from functools import cache
import json
from math import lcm

from ortools.sat.python import cp_model as cp
from inputs import OUT, H, blocks, keys, requests, dist, cap, original_trucks

m = cp.CpModel()
solver = cp.CpSolver()
solver.parameters.num_workers = 1
solver.parameters.random_seed = 0
own = [m.new_bool_var(f"own{i}") for i in range(len(keys))]
targets, unloads, retained = defaultdict(list), defaultdict(list), defaultdict(list)
for i, (b, w, d, h) in enumerate(keys):
    retained[b].append(own[i])
    if w not in H[requests[b][0]]:
        targets[b, w].append(own[i])
    if d == "发":
        unloads[b, h].append(own[i])


def indicator(lits):
    v = m.new_bool_var("")
    m.add_max_equality(v, lits)
    return v


live = {b: indicator(v) for b, v in retained.items()}
target = {key: indicator(v) for key, v in targets.items()}
unload = {key: indicator(v) for key, v in unloads.items()}
for b in requests:
    m.add(sum(v for (c, w), v in target.items() if c == b) <= 4)


@dataclass(frozen=True)
class Choice:
    i: int
    batch: int
    rule: str
    start: str
    end: str
    back: int = 0
    reverse: bool = False


@cache
def size(i, b):
    return sum(F(q, cap[item, requests[b][0]]) for item, q in blocks[keys[i]])


choices = {}
by_block = defaultdict(list)
by_side = defaultdict(list)
disjoint = defaultdict(list)
cost = []
priority = []
partners = defaultdict(list)
needs_partner = []
for i, (b, w, d, h) in enumerate(keys):
    y, a, e = requests[b]
    for c, (x, ac, ec) in requests.items():

        def option(rule, start, end, conditions=(), back=0, reverse=False):
            k = Choice(i, c, rule, start, end, back, reverse)
            v = own[i] if rule == "own" else m.new_bool_var("")
            choices[k] = v
            by_block[i].append(v)
            for cond in conditions:
                m.add_implication(v, cond)
            pickup = d == "发" and not reverse
            by_side[c, pickup].append((size(i, c), v))
            if back:
                by_side[back, True].append((size(i, back), v))
            if rule != "own":
                cost.append((size(i, c), v))
                if y == "U9":
                    priority.append(v)
                if max(a - 6, ac - 6) > min(e, ec):
                    disjoint[b, c].append(v)
                if not pickup:
                    partners[c, y, start].append(v)
                if rule == "R5":
                    needs_partner.append((v, (c, y, h)))

        if b == c:
            option("own", w if d == "发" else h, h if d == "发" else w)
        if y == x or (y == "U9" and x != "U6"):
            continue
        # Deliveries, including reversal of an internal pickup.
        reverse = d == "发"
        start, end = (w, h) if reverse else (h, w)
        if (not reverse or w in set.union(*H.values())) and (c, end) in target:
            need = [target[c, end]]
            if start in H[x]:
                option("R6", start, end, need, reverse=reverse)
            else:
                if dist[x, start] <= 150:
                    option("R7", start, end, need, reverse=reverse)
                if (c, start) in target:
                    option("R8", start, end, need + [target[c, start]], reverse=reverse)
        if d != "发" or (c, w) not in target:
            continue
        need = [target[c, w]]
        if h in H[x]:
            option("R1", w, h, need)
            continue
        if (c, h) in target:
            option("R2", w, h, need + [target[c, h]])
            need = need + [target[c, h].Not()]
        if dist[x, h] <= 150:
            option("R5", w, h, need)
        for depot in sorted(H[x]):
            if (c, depot) not in unload:
                continue
            at = need + [unload[c, depot]]
            if dist[y, depot] <= 150:
                option("R3", w, depot, at)
            for back, (unit, _, latest) in requests.items():
                if unit == y and ac - 6 <= latest and (back, depot) in target:
                    option("R4", w, depot, at + [target[back, depot]], back)
    m.add_exactly_one(by_block[i])
for v, key in needs_partner:
    m.add_bool_or(partners[key]).only_enforce_if(v)

limits = {b: min(30, t + 3) for b, t in original_trucks.items()}
scale = 10**6
for (b, _), terms in by_side.items():
    m.add(sum(int(q * scale) * v for q, v in terms) <= limits[b] * scale)

log = []


def solve(label, allow_end=False):
    while True:
        status = solver.solve(m)
        if allow_end and status == cp.INFEASIBLE:
            log.append([label, "INFEASIBLE", None])
            return False
        assert status == cp.OPTIMAL, solver.status_name(status)
        valid = True
        for (b, _), terms in by_side.items():
            used = [(q, v) for q, v in terms if solver.value(v)]
            if sum(q for q, v in used) > limits[b]:
                m.add_bool_or([v.Not() for q, v in used])
                valid = False
        if valid:
            return True


def lock(label, expr, maximize=False):
    (m.maximize if maximize else m.minimize)(expr)
    solve(label)
    value = solver.value(expr)
    m.add(expr == value)
    log.append([label, "OPTIMAL", value])
    return value


lock("U9", sum(priority), True)
lock("B", sum(live.values()))
# The rounded objective only narrows the search. At most 90 selected costs
# each lose less than one integer unit. Keep every possible exact minimizer.
rough = sum(int(q * scale) * v for q, v in cost)
m.minimize(rough)
solve("rough")
upper = sum(q for q, v in cost if solver.value(v))
m.add(rough <= int(upper * scale))
den = lcm(*(q.denominator for q, v in cost))
coeff = [int(q * den) for q, v in cost]
digits = []
carry = 0
base = 10000
while any(coeff):
    digit = m.new_int_var(0, base - 1, "digit")
    nxt = m.new_int_var(0, len(cost) + 1, "carry")
    m.add(
        sum((n % base) * v for n, (q, v) in zip(coeff, cost)) + carry
        == digit + base * nxt
    )
    digits.append(digit)
    carry = nxt
    coeff = [n // base for n in coeff]
digits.append(carry)
for j in reversed(range(len(digits))):
    lock(f"A_digit_{j}", digits[j])
lock("V0", sum(indicator(v) for v in disjoint.values()))
m.clear_objective()

solutions = []
while solve("enumerate", True):
    picked = sorted(
        (k for k, v in choices.items() if solver.value(v)), key=lambda k: k.i
    )
    assert len(picked) == len(keys) == 90
    solutions.append([asdict(k) for k in picked])

    # Cut the complete block assignment, including auxiliary R4 decisions.
    # Alternative equivalent rule labels should not duplicate a destination.
    def destination(k):
        return k.i, k.batch, k.start, k.end, k.back, k.reverse

    signature = set(map(destination, picked))
    m.add(sum(v for k, v in choices.items() if destination(k) in signature) <= 89)
    log.append(["assignment", "OPTIMAL", len(solutions)])
(OUT / "solutions.json").write_text(
    json.dumps(solutions, ensure_ascii=False, indent=1) + "\n"
)
(OUT / "solver_log.json").write_text(
    json.dumps(dict(base=base, denominator=den, steps=log), indent=2) + "\n"
)
print(log)
