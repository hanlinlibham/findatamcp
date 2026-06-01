"""行情数据工具

提供股票市场数据相关的MCP工具，包括：
- get_stock_data: 获取综合股票数据
- get_latest_daily_close: 获取最新日收盘数据
- get_historical_data: 获取历史数据
- get_moneyflow: 获取资金流向
"""

import asyncio
import pandas as pd
from typing import Annotated, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
from pydantic import Field

from ..cache import cache
from ..entity_store import EntityStore
from ..utils.tushare_api import TushareAPI, fetch_daily_data
from ..utils.large_data_handler import THRESHOLD, handle_large_data, merge_large_data_payload, prepare_large_data_view
from ..utils.ui_hint import append_hint_to_summary
from ..utils.artifact_payload import finalize_artifact_result, AS_FILE_INCLUDE_UI_DECISION_GUIDE
from ..utils.symbol_resolver import (
    build_symbol_not_found,
    is_known_symbol_pattern,
    lookup_by_code,
    lookup_by_name,
    no_data_in_range_response,
    resolve_input,
    unavailable_response,
)
from .constants import INCLUDE_UI_DESCRIPTION, READONLY_ANNOTATIONS
from .routing import attach_next_steps
from ..utils.response import build_error_response
from ..utils.errors import ErrorCode

KLINE_CHART_APP = AppConfig(
    resource_uri="ui://findata/kline-chart",
    visibility=["model", "app"],
)
MONEYFLOW_CHART_APP = AppConfig(
    resource_uri="ui://findata/moneyflow-chart",
    visibility=["model", "app"],
)



def _base_price(df):
    """区间起始基准价：优先用首日 pre_close（前一交易日收盘），正确覆盖假期跳空"""
    if "pre_close" in df.columns and pd.notna(df["pre_close"].iloc[0]):
        return float(df["pre_close"].iloc[0])
    return float(df["close"].iloc[0])


def register_market_tools(mcp: FastMCP, api: TushareAPI, db: Optional[EntityStore] = None):
    """注册行情数据工具"""

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_stock_data(
        ts_code: str,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None,  # 兼容 code 别名
        include_financial: bool = True,  # 过渡开关：False 时跳过财务维度
    ) -> Union[ToolResult, Dict[str, Any]]:
        """获取股票综合快照（行情 + 基础信息 + 可选财务，支持A股/港股/美股）

        本工具是“综合快照”：一次返回实时行情 + 近 60 日行情统计 + 基础信息 +（可选）年报级财务核心项，
        频率混搭。**财务数据建议改用专门工具 get_financial_summary / get_financial_ratios / 三大报表**，
        以获得完整历史与一致口径。后续 include_financial 默认值可能改为 False。

        Args:
            ts_code: 股票代码，支持 '600519.SH'、'00700.HK'、'AAPL' 或裸码
            stock_code: ts_code 的别名
            code: ts_code 的别名
            include_financial: 是否拉取并组装财务核心数据，默认 True（保持现有行为）。
                设为 False 时跳过财务维度，返回里 financial_data 为 None，
                适用于“只要当日快照 + 基础信息”的轻量场景。
        """
        try:
            # 兼容旧参数名
            original_input = ts_code or stock_code or code or ""
            if not original_input:
                return build_error_response(
                    error="请提供股票代码（参数名: ts_code, stock_code 或 code）",
                    error_code=ErrorCode.MISSING_PARAM,
                )

            # 统一解析：名称别名 / 港美 index_global / CBA unavailable
            resolved = resolve_input(original_input, api)
            ts_code = resolved["ts_code"]
            _data_source = resolved["data_source"]

            if _data_source == "unavailable":
                return unavailable_response(resolved)

            comprehensive_data = {
                "ts_code": ts_code,
                "input_code": original_input,
                "collection_time": datetime.now().isoformat(),
                "data_source": "findata_pro" if api.is_available() else "findata_free",
                "api_status": "pro" if api.is_available() else "free"
            }

            market = api.get_market(ts_code) if _data_source != "index_global" else "GLOBAL"

            async def _fetch_global(start_date=None, end_date=None, limit=None):
                kwargs = {"ts_code": ts_code}
                if start_date: kwargs["start_date"] = start_date
                if end_date: kwargs["end_date"] = end_date
                return await asyncio.to_thread(api.pro.index_global, **kwargs)

            # 1. 实时行情数据
            try:
                if api.is_available():
                    if _data_source == "index_global":
                        _end = datetime.now().strftime('%Y%m%d')
                        _start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
                        df = await _fetch_global(start_date=_start, end_date=_end)
                        if df is not None and not df.empty:
                            df = df.sort_values('trade_date')
                            latest = df.iloc[-1].to_dict()
                        else:
                            latest = None
                    else:
                        df = await fetch_daily_data(cache, api, ts_code, cache_type="realtime", limit=1)
                        latest = df.iloc[0].to_dict() if (df is not None and not df.empty) else None

                    if latest is not None:
                        comprehensive_data["realtime_data"] = {
                            "price": latest.get('close'),
                            "change": latest.get('change'),
                            "pct_chg": latest.get('pct_chg'),
                            "changepercent": latest.get('pct_chg'),
                            "open": latest.get('open'),
                            "high": latest.get('high'),
                            "low": latest.get('low'),
                            "pre_close": latest.get('pre_close'),
                            "volume": latest.get('vol'),
                            "amount": latest.get('amount'),
                            "trade_date": latest.get('trade_date')
                        }
                    else:
                        comprehensive_data["realtime_data"] = {"error": "无最新数据"}
                else:
                    comprehensive_data["realtime_data"] = {"error": "数据服务不可用（Pro 接口未配置）"}
            except Exception as e:
                comprehensive_data["realtime_data"] = {"error": f"获取实时数据失败: {str(e)}"}

            # 短暂延迟，避免API限制
            await asyncio.sleep(0.2)

            # 2. 历史行情数据（60天）
            try:
                if api.is_available():
                    end_date = datetime.now().strftime('%Y%m%d')
                    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

                    if _data_source == "index_global":
                        df = await _fetch_global(start_date=start_date, end_date=end_date)
                    else:
                        df = await fetch_daily_data(
                            cache, api, ts_code,
                            cache_type="daily",
                            start_date=start_date,
                            end_date=end_date
                        )

                    if df is not None and not df.empty:
                        df = df.sort_values('trade_date')
                        comprehensive_data["daily_data"] = {
                            "data_count": len(df),
                            "start_date": start_date,
                            "end_date": end_date,
                            "price_statistics": {
                                "max_price": float(df['high'].max()),
                                "min_price": float(df['low'].min()),
                                "avg_price": float(df['close'].mean()),
                                "price_volatility": float(df['pct_chg'].std()) if len(df) > 1 else 0,
                                "max_single_day_gain": float(df['pct_chg'].max()),
                                "max_single_day_loss": float(df['pct_chg'].min())
                            },
                            "trend_statistics": {
                                "total_change": round(float(((df['close'].iloc[-1] / _base_price(df)) - 1) * 100), 2) if len(df) > 0 else 0
                            }
                        }
                    else:
                        comprehensive_data["daily_data"] = {"error": "无历史数据"}
                else:
                    comprehensive_data["daily_data"] = {"error": "数据服务不可用（Pro 接口未配置）"}
            except Exception as e:
                comprehensive_data["daily_data"] = {"error": f"获取历史数据失败: {str(e)}"}

            # 短暂延迟
            await asyncio.sleep(0.2)

            # 3. 基本信息（如果实时数据获取失败）
            if _data_source == "index_global":
                _entry = resolved.get("entry") or {}
                comprehensive_data["basic_info"] = {
                    "ts_code": ts_code,
                    "name": _entry.get("name", ts_code),
                    "category": _entry.get("category"),
                    "data_source": "index_global",
                }
            elif not comprehensive_data.get("realtime_data") or comprehensive_data["realtime_data"].get("error"):
                try:
                    if api.is_available():
                        if market == "HK":
                            df = await cache.cached_call(
                                api.pro.hk_basic,
                                cache_type="basic",
                                ts_code=ts_code,
                                fields='ts_code,name,enname,market,list_status,list_date,delist_date'
                            )
                        elif market == "US":
                            df = await cache.cached_call(
                                api.pro.us_basic,
                                cache_type="basic",
                                ts_code=ts_code,
                                fields='ts_code,name,enname,classify,list_date,delist_date'
                            )
                        else:
                            df = await cache.cached_call(
                                api.pro.stock_basic,
                                cache_type="basic",
                                ts_code=ts_code,
                                fields='ts_code,symbol,name,area,industry,fullname,enname,market,exchange,curr_type,list_status,list_date,delist_date,is_hs'
                            )

                        if not df.empty:
                            basic_info = df.iloc[0].to_dict()
                            comprehensive_data["basic_info"] = basic_info
                        else:
                            comprehensive_data["basic_info"] = {"error": "未找到股票基本信息"}
                    else:
                        comprehensive_data["basic_info"] = {"error": "数据服务不可用（Pro 接口未配置）"}
                except Exception as e:
                    comprehensive_data["basic_info"] = {"error": f"获取基本信息失败: {str(e)}"}
            else:
                comprehensive_data["basic_info"] = {"source": "realtime_data"}

            # 短暂延迟
            await asyncio.sleep(0.2)

            # 4. 财务数据（仅 A 股个股支持；指数 / 港美 跳过）
            #    过渡开关：include_financial=False 时整段跳过，financial_data 置为 None
            _is_a_stock = (
                market == "A"
                and _data_source != "index_global"
                and not api.is_index_code(ts_code)
                and not api.is_fund_code(ts_code)
            )
            if not include_financial:
                comprehensive_data["financial_data"] = None
            elif not _is_a_stock:
                if _data_source == "index_global":
                    _note = f"财务数据不适用于指数（{ts_code} 为港美主流指数）"
                elif api.is_index_code(ts_code):
                    _note = f"财务数据不适用于指数（{ts_code}）"
                elif api.is_fund_code(ts_code):
                    _note = f"财务数据不适用于基金（{ts_code}）"
                elif market == "HK":
                    _note = f"财务数据仅支持A股，当前代码 {ts_code} 为港股"
                elif market == "US":
                    _note = f"财务数据仅支持A股，当前代码 {ts_code} 为美股"
                else:
                    _note = f"财务数据仅支持A股个股，当前代码 {ts_code}"
                comprehensive_data["financial_data"] = {"note": _note}
            else:
                try:
                    if api.is_available():
                        financial_data = {}

                        # 获取利润表核心数据
                        income_df = await cache.cached_call(
                            api.pro.income,
                            cache_type="financial",
                            ts_code=ts_code,
                            limit=1,
                            fields='ts_code,end_date,total_revenue,total_profit,n_income'
                        )

                        if not income_df.empty:
                            latest_income = income_df.iloc[0].to_dict()
                            financial_data["income_core"] = {
                                "total_revenue": latest_income.get('total_revenue', 0),
                                "total_profit": latest_income.get('total_profit', 0),
                                "net_income": latest_income.get('n_income', 0),
                                "end_date": latest_income.get('end_date', '')
                            }

                        # 获取资产负债表核心数据
                        balance_df = await cache.cached_call(
                            api.pro.balancesheet,
                            cache_type="financial",
                            ts_code=ts_code,
                            limit=1,
                            fields='ts_code,end_date,total_assets,total_hldr_eqy_exc_min_int'
                        )

                        if not balance_df.empty:
                            latest_balance = balance_df.iloc[0].to_dict()
                            financial_data["balance_core"] = {
                                "total_assets": latest_balance.get('total_assets', 0),
                                "total_equity": latest_balance.get('total_hldr_eqy_exc_min_int', 0),
                                "end_date": latest_balance.get('end_date', '')
                            }

                        comprehensive_data["financial_data"] = financial_data
                    else:
                        comprehensive_data["financial_data"] = {"error": "数据服务不可用（Pro 接口未配置）"}
                except Exception as e:
                    comprehensive_data["financial_data"] = {"error": f"获取财务数据失败: {str(e)}"}

            # 检查是否有任何有效数据（financial_data 可能为 None，跳过时不计入）
            has_valid_data = any(
                not (data or {}).get("error")
                for data in [
                    comprehensive_data.get("realtime_data", {}),
                    comprehensive_data.get("daily_data", {}),
                    comprehensive_data.get("financial_data", {}),
                ]
                if data is not None
            )

            if has_valid_data:
                result = {
                    "success": True,
                    "ts_code": ts_code,
                    "data": comprehensive_data,
                    "advisory": {
                        "note": "财务维度建议用专门工具(get_financial_summary/get_financial_ratios)以获得完整历史与一致口径",
                        "see": ["get_financial_summary", "get_financial_ratios", "get_historical_data"],
                    },
                    "timestamp": datetime.now().isoformat()
                }
                return attach_next_steps(result, "get_stock_data")
            else:
                return build_error_response(
                    error="无法获取任何有效数据",
                    error_code=ErrorCode.NO_DATA,
                    data={"ts_code": ts_code, "data": comprehensive_data},
                )

        except Exception as e:
            return build_error_response(
                error=f"获取股票综合数据异常: {str(e)}",
                error_code=ErrorCode.NO_DATA,
                data={"ts_code": ts_code if 'ts_code' in locals() else None},
            )

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS, )
    async def get_latest_daily_close(
        ts_code: str,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None  # 兼容 code 别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """获取股票/指数最新收盘价（日线数据，支持A股/港股/美股/指数）

        Args:
            ts_code: 股票或指数代码，支持 '600519.SH'、'00700.HK'、'AAPL'、'000001.SH'(上证指数) 等
            stock_code: ts_code 的别名
            code: ts_code 的别名
        """
        try:
            # 兼容旧参数名
            original_input = ts_code or stock_code or code or ""
            if not original_input:
                return build_error_response(
                    error="请提供股票代码（参数名: ts_code, stock_code 或 code）",
                    error_code=ErrorCode.MISSING_PARAM,
                )

            # 统一解析：名称别名 / 港美 index_global / CBA unavailable
            resolved = resolve_input(original_input, api)
            ts_code = resolved["ts_code"]
            _data_source = resolved["data_source"]

            if _data_source == "unavailable":
                return unavailable_response(resolved)

            if not api.is_available():
                return build_error_response(
                    error="数据服务不可用（Pro 接口未配置）",
                    error_code=ErrorCode.PRO_REQUIRED,
                    data={"ts_code": ts_code},
                )

            if _data_source == "index_global":
                # 港美主流指数走 index_global，取近 10 天最后一行
                _end = datetime.now().strftime('%Y%m%d')
                _start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
                df = await asyncio.to_thread(
                    api.pro.index_global,
                    ts_code=ts_code,
                    start_date=_start,
                    end_date=_end,
                )
                if df is not None and not df.empty:
                    df = df.sort_values('trade_date')
                    latest = df.iloc[-1].to_dict()
                else:
                    latest = None
            else:
                df = await fetch_daily_data(cache, api, ts_code, cache_type="realtime", limit=1)
                latest = df.iloc[0].to_dict() if (df is not None and not df.empty) else None

            if latest is None:
                return build_error_response(
                    error="无最新数据",
                    error_code=ErrorCode.NO_DATA,
                    data={"ts_code": ts_code, "original_input": original_input},
                )

            data = {
                "price": latest.get('close'),
                "change": latest.get('change'),
                "pct_chg": latest.get('pct_chg'),
                "open": latest.get('open'),
                "high": latest.get('high'),
                "low": latest.get('low'),
                "pre_close": latest.get('pre_close'),
                "volume": latest.get('vol'),
                "amount": latest.get('amount'),
                "trade_date": latest.get('trade_date')
            }

            # 计算 asset_type
            if _data_source == "index_global":
                _asset_type = "global_index"
            else:
                _market = api.get_market(ts_code)
                if _market == "HK":
                    _asset_type = "hk"
                elif _market == "US":
                    _asset_type = "us"
                elif api.is_fund_code(ts_code):
                    _asset_type = "fund"
                elif api.is_index_code(ts_code):
                    _asset_type = "index"
                else:
                    _asset_type = "stock"
            if resolved.get("asset_type_hint"):
                _asset_type = resolved["asset_type_hint"]

            # Build concise text summary for LLM
            price = data.get("price")
            pct_chg = data.get("pct_chg")
            amount_val = data.get("amount")
            pct_sign = "+" if pct_chg is not None and pct_chg >= 0 else ""
            amount_yi = round(amount_val / 10000, 2) if amount_val else "N/A"
            summary = f"{ts_code}: 收盘{price}, 涨跌{pct_sign}{pct_chg}%, 成交{amount_yi}亿"

            structured = {
                "success": True,
                "ts_code": ts_code,
                "asset_type": _asset_type,
                "data": data,
                # 向后兼容：保留旧字段名
                "realtime_data": data,
                "meta": {
                    "data_source": "findata_pro",
                    "data_type": "daily_close",
                    "note": "此为日线收盘数据，非盘中实时行情"
                },
                "timestamp": datetime.now().isoformat()
            }

            structured = attach_next_steps(structured, "get_latest_daily_close")

            return ToolResult(
                content=[TextContent(type="text", text=summary)],
                structured_content=structured,
            )

        except Exception as e:
            return {
                "success": False,
                "error": f"获取数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS,
        description='【K线行情】获取股票/指数历史日线走势，含开高低收/成交量/波动率/区间涨跌幅，回答"走势/K线/历史价格"问题首选\n返回形态（默认）：content.text 内联 markdown 表格 + 结构化数据,无内嵌 UI。\n设 include_ui=True 才附加交互式 K 线（ui://findata/kline-chart）。\n\nArgs:\n    ts_code: 股票或指数代码，支持 \'600519.SH\'、\'00700.HK\'、\'AAPL\'、\'399001.SZ\' 等\n    days: 获取天数，默认60，不传 start_date/end_date 时使用\n    start_date: 开始日期(YYYYMMDD)，优先级高于 days\n    end_date: 结束日期(YYYYMMDD)，默认今天\n    include_items: 是否返回每日明细，默认 True\n    max_rows: 明细最大行数，默认30\n    as_file: 为 True 时把完整数据写成 .jsonl 文件，在 structuredContent 里返 path\n    stock_code: ts_code 的别名\n    code: ts_code 的别名\n' + AS_FILE_INCLUDE_UI_DECISION_GUIDE,
    )
    async def get_historical_data(
        ts_code: str,
        days: int = 60,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        include_items: bool = True,
        max_rows: int = 30,
        as_file: bool = False,
        include_ui: Annotated[bool, Field(description=INCLUDE_UI_DESCRIPTION)] = False,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None  # 兼容 code 别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """【K线行情】获取股票/指数历史日线走势，含开高低收/成交量/波动率/区间涨跌幅，回答"走势/K线/历史价格"问题首选"""
        try:
            # 兼容旧参数名
            original_input = ts_code or stock_code or code or ""
            if not original_input:
                return build_error_response(
                    error="请提供股票代码（参数名: ts_code, stock_code 或 code）",
                    error_code=ErrorCode.MISSING_PARAM,
                )

            # 统一解析：名称别名 → INDEX_ENTRIES 命中 → 跳过 normalize；否则 normalize 后再查一次
            resolved = resolve_input(original_input, api)
            ts_code = resolved["ts_code"]
            _data_source = resolved["data_source"]

            if _data_source == "unavailable":
                return unavailable_response(resolved)

            # 获取历史数据
            if api.is_available():
                # 优先级：start_date/end_date > days
                if not end_date:
                    end_date = datetime.now().strftime('%Y%m%d')
                if not start_date:
                    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

                if _data_source == "index_global":
                    # 港美主流指数走 index_global 接口（代码无后缀，如 HSI/SPX/IXIC/DJI）
                    df = await asyncio.to_thread(
                        api.pro.index_global,
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                    )
                else:
                    df = await fetch_daily_data(
                        cache, api, ts_code,
                        cache_type="daily",
                        start_date=start_date,
                        end_date=end_date
                    )

                if df is None or df.empty:
                    # 区分 "代码不存在" vs "代码有效但窗口内无数据"
                    if is_known_symbol_pattern(ts_code, api, resolved.get("entry")):
                        return no_data_in_range_response(
                            ts_code=ts_code,
                            original_input=original_input,
                            start_date=start_date,
                            end_date=end_date,
                            entry=resolved.get("entry"),
                        )
                    return await build_symbol_not_found(ts_code, db, original_input=original_input)

                df = df.sort_values('trade_date')
                full_items = df.to_dict("records")

                # 概要（进 content.text 顶部，不重复进 structuredContent）
                _latest = float(df['close'].iloc[-1])
                _chg = round(float(((df['close'].iloc[-1] / _base_price(df)) - 1) * 100), 2) if len(df) > 0 else 0
                _chg_s = f"+{_chg}%" if _chg >= 0 else f"{_chg}%"
                _header = f"{ts_code} | {len(df)} 个交易日 | 最新 {_latest}, 区间 {_chg_s}"

                if _data_source == "index_global":
                    _asset_type = "global_index"
                else:
                    _market = api.get_market(ts_code)
                    if _market == "HK":
                        _asset_type = "hk"
                    elif _market == "US":
                        _asset_type = "us"
                    elif api.is_index_code(ts_code):
                        _asset_type = "index"
                    else:
                        _asset_type = "stock"
                # resolved 命中条目时优先用 entry 的语义
                if resolved.get("asset_type_hint"):
                    _asset_type = resolved["asset_type_hint"]

                # 扁平 structuredContent —— 数据层只放标识 + 参数 + 时间戳，rows/columns 由 helper 合并
                structured = {
                    "success": True,
                    "ts_code": ts_code,
                    "asset_type": _asset_type,
                    "days": days,
                    "start_date": start_date,
                    "end_date": end_date,
                    "timestamp": datetime.now().isoformat(),
                }

                structured = attach_next_steps(structured, "get_historical_data")

                return finalize_artifact_result(
                    rows=full_items,
                    result=structured,
                    tool_name="get_historical_data",
                    query_params={
                        "ts_code": ts_code,
                        "start_date": start_date,
                        "end_date": end_date,
                        "days": days,
                    },
                    ui_uri="ui://findata/kline-chart",
                    as_file=as_file,
                    include_ui=include_ui,
                    header_text=_header,
                    max_rows_in_text=min(max_rows, 10),
                )
            else:
                return build_error_response(
                    error="数据服务不可用（Pro 接口未配置）",
                    error_code=ErrorCode.PRO_REQUIRED,
                    data={"ts_code": ts_code},
                )
        except Exception as e:
            return {
                "success": False,
                "error": f"获取历史数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS,
        description="【资金流向】获取个股主力/散户净流入金额，含超大单/大单/中单/小单分布与净占比（仅A股）\n返回形态（默认）：content.text 内联 markdown 表格 + 结构化数据,无内嵌 UI。\n设 include_ui=True 才附加交互式资金流向图（ui://findata/moneyflow-chart）。\n\nArgs:\n    ts_code: A股代码，支持 '600519.SH' 或 '600519'\n    start_date: 开始日期(YYYYMMDD)，默认最近30天\n    end_date: 结束日期(YYYYMMDD)，默认今天\n    as_file: 为 True 时把完整数据写成 .jsonl 文件\n    stock_code: ts_code 的别名\n    code: ts_code 的别名\n" + AS_FILE_INCLUDE_UI_DECISION_GUIDE,
    )
    async def get_moneyflow(
        ts_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        as_file: bool = False,
        include_ui: Annotated[bool, Field(description=INCLUDE_UI_DESCRIPTION)] = False,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None  # 兼容 code 别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """【资金流向】获取个股主力/散户净流入金额，含超大单/大单/中单/小单分布与净占比（仅A股）"""
        try:
            # 兼容旧参数名
            ts_code = ts_code or stock_code or code or ""
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 资金流向仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {
                    "success": False,
                    "error": f"资金流向仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"
                }

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            # 默认获取最近30天
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

            df = api.pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df.empty:
                return {"success": False, "error": "未找到资金流向数据", "ts_code": ts_code}

            # 按日期排序
            df = df.sort_values('trade_date')
            data = df.to_dict('records')

            _net_total = sum((r.get("net_mf_amount") or 0) for r in data) / 100000  # 亿
            _net_sign = "+" if _net_total >= 0 else ""
            _header = f"{ts_code} 资金流向 | {start_date}~{end_date} | {len(data)} 个交易日 | 净流入 {_net_sign}{_net_total:.2f} 亿"

            structured = {
                "success": True,
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
                "timestamp": datetime.now().isoformat(),
            }
            return finalize_artifact_result(
                rows=data,
                result=structured,
                tool_name="get_moneyflow",
                query_params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
                ui_uri="ui://findata/moneyflow-chart",
                as_file=as_file,
                include_ui=include_ui,
                header_text=_header,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"获取资金流向数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }