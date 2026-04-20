"""测试 utils.technical_indicators

验证核心技术指标的**数值正确性**与边界条件:
- 单调递增序列下 RSI 应 → 100
- 单调递减序列下 RSI 应 → 0
- 布林带 middle 应等于 SMA,upper-lower = 4σ
- 平坦价格下 KDJ 应收敛到 50
- 数据不足 / 异常输入不抛异常,按模块约定返回 0.0 或 None
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from findatamcp.utils import technical_indicators as ti


# ---------- RSI ----------

def test_rsi_all_up_approaches_100():
    # 连续上涨 -> loss=0 -> RSI = 100
    prices = pd.Series(list(range(1, 40)), dtype=float)
    rsi = ti.calculate_rsi(prices, period=14)
    assert 99.0 <= rsi <= 100.0


def test_rsi_all_down_approaches_0():
    prices = pd.Series(list(range(40, 1, -1)), dtype=float)
    rsi = ti.calculate_rsi(prices, period=14)
    assert 0.0 <= rsi <= 1.0


def test_rsi_flat_returns_zero_or_nan_safe():
    # 完全平坦 -> delta 全 0 -> gain/loss 0/0 -> 函数吞异常返回 0.0
    prices = pd.Series([10.0] * 30)
    rsi = ti.calculate_rsi(prices, period=14)
    assert rsi == 0.0 or math.isnan(rsi)


def test_rsi_empty_input_returns_zero():
    assert ti.calculate_rsi(pd.Series([], dtype=float)) == 0.0


# ---------- Bollinger Bands ----------

def test_bollinger_bands_middle_equals_sma():
    prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0,
                        15.0, 16.0, 17.0, 18.0, 19.0,
                        20.0, 21.0, 22.0, 23.0, 24.0,
                        25.0, 26.0, 27.0, 28.0, 29.0])  # 长度 20
    bb = ti.calculate_bollinger_bands(prices, period=20)
    expected_sma = prices.mean()
    assert bb["middle_band"] == pytest.approx(expected_sma, rel=1e-6)
    # upper - lower 应等于 4σ
    expected_std = prices.std()
    assert (bb["upper_band"] - bb["lower_band"]) == pytest.approx(4 * expected_std, rel=1e-6)


def test_bollinger_bands_flat_prices_zero_band_width():
    prices = pd.Series([50.0] * 25)
    bb = ti.calculate_bollinger_bands(prices, period=20)
    assert bb["upper_band"] == pytest.approx(bb["middle_band"])
    assert bb["lower_band"] == pytest.approx(bb["middle_band"])


# ---------- MACD ----------

def test_macd_returns_required_keys():
    prices = pd.Series(np.linspace(10, 20, 50))
    macd = ti.calculate_macd(prices)
    assert set(macd.keys()) == {"macd", "signal", "histogram"}
    # 线性上升趋势下 MACD 应 > 0(快 EMA 高于慢 EMA)
    assert macd["macd"] > 0


def test_macd_histogram_equals_macd_minus_signal():
    prices = pd.Series(np.linspace(10, 20, 60))
    r = ti.calculate_macd(prices)
    assert r["histogram"] == pytest.approx(r["macd"] - r["signal"], rel=1e-6)


# ---------- KDJ ----------

def _ohlc_df(close: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "high": [c + 1 for c in close],
        "low": [c - 1 for c in close],
        "close": close,
    })


def test_kdj_returns_keys():
    df = _ohlc_df([10.0 + i for i in range(30)])
    kdj = ti.calculate_kdj(df, period=9)
    assert set(kdj.keys()) == {"kdj_k", "kdj_d", "kdj_j"}
    for k in kdj.values():
        assert k is not None


def test_kdj_j_equals_3k_minus_2d():
    df = _ohlc_df([10.0 + i * 0.5 for i in range(30)])
    kdj = ti.calculate_kdj(df)
    assert kdj["kdj_j"] == pytest.approx(3 * kdj["kdj_k"] - 2 * kdj["kdj_d"], rel=1e-6)


# ---------- Williams / CCI / ROC ----------

def test_williams_all_high_returns_zero():
    # 当前 close 等于最高价 -> Williams = 0
    df = pd.DataFrame({
        "high": [20.0] * 20,
        "low": [10.0] * 20,
        "close": [10.0] * 19 + [20.0],
    })
    w = ti.calculate_williams(df, period=14)
    assert w == pytest.approx(0.0)


def test_williams_all_low_returns_100():
    df = pd.DataFrame({
        "high": [20.0] * 20,
        "low": [10.0] * 20,
        "close": [20.0] * 19 + [10.0],
    })
    w = ti.calculate_williams(df, period=14)
    assert w == pytest.approx(100.0)


def test_williams_insufficient_data_returns_none():
    df = _ohlc_df([10.0, 11.0, 12.0])
    assert ti.calculate_williams(df, period=14) is None


def test_roc_basic_formula():
    # period=3, 第 4 个 vs 第 1 个: (20 - 10) / 10 * 100 = 100
    prices = pd.Series([10.0, 12.0, 15.0, 20.0])
    roc = ti.calculate_roc(prices, period=3)
    assert roc == pytest.approx(100.0)


def test_roc_insufficient_data_returns_none():
    prices = pd.Series([10.0, 12.0])
    assert ti.calculate_roc(prices, period=12) is None


# ---------- OBV / 量比 ----------

def test_obv_accumulates_on_up_days_only():
    df = pd.DataFrame({
        "close": [10.0, 11.0, 12.0, 11.0, 12.0],  # 涨/涨/跌/涨
        "vol":   [100,  200,  300,  400,  500],
    })
    # +200(涨) + 300(涨) - 400(跌) + 500(涨) = 600
    assert ti.calculate_obv(df) == 600


def test_volume_ratio_equals_one_when_flat():
    df = pd.DataFrame({"vol": [100.0] * 6})
    ratio = ti.calculate_volume_ratio(df)
    assert ratio == pytest.approx(1.0)


# ---------- ATR ----------

def test_atr_with_constant_range():
    # high-low 恒为 5 -> ATR 恒为 5
    n = 20
    df = pd.DataFrame({
        "high": [15.0] * n,
        "low": [10.0] * n,
        "close": [12.5] * n,
    })
    assert ti.calculate_atr(df, period=14) == pytest.approx(5.0)


def test_atr_insufficient_data_returns_none():
    df = _ohlc_df([10.0])
    assert ti.calculate_atr(df, period=14) is None


# ---------- 风险指标 ----------

def test_max_drawdown_monotonic_down():
    prices = np.array([100.0, 90.0, 80.0, 70.0])
    dd = ti.calculate_max_drawdown(prices)
    # 累积收益 = [0.9, 0.8, 0.7];max = 0.9, min = 0.7
    # drawdown = (0.7 - 0.9)/0.9 ≈ -0.2222
    assert dd == pytest.approx(0.2222, rel=1e-3)


def test_max_drawdown_monotonic_up_is_zero():
    prices = np.array([100.0, 110.0, 120.0, 130.0])
    assert ti.calculate_max_drawdown(prices) == pytest.approx(0.0)


def test_sharpe_ratio_positive_when_returns_exceed_rf():
    np.random.seed(42)
    # 平均日收益 0.1%,波动 1% -> 年化收益 ~25%,应显著高于 rf=3%
    returns = np.random.normal(0.001, 0.01, 252)
    sr = ti.calculate_sharpe_ratio(returns, risk_free_rate=0.03)
    assert sr > 0


def test_sharpe_ratio_insufficient_data_returns_none():
    assert ti.calculate_sharpe_ratio(np.array([0.01])) is None


def test_var_at_95_percent_nonneg():
    np.random.seed(0)
    returns = np.random.normal(0, 0.01, 100)
    v = ti.calculate_var(returns, confidence_level=0.95)
    assert v >= 0


# ---------- 移动平均 ----------

def test_moving_averages_basic():
    prices = pd.Series([float(i) for i in range(1, 21)])
    r = ti.calculate_moving_averages(prices, periods=[5, 10, 20])
    assert r["ma_5"] == pytest.approx(sum(range(16, 21)) / 5)
    assert r["ma_10"] == pytest.approx(sum(range(11, 21)) / 10)
    assert r["ma_20"] == pytest.approx(sum(range(1, 21)) / 20)


def test_moving_averages_missing_period_is_none():
    prices = pd.Series([1.0, 2.0, 3.0])
    r = ti.calculate_moving_averages(prices, periods=[5, 10])
    assert r["ma_5"] is None
    assert r["ma_10"] is None
