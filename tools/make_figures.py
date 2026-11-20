"""论文图表：全部从结果台账直接生成（只读 results/F/**），输出 paper/figs/*.png。

用法：python tools/make_figures.py
配色取 dataviz 参考调色板中已校验的取值：类别第 1 槽蓝、单色蓝阶（顺序）、蓝↔红两极（增减）。
打印用静态图，只做浅色模式；网格与坐标轴为实线细线；不在每个点上标数。
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results" / "F"
OUT = ROOT / "paper" / "figs"
OUT.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")

# ---- 调色板（参考实例，浅色模式）
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, RED, NEUTRAL = "#2a78d6", "#e34948", "#f0efec"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)

plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "SimHei", "sans-serif"], "axes.unicode_minus": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.spines.top": False, "axes.spines.right": False,
})
UNITS = [f"U{i}" for i in range(1, 13)]


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print("写出", (OUT / name).relative_to(ROOT))


def day_ticks(ax, lo=1, hi=91):
    ticks = [d for d in (1, 11, 21, 31, 41, 51, 61, 71, 81, 91) if lo <= d <= hi]
    lab = []
    for d in ticks:
        m, dd = (4, d) if d <= 30 else ((5, d - 30) if d <= 61 else (6, d - 61))
        lab.append(f"{m}/{dd}")
    ax.set_xticks(ticks, lab)


# ---------------------------------------------------------------- 图 2-1 技术路线
def fig_route():
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 48)
    ax.axis("off")

    def box(x, y, w, h, text, strong=False, fs=8):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                    fc=("#cde2fb" if strong else "#f0efec"), ec=(BLUE if strong else AXIS), lw=0.8))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=INK, linespacing=1.4)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=8, lw=0.8, color=MUTED,
                                     shrinkA=0, shrinkB=0))

    box(1, 18, 12, 12, "附件 1–5\n附表 1")
    box(17, 18, 14, 12, "解析与清洗\n需求块构造\n（Y2：90 块）")
    box(35, 6, 22, 36, "共用模块\n\n统一判定函数\n代领 5 种、代交 3 种\n目标仓库数、增车、里程\n\n时间引擎\n行驶、装卸、排队\n容量、等待、留置",
        strong=True, fs=7.6)
    arrow(13, 24, 17, 24)
    arrow(31, 24, 35, 24)
    probs = [("问题 1：追溯 + 按表回放", 40), ("问题 2：四级字典序整数规划", 30), ("问题 3：路线枚举 + 坐标下降", 18), ("问题 4：单块改派邻域搜索", 8)]
    for t, y in probs:
        box(60, y - 3.5, 28, 7, t, fs=7.6)
        arrow(57, y, 60, y)
        arrow(88, y, 91, 24)
    box(91, 14, 12.5, 20, "独立检查器\n不调用\n求解代码\n\n附件 6、7、8\n附表 2–4", strong=True, fs=7.6)
    save(fig, "图2-1_技术路线.png")


# ---------------------------------------------------------------- 流量热图
def flow_matrix(path):
    f = pd.read_csv(path)
    M = pd.DataFrame(0.0, index=UNITS, columns=UNITS)
    for r in f.itertuples():
        M.at[r.executor, r.owner] += r.s
    return M


def draw_heat(ax, M, vmax, title):
    data = M.values.copy()
    masked = np.ma.masked_where(data <= 1e-9, data)
    ax.set_facecolor(SURFACE)
    im = ax.imshow(masked, cmap=SEQ, vmin=0, vmax=vmax, aspect="equal")
    ax.set_xticks(range(12), UNITS, rotation=0, fontsize=7)
    ax.set_yticks(range(12), UNITS, fontsize=7)
    ax.set_xlabel("货主（被代办的单位）")
    ax.set_ylabel("执行方（代办的单位）")
    ax.set_title(title, loc="left")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks(np.arange(-0.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 12, 1), minor=True)
    ax.grid(which="minor", color=GRID, linewidth=0.6)
    ax.tick_params(which="minor", length=0)
    for i in range(12):
        for j in range(12):
            v = data[i, j]
            if v > 1e-9:
                ax.text(j, i, f"{v:.1f}" if v >= 0.95 else f"{v:.2f}", ha="center", va="center", fontsize=5.8,
                        color=("#ffffff" if v > 0.55 * vmax else INK))
    return im


def fig_flow_y1():
    M = flow_matrix(R / "p1/flow_after.csv")
    fig, ax = plt.subplots(figsize=(4.4, 4.0))
    im = draw_heat(ax, M, M.values.max(), "Y1（附件 3）单位间代领代交量")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("等效车数（按执行方车型）", color=INK2)
    cb.outline.set_visible(False)
    save(fig, "图6-1_Y1流量.png")


def fig_flow_p34():
    M3, M4 = flow_matrix(R / "p2/flow_main.csv"), flow_matrix(R / "p4/flow_main.csv")
    vmax = max(M3.values.max(), M4.values.max())
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.9), constrained_layout=True)
    draw_heat(axs[0], M3, vmax, f"问题 3（代领代交 {M3.values.sum():.2f} 等效车）")
    im = draw_heat(axs[1], M4, vmax, f"问题 4（代领代交 {M4.values.sum():.2f} 等效车）")
    axs[1].set_ylabel("")
    cb = fig.colorbar(im, ax=axs, fraction=0.025, pad=0.02)
    cb.set_label("等效车数（按执行方车型）", color=INK2)
    cb.outline.set_visible(False)
    save(fig, "图9-1_问题3与问题4流量.png")


# ---------------------------------------------------------------- 图 7-1 折衷曲线
def fig_curve():
    s = pd.read_csv(R / "p2/summary.csv")
    c = s[s.variant.str.startswith("curve_B")].copy()
    c["nb"] = c.variant.str.replace("curve_B", "").astype(int)
    c = c[c.nb == c.B].sort_values("B")
    fig, ax = plt.subplots(figsize=(5.6, 3.0))
    ax.grid(axis="y")
    ax.plot(c.B, c.A, color=BLUE, lw=2, zorder=3)
    ax.scatter(c.B, c.A, s=26, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=4)
    for b in (32, 33, 34, int(c.B.max())):
        r = c[c.B == b].iloc[0]
        ax.annotate(f"{b} 批：{r.A:.2f}", (r.B, r.A), xytext=(6, 4), textcoords="offset points", fontsize=7.5, color=INK2)
    ax.set_xlabel("保留批次数")
    ax.set_ylabel("代领代交量最小值（等效车）")
    ax.set_title("问题 2：批次数与代领代交量的折衷", loc="left")
    ax.set_xticks(range(int(c.B.min()), int(c.B.max()) + 1))
    ax.set_ylim(0, c.A.max() * 1.15)
    save(fig, "图7-1_折衷曲线.png")


# ---------------------------------------------------------------- 图 8-1 甘特图
def fig_gantt():
    b = pd.read_csv(R / "p3/batches_main.csv")
    mp = pd.read_csv(R / "p3/batch_id_map.csv").set_index("orig_batch").new_batch
    b["new"] = b.batch.map(mp)
    b = b.sort_values("new")
    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    ax.grid(axis="x")
    for i, r in enumerate(b.itertuples()):
        y = len(b) - 1 - i
        lo = max(1, r.a - 6)
        ax.barh(y, r.e - lo + 1, left=lo - 0.5, height=0.72, color=NEUTRAL, edgecolor="none", zorder=1)
        ax.barh(y, r.end - r.start + 1, left=r.start - 0.5, height=0.42, color=BLUE, edgecolor="none", zorder=2)
        ax.plot([r.a - 0.5, r.a - 0.5], [y - 0.36, y + 0.36], color=INK2, lw=0.9, zorder=3)
        if r.start != r.a:
            ax.annotate(f"{'提前' if r.start < r.a else '推迟'} {abs(r.start - r.a)} 天", (r.end + 0.5, y), xytext=(4, 0),
                        textcoords="offset points", va="center", fontsize=7, color=INK2)
    ax.set_yticks(range(len(b)), [f"{int(r.new)}（{r.unit}）" for r in b.itertuples()][::-1], fontsize=6.5)
    last = int(max(b.e.max(), b.end.max())) + 6
    day_ticks(ax, 1, last)
    ax.set_xlim(0, last)
    ax.set_xlabel("日期")
    ax.set_title("问题 3：各批次实施时段（蓝）与允许出发区间（灰），竖线为提报开始日", loc="left")
    save(fig, "图8-1_问题3甘特图.png")


# ---------------------------------------------------------------- 图 8-2 仓库日负荷
def fig_whload():
    w = pd.read_csv(R / "p3/wh_load_main.csv")
    top = w.groupby("wh").veh.sum().sort_values(ascending=False).index[:2].tolist()
    last = int(w[w.wh.isin(top)].day.max()) + 4
    fig, axs = plt.subplots(len(top), 1, figsize=(7.0, 4.2), sharex=True, constrained_layout=True)
    for ax, wh in zip(axs, top):
        d = w[w.wh == wh]
        ax.grid(axis="y")
        ax.bar(d.day, d.veh, width=0.8, color=BLUE, edgecolor="none", zorder=2)
        ax.axhline(20, color=INK2, lw=0.9, zorder=3)
        ax.text(last, 20, "日容量 20 台次", va="bottom", ha="right", fontsize=7, color=INK2)
        ax.set_ylim(0, 23)
        ax.set_ylabel("作业台次")
        ax.set_title(f"{wh}：{len(d)} 个作业日，满额 {int((d.veh >= 20 - 1e-6).sum())} 天", loc="left")
    day_ticks(axs[-1], 1, last)
    axs[-1].set_xlim(0, last)
    axs[-1].set_xlabel("日期")
    save(fig, "图8-2_仓库日负荷.png")


# ---------------------------------------------------------------- 图 10-1 龙卷风图
def fig_tornado():
    rl = pd.read_csv(R / "extra/p3_rules.csv").set_index("读法")
    sn = pd.read_csv(R / "extra/sens.csv").set_index("方案")
    base = rl.loc["spec 默认"]
    items = [("长段可随时出发", rl.loc["split_long（G6 备选）"]), ("任何路段可途中过夜", rl.loc["split_legs（D11 的 b）"]),
             ("装卸不限时段", rl.loc["load_anytime"]), ("装卸不取整", sn.loc["G7 装卸不取整"]),
             ("长段随时出发 + 装卸不限时段", rl.loc["split_long+load_anytime"]), ("途中过夜 + 装卸不限时段", rl.loc["split_legs+load_anytime"]),
             ("里程上限 2200 km", sn.loc["G2 里程上限 2200 km"]), ("里程上限 2500 km", sn.loc["G2 里程上限 2500 km"]),
             ("留置不受等待限制", sn.loc["G14 留置不受等待限制"])]
    rows = [(n, float(r["执行总时间"]) - base["执行总时间"], float(r["载货总行驶距离"]) - base["载货总行驶距离"]) for n, r in items]
    rows.sort(key=lambda x: abs(x[1]))
    names = [r[0] for r in rows]
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.4), sharey=True, constrained_layout=True)
    for ax, k, lab, fmt in ((axs[0], 1, "执行总时间变化（天）", "{:+.0f}"), (axs[1], 2, "载货距离变化（km）", "{:+.1f}")):
        vals = [r[k] for r in rows]
        ax.grid(axis="x")
        ax.barh(range(len(rows)), vals, height=0.55, color=[BLUE if v < 0 else RED for v in vals], edgecolor="none", zorder=2)
        ax.axvline(0, color=AXIS, lw=0.9, zorder=3)
        for i, v in enumerate(vals):
            ax.text(v + (0.4 if k == 1 else 3) * (1 if v >= 0 else -1), i, fmt.format(v) if abs(v) > 1e-9 else "0",
                    va="center", ha=("left" if v >= 0 else "right"), fontsize=7, color=INK2)
        ax.set_xlabel(lab)
        lim = max(abs(min(vals)), abs(max(vals))) * 1.35 + (1 if k == 1 else 10)
        ax.set_xlim(-lim, lim)
    axs[0].set_yticks(range(len(rows)), names)
    axs[0].set_title(f"问题 3 对规则读法的灵敏度（主结果 {int(base['执行总时间'])} 天 / {base['载货总行驶距离']:.1f} km）", loc="left")
    save(fig, "图10-1_灵敏度.png")


if __name__ == "__main__":
    fig_route()
    fig_flow_y1()
    fig_curve()
    fig_gantt()
    fig_whload()
    fig_flow_p34()
    fig_tornado()
