"""Run from a checkout containing openpyxl; pass the baseline checkout as argv[1]."""
import csv
import math

from replay import RESULTS, audit, save


def rows(path):
    with (RESULTS / path).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def equal(actual, published):
    assert math.isclose(float(actual), float(published), rel_tol=0, abs_tol=1e-8), (actual, published)


def normalized(value, low, high):
    return (float(value) - low) / ((high - low) or 1)


def run():
    reference, = rows("p3/ref.csv")
    ties = rows("p3/ties.csv")
    axes = ("tau", "L", "delta")
    limits = {}
    for key in axes:
        low, high = (float(reference[p + key]) for p in ("l_", "u_"))
        equal(low, min(float(row["lb_" + key]) for row in ties) if key != "delta" else 0)
        equal(high, max(float(row["base_" + key]) for row in ties))
        limits[key] = low, high

    scores = []
    for row in ties:
        parts = [normalized(row[k], *limits[k]) for k in axes]
        score = sum(parts)
        equal(score, row["score"])
        scores.append((int(row["tie"]), *parts, score, int(row["V"]), float(row["D"])))
    assert sorted(r[0] for r in scores) == [0, 1, 2]
    winner = min(scores, key=lambda r: r[4:])[0]
    assert [int(r["tie"]) for r in ties if r["chosen"] == "True"] == [winner] == [2]
    save("tie_scores.csv", "指派,z_tau,z_L,z_delta,J1,V,D", scores)

    metrics = [audit(n) for n in (3, 4)]
    columns = ("人员调动执行总时间", "载货车辆总行驶距离", "开始偏离")
    selected, = [r for r in ties if int(r["tie"]) == winner]
    for column, key in zip((*columns, "V", "调运总里程"), (*axes, "V", "D")):
        equal(metrics[0][column], selected[key])

    published = rows("p4/summary.csv")
    assert published[0]["方案"] == "问题3方案" and published[1]["方案"].startswith("问题4方案")
    all_scores = []
    for i, row in enumerate(published):
        data = metrics[i] if i < 2 else row
        if i < 2:
            for key, value in data.items():
                equal(value, row[key])
        parts = [normalized(data[c], *limits[k]) for c, k in zip(columns, axes)]
        parts += [normalized(data["失衡度"], 0, float(metrics[0]["失衡度"])),
                  normalized(data["批次仓库对"], 42, metrics[0]["批次仓库对"])]
        equal(sum(parts), row["合成分"])
        all_scores.append((row["方案"], *parts, sum(parts), row["合成分"]))
    save("comparison_scores.csv", "方案,z_tau,z_L,z_delta,z_E,z_W,五项和,公布值", all_scores)
    save("workbook_metrics.csv", "指标,问题3,问题4,问题4减问题3",
         [(k, float(v), float(metrics[1][k]), float(metrics[1][k] - v)) for k, v in metrics[0].items()])
    print(scores, all_scores[:2])


if __name__ == "__main__":
    run()
