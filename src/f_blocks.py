"""F 题：把批次表（附件 2/4）拆成需求块（spec v1.1 §3.1），并给出静态可行转移（§5.2 R1–R8）。

需求块 = 同一原始批次中 (仓库 w, 方向 dir, 存放仓库 h) 相同的全部货物行。
- dir='领'：货从 w 到 h；dir='交'：货从 h 到 w。
- 内部互转：w 是别的单位的队属仓库（inner=True）。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import pandas as pd

import f_parse as fp

UNITS = [f"U{i}" for i in range(1, 13)]
TEAM_WH = ["WO", "WP", "WQ", "WR", "WS", "WT", "WU"]
H = fp.OWN_WH  # 单位 -> 可用队属仓库
NEAR = 150


def day(md) -> int:
    """(月,日) -> 日序号，4/1 = 1。"""
    m, d = md
    return {4: 0, 5: 30, 6: 61}[m] + d


@dataclass
class Block:
    id: int
    batch: int
    owner: str
    w: str
    dir: str  # 领 / 交
    h: str
    inner: bool
    items: dict = field(default_factory=dict)  # 货物 -> 数量
    remark: str = ""

    def s(self, cap: pd.DataFrame, unit: str) -> float:
        return sum(q / cap.at[d, unit] for d, q in self.items.items())


@dataclass
class Batch:
    id: int
    unit: str
    a: int
    e: int
    T0: int
    N0: int
    P0: int
    blocks: list = field(default_factory=list)


def _storage(unit: str, remark: str) -> str | None:
    m = re.search(r"(?:存放至|放置于)(W[A-Z])", remark or "")
    if m:
        return m.group(1)
    m = re.search(r"从(W[A-Z])装载", remark or "")
    if m:
        return m.group(1)
    return H[unit][0] if len(H[unit]) == 1 else None


def build(k: int = 4):
    """返回 (batches: dict[int, Batch], blocks: list[Block])。"""
    df = fp.load(k)
    df = df[~df.is_sub].copy()
    df["qty"] = pd.to_numeric(df.qty)
    batches, blocks = {}, []
    for b, g in df.groupby("batch", sort=True):
        u = g.unit.iloc[0]
        T0 = int(sum(float(x) for x in g.drop_duplicates("T_block")["T"]))
        s, e = eval(str(g.start.iloc[0])), eval(str(g.end.iloc[0]))
        try:
            P0 = int(float(g.P.iloc[0]))
        except (TypeError, ValueError):
            P0 = -1
        bt = Batch(int(b), u, day(s), day(e), T0, int(float(g.N.iloc[0])), P0)
        groups: dict = {}
        for _, r in g.iterrows():
            rm = "" if pd.isna(r.remark) else str(r.remark)
            if r.dst_node == u:
                d_, w = "领", r.src_node
            elif r.src_node == u:
                d_, w = "交", r.dst_node
            else:
                raise ValueError(f"批{b} 行{r.row}: 收发双方不含执行单位 {r.flow}")
            if w in UNITS:  # 附件2 的内部互转写成 U8（发）-U7（收）：取对方的主队属仓库
                w = H[w][0]
            h = _storage(u, rm)
            groups.setdefault((w, d_, h), []).append((r["item"], float(r.qty), rm))
        for (w, d_, h), rows in groups.items():
            items: dict = {}
            for it, q, _ in rows:
                items[it] = items.get(it, 0.0) + q
            blk = Block(len(blocks), int(b), u, w, d_, h, w in TEAM_WH,
                        items, "；".join(sorted({x[2] for x in rows if x[2]})))
            blocks.append(blk)
            bt.blocks.append(blk)
        batches[int(b)] = bt
    return batches, blocks


def targets(bt: Batch) -> set:
    """原始批次的目标仓库集（术语 5）：去掉执行单位可用的队属仓库。"""
    return {k.w for k in bt.blocks} - set(H[bt.unit])


def feasible_cases(k: Block, bt: Batch, batches: dict, dist: pd.DataFrame) -> list:
    """块 k 转给批次 bt（另一单位）时静态可用的情形编号列表（以 bt 的原始目标仓库为 W^own 上界）。"""
    x, y = bt.unit, k.owner
    if x == y or k.h is None:
        return []
    if y == "U9" and x != "U6":
        return []
    W = targets(bt)
    if k.w not in W:
        return []
    out = []
    own_unload = {q.h for q in bt.blocks if q.dir == "领" and q.h in H[x]}
    if k.dir == "领":
        if k.h in H[x]:
            out.append("R1")
        elif k.h in W:
            out.append("R2")
        else:
            if any(dist.at[y, hx] <= NEAR for hx in own_unload):
                out.append("R3")
            for b2 in batches.values():
                if b2.unit == y and (own_unload & targets(b2)) and bt.a - 6 <= b2.e:
                    out.append(f"R4(批{b2.id})")
            if dist.at[x, k.h] <= NEAR:
                out.append("R5*")  # 还需 bt 同时为 y 代交一个从同一 h 出发的块
    else:
        if k.h in H[x]:
            out.append("R6")
        elif k.h in W:
            out.append("R8")
        elif dist.at[x, k.h] <= NEAR:
            out.append("R7")
    return out


def tnp(T: int):
    """spec §4.1：总车数与人数。"""
    N = T + 1 + (1 if T <= 20 else 2) + min(2, math.ceil(T / 10))
    return N, 2 * N + 3 + 2 * math.ceil(T / 5)
