"""评测/测试共享 harness：在进程内注册全部 MCP 工具，供静态断言与 LLM 评测复用。

不依赖运行中的 server，也不需要 Tushare token（注册阶段不打 API）。
"""

import asyncio
from typing import Dict, List

from fastmcp import FastMCP

from findatamcp.utils.tushare_api import TushareAPI
from findatamcp.entity_store import EntityStore
from findatamcp.tools import (
    meta, search, market_data, market_statistics, market_flow,
    index_data, analysis, macro_data, financial_data,
    performance_data, fund_data, sector,
)


def build_mcp() -> FastMCP:
    """注册全部 12 个工具模块，返回 FastMCP 实例。"""
    api = TushareAPI()
    db = EntityStore()
    mcp = FastMCP("findata-test")
    meta.register_meta_tools(mcp, api)
    search.register_search_tools(mcp, api, db)
    market_data.register_market_tools(mcp, api)
    market_statistics.register_market_statistics_tools(mcp, api)
    market_flow.register_market_flow_tools(mcp, api)
    index_data.register_index_tools(mcp, api)
    analysis.register_analysis_tools(mcp, api)
    macro_data.register_macro_tools(mcp, api)
    financial_data.register_financial_tools(mcp, api)
    performance_data.register_performance_tools(mcp, api)
    fund_data.register_fund_tools(mcp, api)
    sector.register_sector_tools(mcp, api)
    return mcp


def list_tools() -> List:
    """同步返回已注册工具对象列表（每个含 .name / .description / .parameters）。"""
    mcp = build_mcp()
    return asyncio.run(mcp._list_tools())


def tool_names() -> set:
    return {t.name for t in list_tools()}


def tool_catalog() -> Dict[str, str]:
    """{工具名: 首行描述}，供 LLM 评测构造工具表。"""
    out = {}
    for t in list_tools():
        desc = (t.description or "").strip().split("\n")[0]
        out[t.name] = desc
    return out
