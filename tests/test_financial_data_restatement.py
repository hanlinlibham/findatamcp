"""get_income_statement/get_balance_sheet/get_cashflow_statement/get_financial_ratios
在同一 (end_date, report_type) 有重报/更正记录时,必须取最新公告日的版本。

背景(2026-07-09):修 get_financial_metrics 的 report_type 缺失 bug 时,用
get_income_statement(period=20250630, report_type=1) 核对五粮液(000858.SZ)
数据当"标准答案",结果发现这个"标准答案"本身也不准——它和刚修好的
get_financial_metrics 对不上。查 Tushare 原始返回坐实:同一个
(end_date=20250630, report_type=1) 底下有两条记录,f_ann_date 更早的一条
(52770984383.52,首次披露)排在前面,f_ann_date 更晚的一条(23509972048.65,
和 FY2025 年报同天发布的重报版本)排在后面。四个函数全部无脑 df.iloc[0],
吃到了过期的首次披露版本。

本测试用真实观测到的行形状(见 tools/financial_data.py 里 _latest_reported_row
的 docstring)钉死:必须选中 f_ann_date 更晚的那一条。
"""

from __future__ import annotations

import asyncio
import os

import pandas as pd
import pytest
from fastmcp import FastMCP

from findatamcp.tools.financial_data import register_financial_tools
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


# 000858.SZ 20250630 report_type=1 真实观测到的两条冲突记录。
_RESTATED_ROWS = [
    # end_date,    report_type, ann_date,   f_ann_date, update_flag, total_revenue
    ("20250630", "1", "20250828", "20250828", "0", 52770984383.52),  # 首次披露(旧)
    ("20250630", "1", "20250828", "20260430", "1", 23509972048.65),  # 重报(新,应选这条)
]


def _fake_income(**kwargs):
    df = pd.DataFrame(
        _RESTATED_ROWS,
        columns=["end_date", "report_type", "ann_date", "f_ann_date", "update_flag", "total_revenue"],
    )
    if kwargs.get("report_type") is not None:
        df = df[df["report_type"] == kwargs["report_type"]]
    return df.reset_index(drop=True)


def test_get_income_statement_picks_latest_announcement_not_first_row(monkeypatch):
    api = _build_api()
    monkeypatch.setattr(api.pro, "income", _fake_income)
    mcp = FastMCP("test-financial-data")
    register_financial_tools(mcp, api)
    fn = _get_fn(mcp, "get_income_statement")

    res = asyncio.run(fn(ts_code="000858.SZ", period="20250630", report_type="1"))
    data = _result_dict(res)["data"]

    assert data["total_revenue"] == pytest.approx(23509972048.65), (
        f"应该选中 f_ann_date=20260430 的重报版本,而不是 df 里排第一的旧披露,实际拿到: {data}"
    )
    assert data["f_ann_date"] == "20260430"


def test_single_row_period_is_unaffected(monkeypatch):
    """常态(只有一条记录)下,新逻辑必须和原来的 .iloc[0] 行为完全一致。"""
    def _fake_single_row(**kwargs):
        df = pd.DataFrame(
            [("20251231", "1", "20260430", "20260430", "1", 40528509770.23)],
            columns=["end_date", "report_type", "ann_date", "f_ann_date", "update_flag", "total_revenue"],
        )
        return df.reset_index(drop=True)

    api = _build_api()
    monkeypatch.setattr(api.pro, "income", _fake_single_row)
    mcp = FastMCP("test-financial-data")
    register_financial_tools(mcp, api)
    fn = _get_fn(mcp, "get_income_statement")

    res = asyncio.run(fn(ts_code="000858.SZ", period="20251231", report_type="1"))
    data = _result_dict(res)["data"]
    assert data["total_revenue"] == pytest.approx(40528509770.23)
