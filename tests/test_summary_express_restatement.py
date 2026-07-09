"""get_financial_summary / get_stock_data 财务块 / get_express 的重报口径回归。

背景(2026-07-09):修完 get_income_statement 一族的重报 bug 后做同型扫描,
发现还有三处"让 Tushare 返回顺序决定选哪一行"的同族调用点:
- financial_data._financial_summary_impl: pro.income/balancesheet 用 limit=1
  把选行权整个交给服务端排序,且没钉 report_type(同一 end_date 混多口径);
- market_data.get_stock_data 财务块: 从上面逐字复制出来的同一段代码;
- performance_data.get_express: 业绩快报更正后同一 end_date 两条记录,iloc[0]
  看运气。

修法统一收口到 financial_data._latest_reported_row(单一实现,不再复制),
summary 类调用改为 report_type='1' + limit=8 + 本地按公告日取最新。
本文件用 000858.SZ 真实观测到的重报行形状钉死行为。
"""

from __future__ import annotations

import asyncio
import os

import pandas as pd
import pytest
from fastmcp import FastMCP

from findatamcp.tools.financial_data import register_financial_tools
from findatamcp.tools.performance_data import register_performance_tools
from findatamcp.utils.tushare_api import TushareAPI


def _build_api() -> TushareAPI:
    return TushareAPI(token=os.environ.get("TUSHARE_TOKEN"))


def _get_fn(mcp: FastMCP, name: str):
    tools = asyncio.run(mcp._list_tools())
    for t in tools:
        if t.name == name:
            return t.fn
    raise AssertionError(f"tool not found: {name}")


def _result_dict(res):
    return res if isinstance(res, dict) else getattr(res, "structured_content", {})


# ---------------------------------------------------------------------------
# get_financial_summary
# ---------------------------------------------------------------------------

_INCOME_COLS = ["ts_code", "end_date", "ann_date", "f_ann_date",
                "total_revenue", "total_profit", "n_income"]
_INCOME_ROWS = [
    # 首次披露(旧)排在前面 —— 直接取第一行就会吃到它
    ("000858.SZ", "20250630", "20250828", "20250828", 52770984383.52, 1.0e10, 8.0e9),
    ("000858.SZ", "20250630", "20250828", "20260430", 23509972048.65, 5.0e9, 4.0e9),
]

_BALANCE_COLS = ["ts_code", "end_date", "ann_date", "f_ann_date",
                 "total_assets", "total_hldr_eqy_exc_min_int"]
_BALANCE_ROWS = [
    ("000858.SZ", "20250630", "20250828", "20250828", 2.0e11, 1.5e11),
    ("000858.SZ", "20250630", "20250828", "20260430", 1.8e11, 1.4e11),
]


def test_financial_summary_pins_report_type_and_picks_restated_income(monkeypatch):
    income_calls: list[dict] = []

    def _fake_income(**kwargs):
        income_calls.append(kwargs)
        return pd.DataFrame(_INCOME_ROWS, columns=_INCOME_COLS)

    def _fake_balancesheet(**kwargs):
        return pd.DataFrame(_BALANCE_ROWS, columns=_BALANCE_COLS)

    api = _build_api()
    monkeypatch.setattr(api.pro, "income", _fake_income)
    monkeypatch.setattr(api.pro, "balancesheet", _fake_balancesheet)
    mcp = FastMCP("test-financial-summary")
    register_financial_tools(mcp, api)
    fn = _get_fn(mcp, "get_financial_summary")

    res = asyncio.run(fn(ts_code="000858.SZ"))
    data = _result_dict(res)["financial_data"]

    assert income_calls, "pro.income 没有被调用"
    assert income_calls[0].get("report_type") == "1", (
        f"必须钉死合并报表口径 report_type='1',实际调用参数: {income_calls[0]}"
    )
    assert data["income_core"]["total_revenue"] == pytest.approx(23509972048.65), (
        f"应该选中 f_ann_date=20260430 的重报版本,实际拿到: {data['income_core']}"
    )
    assert data["balance_core"]["total_assets"] == pytest.approx(1.8e11)


def test_financial_summary_single_row_unaffected(monkeypatch):
    # 注意: cache.cached_call 的缓存键含 ts_code+调用参数,和上一个用例
    # 撞键会直接命中缓存、绕过本用例的 fake——所以这里换一只股票。
    def _fake_income(**kwargs):
        return pd.DataFrame(
            [("600519.SH", "20251231", "20260430", "20260430", 4.05e10, 1.6e10, 1.2e10)],
            columns=_INCOME_COLS,
        )

    def _fake_balancesheet(**kwargs):
        return pd.DataFrame(
            [("600519.SH", "20251231", "20260430", "20260430", 2.1e11, 1.6e11)],
            columns=_BALANCE_COLS,
        )

    api = _build_api()
    monkeypatch.setattr(api.pro, "income", _fake_income)
    monkeypatch.setattr(api.pro, "balancesheet", _fake_balancesheet)
    mcp = FastMCP("test-financial-summary-single")
    register_financial_tools(mcp, api)
    fn = _get_fn(mcp, "get_financial_summary")

    res = asyncio.run(fn(ts_code="600519.SH"))
    data = _result_dict(res)["financial_data"]
    assert data["income_core"]["total_revenue"] == pytest.approx(4.05e10)


# ---------------------------------------------------------------------------
# get_express
# ---------------------------------------------------------------------------

_EXPRESS_COLS = ["ts_code", "end_date", "ann_date", "revenue", "n_income"]
_EXPRESS_ROWS = [
    # 快报更正: 原始快报排前,更正公告(ann_date 更晚)排后
    ("000858.SZ", "20251231", "20260128", 4.00e10, 1.50e10),
    ("000858.SZ", "20251231", "20260215", 4.05e10, 1.55e10),
]


def test_get_express_picks_latest_correction_not_first_row(monkeypatch):
    def _fake_express(**kwargs):
        return pd.DataFrame(_EXPRESS_ROWS, columns=_EXPRESS_COLS)

    api = _build_api()
    monkeypatch.setattr(api.pro, "express", _fake_express)
    mcp = FastMCP("test-express")
    register_performance_tools(mcp, api)
    fn = _get_fn(mcp, "get_express")

    res = asyncio.run(fn(ts_code="000858.SZ", period="20251231"))
    data = _result_dict(res)["data"]

    assert data["n_income"] == pytest.approx(1.55e10), (
        f"应该选中 ann_date=20260215 的更正版本,实际拿到: {data}"
    )
    assert data["ann_date"] == "20260215"


def test_get_express_multi_period_still_returns_latest_period(monkeypatch):
    """不传 period 时(多期混在一个 df 里),必须返回最新报告期的最新版本。"""
    rows = [
        ("000858.SZ", "20251231", "20260128", 4.00e10, 1.50e10),
        ("000858.SZ", "20250630", "20250715", 2.30e10, 0.90e10),
    ]

    def _fake_express(**kwargs):
        return pd.DataFrame(rows, columns=_EXPRESS_COLS)

    api = _build_api()
    monkeypatch.setattr(api.pro, "express", _fake_express)
    mcp = FastMCP("test-express-multi")
    register_performance_tools(mcp, api)
    fn = _get_fn(mcp, "get_express")

    res = asyncio.run(fn(ts_code="000858.SZ"))
    data = _result_dict(res)["data"]
    assert data["end_date"] == "20251231"
    assert data["n_income"] == pytest.approx(1.50e10)
