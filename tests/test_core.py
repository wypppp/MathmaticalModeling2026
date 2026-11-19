"""第一批单元测试：回测器、检查器、数据对齐（evidence P1–P3、P10）。运行：python -m pytest tests -q"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import checker, data, sim  # noqa: E402


def _run(b, L, G, S0, u):
    led = sim.execute_day(b, L, G, S0, lambda t, S, bt, Lt, Gt: u[t])
    price = np.ones(len(b))
    errs = checker.check_ledger(led.b, led.L, led.G, led.c, led.d, led.e, led.w, led.S, price, led.cost(price))
    return led, errs


def test_hand_case_shortage_and_surplus():
    # 时段 0：缺口 100，放电 50 → 紧急 50；时段 1：富余 200 → 自动充电 200；时段 2：放电请求但有富余 → 改为充电
    b = np.array([0.0, 300.0, 100.0]); L = np.array([100.0, 100.0, 50.0]); G = np.zeros(3)
    led, errs = _run(b, L, G, 6000.0, [50.0, 0.0, 30.0])
    assert errs == []
    assert np.isclose(led.e[0], 50) and np.isclose(led.d[0], 50)
    assert np.isclose(led.c[1], 200) and led.w[1] == 0
    assert np.isclose(led.c[2], 50) and led.d[2] == 0
    assert np.isclose(led.S[3], 6000 - 50 / 0.9 + 0.9 * 250)


def test_power_and_soc_limits():
    # 接近下限时放电受 SOC 限制；功率不超过 833.33
    b = np.zeros(2); L = np.array([2000.0, 2000.0]); G = np.zeros(2)
    led, errs = _run(b, L, G, 1300.0, [2000.0, 2000.0])
    assert errs == []
    assert np.isclose(led.d[0], 90.0) and np.isclose(led.S[1], 1200.0)
    assert np.isclose(led.e[0], 1910.0) and led.d[1] == 0


def test_surplus_when_full():
    b = np.array([1000.0]); L = np.array([100.0]); G = np.zeros(1)
    led, errs = _run(b, L, G, 10800.0, [0.0])
    assert errs == [] and np.isclose(led.w[0], 900.0) and led.c[0] == 0


def test_checker_catches_errors():
    b = np.array([100.0]); L = np.array([100.0]); G = np.zeros(1)
    errs = checker.check_ledger(b, L, G, [10.0], [10.0], [0.0], [0.0], [6000.0, 6000.0 + 9 - 10 / 0.9], [1.0], 100.0)
    assert any("同时充放" in x for x in errs)
    errs = checker.check_ledger(b, L, G, [0.0], [0.0], [0.0], [0.0], [6000.0, 6000.0], [1.0], 99.0)
    assert any("P4" in x for x in errs)


def test_data_alignment():
    p, L1, G1 = data.load_a1()
    assert len(p) == 144 and np.isclose(p.max() / p.min(), 3.7576, atol=1e-3)
    dates, L, G = data.load_a2()
    assert dates[0].isoformat() == "2025-01-01" and L.shape == (365, 144)
    assert data.slot_label(0) == "0:00-0:10" and data.slot_label(60) == "10:00-10:10" and data.slot_label(143) == "23:50-24:00"
    fc = data.load_a3()
    import datetime as dt
    assert fc[(dt.date(2025, 1, 1), 6)].shape == (24,)
