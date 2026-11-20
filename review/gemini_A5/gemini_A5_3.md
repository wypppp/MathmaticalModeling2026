
逐行核对 `src/f_*.py`、`tools/f_check.py` 与 `spec.md`（v2.2）后，发现的问题按性质分为四类整理如下：

---

### 一、偷偷放松或漏查 spec 硬约束

1. **§5.2 R5（路线顺序）**

   - **代码位置**：`f_routes.py` `enumerate_routes`；`f_p3.py` `Instance.evaluate`；`f_p4.py`；`tools/f_check.py`
   - **问题**：spec 明确要求 R5“**路线上先到 $h_k$ 装代交货，之后才到 $w_k$ 代领**”。但 `enumerate_routes` 只把 R5 的代领货组 `(w_k > h_k)` 和代交货组 `(h_k > w_交)` 一起放进 `pending`，既不强制先到 $h_k$、后到 $w_k$，各评价函数与检查器也完全不查这一先后顺序，车队可以先到 $w_k$ 装代领货再回 $h_k$ 卸代领并装代交。
2. **§5.3 S11（多站留置“按相反顺序逐站汇合”）**

   - **代码位置**：`f_routes.py` `enumerate_routes`（`cand` 与 `rejoin = n in lf`）；`f_p3.py` `Instance.evaluate`；`tools/f_check.py` `main`
   - **问题**：spec 要求“可以在多个站留置，**按相反顺序逐站汇合**”（LIFO 栈序）。但代码全部用无序集合/字典 `left` 维护留置站，只要后来全部回到过即可；当在一趟中先后在 A、B 两站留置时，代码允许先回 A 汇合、再回 B 汇合，放松了汇合顺序约束。
3. **§5.3 S12（批次流程顺序）**

   - **代码位置**：`f_routes.py` `enumerate_routes`（`cand` 生成）；`tools/f_check.py`
   - **问题**：spec S12（标为硬约束）规定“自有送交货在出发后先到其所在的队属仓库装车；……接领的货最后卸到各自的卸货仓库”。`enumerate_routes` 在驻地出发时把所有待装站点 `{g.load}` 直接并入候选集，允许执行单位先去外仓接领、再回己方队属仓库卸领货同时装自有送交货、最后再去送交（先接领后装自有送交、中途卸领货），未被求解器或检查器禁止。
4. **§5.2 R4（到达时刻与卸完时刻先后）**

   - **代码位置**：`f_p3.py` `Instance.evaluate`（`for kid, be, br, ... in self.r4:`）
   - **问题**：spec R4 要求“$\beta'$ **到达** $h_x$ 的时刻 $\ge \beta$ 在 $h_x$ 卸完这批货的时刻”。但 `f_p3.py` 取的是 `t_ld = next(lg.start ...)`（**开始装卸时刻 `lg.start`**），而不是 `lg.arrive`。若 $\beta'$ 在 $\beta$ 卸完前就已到达 $h_x$、仅因排队等到 $\beta$ 卸完后才开始装车，`f_p3.py` 会误判合规，偷偷放松了 R4（注：`tools/f_check.py` 正确使用了 `st["arrive"]`，故一旦触发就会被独立检查器拦下）。
5. **§5.3 S10（留置等待 $\le 1$ 天在 `16:00` 到站时的边界漏判）**

   - **代码位置**：`f_routes.py` `evaluate`；`f_p3.py` `Instance.evaluate`；`tools/f_check.py` `main`
   - **问题**：三处均用 `lg.arrive[0] - left_at.pop(st.node) - 1 > 1` 判定留置整日闲置天数。若留置在第 10 天结束、汇合车队于第 12 天 **`16:00`（`arrive[1] >= 8.0 - EPS`）** 才到达该站，则无论第 12 天是否有作业，都要等到第 13 天 `8:00` 才能工作或出发——留在原地的车辆在第 11 天和第 12 天都整天既不作业也不行驶（共 2 天 $> 1$ 天），但 `12 - 10 - 1 = 1` 会逃过 S10 检验（对比同文件对“排队”正确判断了 `arrive[1] < 1e-9`，对“留置”漏了 `arrive[1] >= 8.0 - 1e-9`）。
6. **§5.1 C1（$|W_\beta| \le 4$）与 §13 C6（U9 优先最大量交 U6）**

   - **代码位置**：`f_p2.py` `solve`；`f_p4.py` `P4.static_ok`；`f_run_p4.py`；`f_run_extra.py`
   - **问题**：① `f_p2.py` 与 `f_p4.py` 均未显式添加 `|W_β| ≤ 4` 约束（仅隐含依赖 $W_\beta \subseteq W_b^0$ 及附件 4 原始批次本身 $\le 4$ 个仓库）；② `f_run_p4.py` 与 `f_run_extra.py` 在问题 4 搜索中直接硬编码 `u9_min = 5`，`P4.static_ok` 只检查 `u9 >= u9_min` 而非动态保证“硬约束下 U9→U6 块数最大”（若在联合邻域中存在可交 6 块的方案则放松了 C6；在 `r3_study` 禁用 R3 时若最大可交块数改变，硬编码 `5` 会误判）。

---

### 二、单位、口径与计算公式不一致

7. **§4.1 运力 $T_\beta$ 与 §2 A6“收/发”口径（`f_p2.py` vs `f_routes.py` / `f_export.py` / `f_check.py`）**

   - **代码位置**：`f_routes.py` `batch_groups`、`batch_T`、`_is_send`；`f_export.py` `write_p2`；`tools/f_check.py` `is_send`
   - **问题**：`f_p2.py` 严格按原始块方向 `k.dir` 区分领/交两侧；但存在两类不一致：
     1. **同货组角色混杂**：`f_routes.py` 先按 `(load, unload)` 合并成 `Group`。若同一 `(w, h)` 既包含执行单位的自有“领”（内部互转）又包含代其他单位的 R8“代交”（例如 $U_x$ 从 $W_R$ 领货到 $W_O$、同时代 $U_4$ 从 $W_R$ 送货到 $W_O$），`_is_send` 因 `roles = {"own", "代交"}` 且 `g.load ∉ own` 而返回 `False`，把该“代交”车数错划到“领”侧，导致 `f_routes.batch_T` 与 `f_p2` 算出的 $T_\beta$ 不一致。
     2. **多可用仓库内部互转到己方另一仓库**：若执行单位有多个可用队属仓库（如 U7、U11），自身送交块的目的地恰在 `H[x]` 内（`g.load in own and g.unload in own`），`f_routes._is_send`、`f_check.is_send` 会将其误判为“领”侧，而 `f_export.write_p2` 的 `if g.load in own and g.unload not in own or role == "代交":` 会将其错输出成在 `g.load` 发、而非在 `g.unload` 收。
8. **§5.3 S9（同时到达按批次号排队）**

   - **代码位置**：`f_engine.py` `simulate`；`tools/f_check.py` `services` 排序
   - **问题**：同时到达同一仓库时，`f_engine.py` 的事件堆 `(arr, p.bid)` 按**原始批次号** `p.bid` 决胜；而 `f_check.py` 读入重编号后的结果表，按 `(s["arrive"], s["_b"])` 排序，使用的是按 `(start_day, orig_batch)` 重排后的**新批次号** `new_id`（且 `arrive` 已四舍五入到分钟）。只要两个不同出发日的批次在同一（或舍入后同一）时刻到站，引擎与检查器的排队先后就会相反。
9. **§12 J1/J3 归一化与 P3/P4 同口径对比**

   - **代码位置**：`f_run_p4.py` `main`；`f_p4.py` `P4.score`；`f_run_extra.py` `r3_study`、`p4_batches`
   - **问题**：
     1. `f_run_p3.py` 生成问题 3 主结果时执行了 `improve` + 5 轮 `improve_pairs`（成对邻域），但 `f_run_p4.py` 重建对比行 `"问题3方案"` 时只执行了 `improve`、漏掉 `improve_pairs`，导致 `p4/summary.csv` 中的问题 3 对照指标可能与 `问题3_results.xlsx` 不一致。
     2. `f_p4.py` 的 `zE`、`zW` 缺少 J1 规定的 `u - l == 0` 时分母取 `1` 的保护；`f_run_extra.py` 的 `r3_study` 和 `p4_batches` 把 `ref_W` 的下界硬编码成 `42`，未按该场景真实求得的 `Wmin` 代入。

---

### 三、边界条件与内部逻辑缺陷

10. **§5.1 C2（$T_\beta - T_\beta^0 \le 3$）在整数规划容差下的边界风险**

    - **代码位置**：`f_p2.py` `solve`；`f_run_p2.py` `solve_checked`
    - **问题**：`f_p2.py` 用 `recv <= capT * y[b]` 约束 C2（Gurobi 默认容差 `1e-6`），而 `f_routes.py`、`f_check.py` 的 `ceil_` 使用 `math.ceil(x - 1e-9)`。若某批求和恰落入 `(capT + 1e-9, capT + 1e-6]`，Gurobi 会视为可行，而进位后会变成 `capT + 1` 违反 C2；且 `solve_checked` 只回查里程、未顺带复核 `T_β <= capT`。
11. **§2 A3（内部精确计算、输出舍入分钟）与检查器精度阈值冲突**

    - **代码位置**：`f_export.py` `_to_dt`；`tools/f_check.py` `hours`、`travel`
    - **问题**：`f_export.py` 按 spec A3 把 `arrive`/`depart` 四舍五入到分钟写入 Excel，而 `f_check.py` 读回这些已舍入时间后，在 `travel()` 中直接用 `1e-6` 小时（约 0.0036 秒）作为 `h > 1e-6` 与 `h + hrs <= 8 + 1e-6` 的分支阈值。虽因首站容差 `TOL = 61s`、后续站使用重算的 `end` 缓解了多数情况，但当首站 `arrive` 舍入或后续在边界 `0.5 分钟` 附近时，舍入时间与精确浮点仍存在错位风险。
12. **§5.3 S8（`load_anytime` 备选模式下的空转占名额 bug）**

    - **代码位置**：`f_engine.py` `Warehouse.serve`
    - **问题**：`us.add(unit)` 位于 `if room <= EPS:` 之前。当打开 `OPT["load_anytime"]=True`（一“天”扩展为 24 小时，但日限 20 台不变）且某天 `20` 台额度已用完但时间还没到次日 `8:00` 时，后到单位在该天做 `0` 台工作却仍把自身写入 `self.units[d]`，白白占用当日 3 支单位名额之一。
13. **§5.2 R2/R3/R4/R5/R7/R8 候选生成过度剪枝（偏严，非放松）**

    - **代码位置**：`f_p2.py` `options`（`if k.h in W: ... else:` 等处）
    - **问题**：`options` 基于转移前的初始目标集 `W = fb.targets(bt)` 判断 `k.h in W` 与否并作互斥分支。若接收批 `bt` 原先有去 `k.h` 的自有块，但在统筹中把该自有块转走了（最终 $h_k \notin W_\beta^{\text{own}}$），则 R2/R8 不可用而 R3/R4/R5/R7 原本可用，但 `options` 未生成这些候选，会漏掉合法合并。

---

### 四、独立检查器 `tools/f_check.py` 的漏检与自身漏洞

14. **§3.1 存放仓库备注解析与主流程不一致**

    - **代码位置**：`tools/f_check.py` `read_demand` vs `f_blocks.py` `_storage`
    - **问题**：`f_blocks._storage` 同时匹配 `(?:存放至|放置于)(W[A-Z])` 和 `从(W[A-Z])装载`，而 `f_check.py` 漏掉了 `从(W[A-Z])装载`；若需求表中有多仓库单位送交行采用该备注写法，检查器会得 `h = None` 并报出虚假的“守恒”违例。
15. **§5.1 C5、§5.2 R1–R8、§5.3 S15、§13 C6 在检查器中的漏检**

    - **代码位置**：`tools/f_check.py` `main`
    - **问题**：`f_check.py` 未完整核查：
      - 代领代交是否符合 R1–R8 之一（未核 $w_k \in W_\beta^{\text{own}}$、未核 R3/R4 的 $h_x$ 是否有自有卸货、未核 R4 的 $h_x \in W_{\beta'}^{\text{own}}$、未核 R5 同仓代交配对与顺序、未核内部互转反转前提）；
      - S15 中无作业途经站是否属于本批次合法节点集（任意无关仓库无动作过路不会被报出）；
      - C6 是否达到最大可转给 U6 块数；
      - 守恒核对对 R3 的豁免只验证两点均属 `TEAM` 且任一点距货主 $\le 150\text{ km}$，未核对落点确实是合规代领卸载仓。
16. **同键值匹配碰撞与统计误差（仅影响检查器自身）**

    - **代码位置**：`tools/f_check.py` `main`
    - **问题**：
      - `onboard.remove(hit)` 仅按 `(owner, item, qty)` 匹配首个元素，若同批次替同一货主在不同仓库装载了两批品名、数量相同的货，且先装的后卸，会扣错 `hit` 导致 `Lbar` 和 `is_send` 算错；
      - `stage_ld` / `stage_un` 以 `(owner, it, n, q)` 为键，若同一货主两笔同规格货物走同一仓库 R4 暂存，后者会覆盖前者；
      - `Vpairs` 用 `cands[:1]` 反查被代原批次，未匹配仓库 `w` 与方向 `dir` 且截断为 1 条，若同单位多批次有同规格货物会误算 `V`；
      - 同一站若既汇合又留置新货（`any(sg["follow"] == "否")`），`if n in left and not any(...)` 会跳过汇合弹出。
