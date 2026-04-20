"""pytest 公共 fixtures

集中提供 Tushare API 的 mock 与常用假数据,让单元测试不依赖真网络/Token。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pandas as pd
import pytest

# 让 `import findatamcp` 能找到包根
sys.path.insert(0, str(Path(__file__).parent.parent))


# 需要真实 Tushare / 本地服务的集成脚本,默认不随单元测试运行。
# 可显式执行:`pytest tests/test_market_statistics.py` 等。
collect_ignore = [
    "test_market_statistics.py",   # 直连 Tushare Pro
    "test_tools.py",               # 需本地 MCP server (8006)
    "test_complete_workflow.py",   # 需本地 backend (8004)
    "test_sse_client.py",          # 需本地 SSE server
]


# ---------- 假数据 ----------

@pytest.fixture
def sample_daily_df() -> pd.DataFrame:
    """一段 5 日 A 股日线,用于行情类测试。"""
    return pd.DataFrame({
        "ts_code": ["600519.SH"] * 5,
        "trade_date": ["20240102", "20240103", "20240104", "20240105", "20240108"],
        "open":  [1700.0, 1710.0, 1705.0, 1720.0, 1715.0],
        "high":  [1720.0, 1730.0, 1725.0, 1740.0, 1735.0],
        "low":   [1695.0, 1700.0, 1695.0, 1710.0, 1705.0],
        "close": [1715.0, 1708.0, 1722.0, 1730.0, 1728.0],
        "pre_close": [1690.0, 1715.0, 1708.0, 1722.0, 1730.0],
        "change": [25.0, -7.0, 14.0, 8.0, -2.0],
        "pct_chg": [1.48, -0.41, 0.82, 0.46, -0.12],
        "vol": [30000.0, 32000.0, 28000.0, 35000.0, 31000.0],
        "amount": [5_000_000.0, 5_200_000.0, 4_800_000.0, 5_800_000.0, 5_300_000.0],
    })


@pytest.fixture
def sample_stock_basic_df() -> pd.DataFrame:
    """少量股票基础信息,用于 entity_store 等测试。"""
    return pd.DataFrame({
        "ts_code": ["600519.SH", "000001.SZ", "300750.SZ"],
        "symbol":  ["600519", "000001", "300750"],
        "name":    ["贵州茅台", "平安银行", "宁德时代"],
        "area":    ["贵州", "深圳", "福建"],
        "industry": ["白酒", "银行", "电池"],
        "market":  ["主板", "主板", "创业板"],
        "list_date": ["20010827", "19910403", "20180611"],
    })


@pytest.fixture
def sample_fund_basic_df() -> pd.DataFrame:
    """少量 ETF 基础信息。"""
    return pd.DataFrame({
        "ts_code": ["510300.SH", "159915.SZ"],
        "name": ["沪深300ETF", "易方达创业板ETF"],
        "management": ["华泰柏瑞", "易方达"],
        "type": ["股票型", "股票型"],
        "fund_type": ["ETF", "ETF"],
        "list_date": ["20120528", "20110901"],
        "status": ["L", "L"],
    })


@pytest.fixture
def sample_rows() -> List[Dict[str, Any]]:
    """通用 dict 行集合,用于 large_data_handler / data_file_store。"""
    return [
        {"trade_date": f"2024010{i+1}", "ts_code": "600519.SH", "close": 100.0 + i}
        for i in range(5)
    ]


# ---------- Tushare API mock ----------

@pytest.fixture
def mock_tushare_pro(sample_daily_df, sample_stock_basic_df, sample_fund_basic_df):
    """MagicMock 模拟的 `tushare.pro_api()` 对象,默认方法返回常用 DataFrame。

    测试中可按需 `mock_tushare_pro.daily.return_value = ...` 覆盖。
    """
    pro = MagicMock()
    pro.daily.return_value = sample_daily_df
    pro.stock_basic.return_value = sample_stock_basic_df
    pro.fund_basic.return_value = sample_fund_basic_df
    pro.hk_basic.return_value = pd.DataFrame()
    pro.us_basic.return_value = pd.DataFrame()
    pro.income.return_value = pd.DataFrame([{
        "ts_code": "600519.SH", "end_date": "20231231",
        "total_revenue": 1.5e11, "total_profit": 8e10, "n_income": 7e10,
    }])
    pro.balancesheet.return_value = pd.DataFrame([{
        "ts_code": "600519.SH", "end_date": "20231231",
        "total_assets": 2.5e11, "total_hldr_eqy_exc_min_int": 2e11,
    }])
    pro.moneyflow.return_value = pd.DataFrame({
        "ts_code": ["600519.SH"] * 3,
        "trade_date": ["20240102", "20240103", "20240104"],
        "net_mf_amount": [1_000_000.0, -500_000.0, 800_000.0],
    })
    return pro


@pytest.fixture
def mock_tushare_api(mock_tushare_pro):
    """构造一个已初始化的 `TushareAPI`,其 `pro` 指向 mock。

    避免在 __init__ 中触发真网络调用:直接 bypass 构造器的连通性检查。
    """
    from findatamcp.utils.tushare_api import TushareAPI

    api = TushareAPI.__new__(TushareAPI)
    api.token = "fake-token"
    api.pro = mock_tushare_pro
    api._is_pro = True
    return api
