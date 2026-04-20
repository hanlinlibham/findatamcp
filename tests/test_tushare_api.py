"""测试 utils.tushare_api

重点:纯静态规则(代码标准化、市场判断、指数/基金识别)。
涉及网络/token 的 API 调用逻辑由 fetch_daily_data 的 mock 路径覆盖。
"""

from __future__ import annotations

import pandas as pd
import pytest

from findatamcp.utils.tushare_api import TushareAPI, fetch_daily_data


@pytest.fixture
def api():
    """无 token 的 api 实例(纯规则方法不需要网络)。"""
    return TushareAPI.__new__(TushareAPI)


# ---------- normalize_stock_code ----------

@pytest.mark.parametrize("raw,expected", [
    ("600519", "600519.SH"),           # 上交所主板
    ("000001", "000001.SZ"),           # 深证
    ("300750", "300750.SZ"),           # 创业板
    ("832000", "832000.BJ"),           # 北交所 8 开头
    ("430010", "430010.BJ"),           # 北交所 4 开头
    ("600519.SH", "600519.SH"),        # 已带后缀
    ("00700.HK", "00700.HK"),          # 港股
    ("00700.hk", "00700.HK"),          # 港股大小写
    ("AAPL", "AAPL"),                  # 美股
    ("aapl", "AAPL"),                  # 美股大小写
])
def test_normalize_stock_code(api, raw, expected):
    assert api.normalize_stock_code(raw) == expected


# ---------- get_market ----------

@pytest.mark.parametrize("code,market", [
    ("600519.SH", "A"),
    ("000001.SZ", "A"),
    ("399001.SZ", "A"),
    ("00700.HK", "HK"),
    ("AAPL", "US"),
    ("MSFT", "US"),
])
def test_get_market(api, code, market):
    assert api.get_market(code) == market


# ---------- is_index_code ----------

@pytest.mark.parametrize("code,is_index", [
    ("000001.SH", True),    # 上证指数
    ("399001.SZ", True),    # 深证成指
    ("399006.SZ", True),    # 创业板指
    ("801010.SI", True),    # 申万
    ("CI005001.CI", True),  # 中信
    ("999999.SH", True),    # 9xxxxx.SH
    ("600519.SH", False),   # 个股
    ("000001.SZ", False),   # 平安银行(深圳是 000001,不是指数)
    ("300750.SZ", False),   # 创业板个股
])
def test_is_index_code(api, code, is_index):
    assert api.is_index_code(code) is is_index


# ---------- is_fund_code ----------

@pytest.mark.parametrize("code,is_fund", [
    ("510300.SH", True),    # 沪市 ETF
    ("159915.SZ", True),    # 深市 ETF
    ("110011.OF", True),    # 场外基金
    ("600519.SH", False),
    ("000001.SZ", False),
])
def test_is_fund_code(api, code, is_fund):
    assert api.is_fund_code(code) is is_fund


# ---------- fetch_daily_data 路由 ----------

class _StubCache:
    """把 cached_call 变成直接调用,便于断言路由。"""

    def __init__(self):
        self.calls = []

    async def cached_call(self, func, cache_type="daily", **kwargs):
        self.calls.append((func, kwargs))
        return func(**kwargs)


@pytest.mark.asyncio
async def test_fetch_daily_routes_a_stock(mock_tushare_api, sample_daily_df):
    cache = _StubCache()
    df = await fetch_daily_data(cache, mock_tushare_api, "600519.SH")
    assert df is sample_daily_df
    mock_tushare_api.pro.daily.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_daily_routes_hk(mock_tushare_api):
    hk_df = pd.DataFrame({"ts_code": ["00700.HK"], "close": [300.0]})
    mock_tushare_api.pro.hk_daily = lambda **kw: hk_df
    cache = _StubCache()

    df = await fetch_daily_data(cache, mock_tushare_api, "00700.HK")
    assert df is hk_df


@pytest.mark.asyncio
async def test_fetch_daily_routes_us_and_renames(mock_tushare_api):
    us_df = pd.DataFrame({
        "ts_code": ["AAPL"], "close": [200.0], "pct_change": [1.23]
    })
    mock_tushare_api.pro.us_daily = lambda **kw: us_df.copy()
    cache = _StubCache()

    df = await fetch_daily_data(cache, mock_tushare_api, "AAPL")
    assert "pct_chg" in df.columns
    assert "pct_change" not in df.columns
    assert "pre_close" in df.columns
    assert "change" in df.columns


@pytest.mark.asyncio
async def test_fetch_daily_routes_fund(mock_tushare_api):
    fd = pd.DataFrame({"ts_code": ["510300.SH"], "close": [4.0]})
    mock_tushare_api.pro.fund_daily = lambda **kw: fd
    cache = _StubCache()

    df = await fetch_daily_data(cache, mock_tushare_api, "510300.SH")
    assert df is fd


@pytest.mark.asyncio
async def test_fetch_daily_routes_index(mock_tushare_api):
    idx = pd.DataFrame({"ts_code": ["000001.SH"], "close": [3500.0]})
    mock_tushare_api.pro.index_daily = lambda **kw: idx
    cache = _StubCache()

    df = await fetch_daily_data(cache, mock_tushare_api, "000001.SH")
    assert df is idx


# ---------- get_api_type / is_available ----------

def test_is_available_reflects_pro_flag():
    api = TushareAPI.__new__(TushareAPI)
    api.pro = None
    api._is_pro = False
    assert api.is_available() is False

    api.pro = object()
    api._is_pro = True
    assert api.is_available() is True
