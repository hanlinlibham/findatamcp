"""报错契约断言：枚举非法 → error_code=invalid_enum + valid_values 白名单回显。

只测"枚举校验在打 API 之前"的工具(非法值会被前置拦截,无需 Tushare token)。
需要真实数据的报错自纠(把名称误当代码等)由 tests/eval/run_llm_eval.py 的 LLM 链路覆盖。
"""

import asyncio
import pytest

from tests._harness import build_mcp


def _get_fn(mcp, name):
    tools = asyncio.run(mcp._list_tools())
    for t in tools:
        if t.name == name:
            return t.fn
    raise AssertionError(f"tool not found: {name}")


@pytest.fixture(scope="module")
def mcp():
    return build_mcp()


@pytest.mark.parametrize("tool,kwargs,bad_field", [
    ("compute_correlation", {"stock_codes": ["600519.SH", "000858.SZ"], "basis": "bogus"}, "basis"),
    ("compute_correlation", {"stock_codes": ["600519.SH", "000858.SZ"], "basis": "price", "mode": "bogus"}, "mode"),
    ("get_market_extremes", {"metric": "bogus"}, "metric"),
    # 注: get_industry_overview.action 是 Literal 类型,由 schema 层拦截非法值,
    #     真实 MCP 调用到不了函数体,故不在此用例集内。
    ("analyze_stock_performance", {"stock_codes": ["600519.SH"], "analysis_type": "bogus"}, "analysis_type"),
])
def test_invalid_enum_returns_whitelist(mcp, tool, kwargs, bad_field):
    fn = _get_fn(mcp, tool)
    res = asyncio.run(fn(**kwargs))
    # 兼容 dict / ToolResult.structured_content
    data = res if isinstance(res, dict) else getattr(res, "structured_content", {})
    assert data.get("success") is False, f"{tool} 非法 {bad_field} 应失败: {data}"
    assert data.get("error_code") == "invalid_enum", data
    assert data.get("valid_values"), f"{tool} 应回显 valid_values 白名单: {data}"


def test_deprecated_tools_carry_marker(mcp):
    """改名/合并后的旧名 facade 成功返回应带 deprecation 标记(此处只校验静态描述前缀)。"""
    tools = asyncio.run(mcp._list_tools())
    by_name = {t.name: t for t in tools}
    for old in ["analyze_price_correlation", "calculate_metrics",
                "get_financial_indicators", "get_financial_indicator"]:
        assert old in by_name, f"facade {old} 必须保留"
        assert "DEPRECATED" in (by_name[old].description or ""), \
            f"{old} 描述应标 [DEPRECATED→...]"
