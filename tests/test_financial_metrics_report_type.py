"""get_financial_metrics 的 revenue/profit 序列必须只取合并报表(report_type=1)口径。

背景(2026-07-09):ablework 生产上一次白酒行业研究任务里,主脑把五粮液(000858.SZ)
"2025全年营收306亿/26Q1营收同比-56.6%"写进了交付物。实测这两个数字既不是幻觉也不是
计算错误——它们是 get_financial_metrics 真实返回的值,但源头脏了:tools/analysis.py
调 Tushare 原生 income 接口时没传 report_type,该接口不传这个参数会把同一个 end_date
的"合并报表/单季合并/调整合并"等多条口径混在一起返回。_calculate_metric_stats 的
yoy/cagr/ttm 全是纯位置窗口运算(iloc[i-4] 等),对这种混入的重复行没有任何防御,
一旦出现就会把不同口径的两行相减,产出离谱同比(实测复现出过 -73.6% 这种值)。

get_income_statement(同文件旁边的姊妹工具)一直是准的,因为它显式传了
report_type=report_type(默认 "1")。本测试钉死 get_financial_metrics 也必须
这样做,并且对残留的更正重报(update_flag)重复行做兜底去重。
"""

from __future__ import annotations

import asyncio
import os

import pandas as pd
import pytest
from fastmcp import FastMCP

from findatamcp.tools.analysis import register_analysis_tools
from findatamcp.utils.tushare_api import TushareAPI


def _build_api() -> TushareAPI:
    """TushareAPI() 不读环境变量——server.py 显式传 config.TUSHARE_TOKEN,
    这里镜像同样的构造方式,否则 api.pro 恒为 None,monkeypatch 无从下手。"""
    return TushareAPI(token=os.environ.get("TUSHARE_TOKEN"))


def _get_fn(mcp: FastMCP, name: str):
    tools = asyncio.run(mcp._list_tools())
    for t in tools:
        if t.name == name:
            return t.fn
    raise AssertionError(f"tool not found: {name}")


def _result_dict(res):
    return res if isinstance(res, dict) else getattr(res, "structured_content", {})


# 真实观测到的 000858.SZ 数据形状(2026-07-08 抓取):不传 report_type 时,
# Tushare income 接口对 20250630/20250930 各多返回一条"单季合并"(report_type=2)行,
# 数值远小于对应的"合并报表"(report_type=1)累计值。
_RAW_INCOME_ROWS = [
    ("20250331", "1", "20250426", 36940356116.35),
    ("20250630", "1", "20250825", 52770984383.52),   # 合并报表(半年累计) — 干净值
    ("20250630", "2", "20250825", 15830628267.17),    # 单季合并(Q2单季) — 不该混进 raw/yoy 序列
    ("20250930", "1", "20251028", 60945321083.57),   # 合并报表(前三季累计) — 干净值
    ("20250930", "2", "20251028", 8174336699.63),     # 单季合并(Q3单季) — 不该混进 raw/yoy 序列
    ("20251231", "1", "20260430", 89175178322.70),
    ("20260331", "1", "20260430", 22838024164.27),
]


def _fake_income(**kwargs):
    df = pd.DataFrame(_RAW_INCOME_ROWS, columns=["end_date", "report_type", "f_ann_date", "total_revenue"])
    report_type = kwargs.get("report_type")
    if report_type is not None:
        df = df[df["report_type"] == report_type]
    return df.reset_index(drop=True)


@pytest.fixture
def api_with_fake_income(monkeypatch):
    api = _build_api()
    calls = []

    def recording_income(**kwargs):
        calls.append(kwargs)
        return _fake_income(**kwargs)

    monkeypatch.setattr(api.pro, "income", recording_income)
    return api, calls


def test_income_call_requests_consolidated_report_type(api_with_fake_income):
    """report_type='1' 必须显式传给 Tushare,不能让它默认混入其它口径。"""
    api, calls = api_with_fake_income
    mcp = FastMCP("test-analysis")
    register_analysis_tools(mcp, api)
    fn = _get_fn(mcp, "get_financial_metrics")

    asyncio.run(fn(ts_code="000858.SZ", metrics=["revenue"], period="2y", calc_type="raw"))

    assert calls, "income 端点应该被调用过"
    assert calls[0].get("report_type") == "1", (
        f"必须显式请求合并报表口径,实际调用参数: {calls[0]}"
    )


def test_revenue_raw_series_excludes_mismatched_report_type_rows(api_with_fake_income):
    """raw 序列不应包含单季合并那两条 —— 每个 end_date 只保留一条干净值。"""
    api, _ = api_with_fake_income
    mcp = FastMCP("test-analysis")
    register_analysis_tools(mcp, api)
    fn = _get_fn(mcp, "get_financial_metrics")

    res = asyncio.run(fn(ts_code="000858.SZ", metrics=["revenue"], period="2y", calc_type="raw"))
    revenue = _result_dict(res)["metrics"]["revenue"]

    assert len(revenue["values"]) == 5, (
        f"5 个 end_date 应各只剩一条合并报表值,实际拿到 {len(revenue['values'])} 条: {revenue['values']}"
    )
    for contaminated in (15830628267.17, 8174336699.63):
        assert contaminated not in revenue["values"], (
            f"单季合并口径的 {contaminated} 不应混入合并报表序列"
        )
    # end_date 不应有重复
    assert len(revenue["source_dates"]) == len(set(revenue["source_dates"]))


def test_revenue_yoy_matches_clean_same_period_comparison(api_with_fake_income):
    """yoy 是纯位置窗口运算(iloc[i-4]),序列不干净就会把不同口径的行相减出离谱同比。
    修复后应该等价于真实"26Q1 vs 25Q1"营收同比(约 -38.18%),不是之前生产复现出的
    -56.6% / -73.6% 这类跟真实数据对不上的数字。
    """
    api, _ = api_with_fake_income
    mcp = FastMCP("test-analysis")
    register_analysis_tools(mcp, api)
    fn = _get_fn(mcp, "get_financial_metrics")

    res = asyncio.run(fn(ts_code="000858.SZ", metrics=["revenue"], period="2y", calc_type="yoy"))
    revenue = _result_dict(res)["metrics"]["revenue"]

    expected = (22838024164.27 - 36940356116.35) / 36940356116.35 * 100
    assert revenue["yoy_growth_rates"] == pytest.approx([expected], rel=1e-6), (
        f"expected clean 26Q1-vs-25Q1 yoy ≈{expected:.2f}%, got {revenue['yoy_growth_rates']}"
    )


# ---- fina_indicator 同款去重兜底(更正重报 update_flag 场景) ----

_RAW_FINA_ROWS = [
    ("20250930", "20251028", 22.15),
    ("20251231", "20260430", 6.50),
    ("20260331", "20260430", 6.50),
    ("20260331", "20260501", 6.50),  # 更正重报,同一 end_date 多一条(数值恰好相同也要去重)
]


def _fake_fina_indicator(**kwargs):
    df = pd.DataFrame(_RAW_FINA_ROWS, columns=["end_date", "ann_date", "roe"])
    return df.reset_index(drop=True)


def test_fina_indicator_dedupes_restated_rows(monkeypatch):
    api = _build_api()
    monkeypatch.setattr(api.pro, "fina_indicator", _fake_fina_indicator)
    mcp = FastMCP("test-analysis")
    register_analysis_tools(mcp, api)
    fn = _get_fn(mcp, "get_financial_metrics")

    res = asyncio.run(fn(ts_code="000858.SZ", metrics=["roe"], period="2y", calc_type="raw"))
    roe = _result_dict(res)["metrics"]["roe"]

    assert len(roe["values"]) == 3, (
        f"20260331 的更正重报行应被去重,只留最新公告日一条,实际: {roe}"
    )
    assert len(roe["source_dates"]) == len(set(roe["source_dates"]))
