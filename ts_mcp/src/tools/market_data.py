"""行情数据工具

提供股票市场数据相关的MCP工具，包括：
- get_stock_data: 获取综合股票数据
- get_latest_daily_close: 获取最新日收盘数据
- get_historical_data: 获取历史数据
- get_moneyflow: 获取资金流向
"""

import asyncio
import pandas as pd
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..cache import cache
from ..utils.tushare_api import TushareAPI, fetch_daily_data
from ..utils.large_data_handler import THRESHOLD, handle_large_data, merge_large_data_payload, prepare_large_data_view
from ..utils.ui_hint import append_hint_to_summary
from .constants import READONLY_ANNOTATIONS

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


def register_market_tools(mcp: FastMCP, api: TushareAPI):
    """注册行情数据工具"""

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_stock_data(
        ts_code: str,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None  # 兼容 code 别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """获取股票综合数据（行情+财务+基础信息，支持A股/港股/美股）

        Args:
            ts_code: 股票代码，支持 '600519.SH'、'00700.HK'、'AAPL' 或裸码
            stock_code: ts_code 的别名
            code: ts_code 的别名
        """
        try:
            # 兼容旧参数名
            ts_code = ts_code or stock_code or code or ""
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            # 标准化股票代码
            ts_code = api.normalize_stock_code(ts_code)

            comprehensive_data = {
                "ts_code": ts_code,
                "input_code": ts_code,
                "collection_time": datetime.now().isoformat(),
                "data_source": "findata_pro" if api.is_available() else "findata_free",
                "api_status": "pro" if api.is_available() else "free"
            }

            market = api.get_market(ts_code)

            # 1. 实时行情数据（通过 fetch_daily_data 路由）
            try:
                if api.is_available():
                    df = await fetch_daily_data(cache, api, ts_code, cache_type="realtime", limit=1)
                    if not df.empty:
                        latest = df.iloc[0].to_dict()
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

            # 2. 历史行情数据（60天，通过 fetch_daily_data 路由）
            try:
                if api.is_available():
                    end_date = datetime.now().strftime('%Y%m%d')
                    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

                    df = await fetch_daily_data(
                        cache, api, ts_code,
                        cache_type="daily",
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    if not df.empty:
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
            if not comprehensive_data.get("realtime_data") or comprehensive_data["realtime_data"].get("error"):
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

            # 4. 财务数据（仅 A 股支持）
            if market != "A":
                comprehensive_data["financial_data"] = {
                    "note": f"财务数据仅支持A股，当前代码 {ts_code} 为{'港股' if market == 'HK' else '美股'}"
                }
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

            # 检查是否有任何有效数据
            has_valid_data = any(
                not data.get("error")
                for data in [
                    comprehensive_data.get("realtime_data", {}),
                    comprehensive_data.get("daily_data", {}),
                    comprehensive_data.get("financial_data", {})
                ]
            )

            if has_valid_data:
                return {
                    "success": True,
                    "ts_code": ts_code,
                    "data": comprehensive_data,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "无法获取任何有效数据",
                    "ts_code": ts_code,
                    "data": comprehensive_data
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"获取股票综合数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

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
            ts_code = ts_code or stock_code or code or ""
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            if api.is_available():
                df = await fetch_daily_data(cache, api, ts_code, cache_type="realtime", limit=1)
                if df is not None and not df.empty:
                    latest = df.iloc[0].to_dict()
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
                else:
                    return {
                        "success": False,
                        "error": "无最新数据",
                        "ts_code": ts_code
                    }
            else:
                return {
                    "success": False,
                    "error": "数据服务不可用（Pro 接口未配置）",
                    "ts_code": ts_code
                }

            # 计算 asset_type
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

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS, app=KLINE_CHART_APP)
    async def get_historical_data(
        ts_code: str,
        days: int = 60,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        include_items: bool = True,
        max_rows: int = 30,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None  # 兼容 code 别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """获取股票/指数历史数据及统计指标（波动率、区间涨跌幅、价格区间）

        Args:
            ts_code: 股票或指数代码，支持 '600519.SH'、'00700.HK'、'AAPL'、'399001.SZ' 等
            days: 获取天数，默认60，不传 start_date/end_date 时使用
            start_date: 开始日期(YYYYMMDD)，优先级高于 days
            end_date: 结束日期(YYYYMMDD)，默认今天
            include_items: 是否返回每日明细，默认 True
            max_rows: 明细最大行数，默认30
            stock_code: ts_code 的别名
            code: ts_code 的别名
        """
        try:
            # 兼容旧参数名
            ts_code = ts_code or stock_code or code or ""
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            # 标准化股票代码
            ts_code = api.normalize_stock_code(ts_code)

            # 获取历史数据
            if api.is_available():
                # 优先级：start_date/end_date > days
                if not end_date:
                    end_date = datetime.now().strftime('%Y%m%d')
                if not start_date:
                    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

                df = await fetch_daily_data(
                    cache, api, ts_code,
                    cache_type="daily",
                    start_date=start_date,
                    end_date=end_date
                )

                if df is not None and not df.empty:
                    df = df.sort_values('trade_date')

                    # 计算统计指标
                    daily_data = {
                        "data_count": len(df),
                        "start_date": start_date,
                        "end_date": end_date,
                        "price_statistics": {
                            "max_price": float(df['high'].max()),
                            "min_price": float(df['low'].min()),
                            "avg_price": round(float(df['close'].mean()), 2),
                            "latest_price": float(df['close'].iloc[-1]),
                            "price_volatility": round(float(df['pct_chg'].std()), 4) if len(df) > 1 else 0,
                            "max_single_day_gain": float(df['pct_chg'].max()),
                            "max_single_day_loss": float(df['pct_chg'].min())
                        },
                        "trend_statistics": {
                            "total_change": round(float(((df['close'].iloc[-1] / _base_price(df)) - 1) * 100), 2) if len(df) > 0 else 0
                        }
                    }

                    full_items = df.to_dict("records")
                    large_items = None
                    if len(full_items) > THRESHOLD:
                        inline_limit = max(1, min(max_rows, 120))
                        large_items = handle_large_data(
                            full_items,
                            "get_historical_data",
                            {
                                "ts_code": ts_code,
                                "start_date": start_date,
                                "end_date": end_date,
                                "days": days,
                            },
                            preview_rows=inline_limit,
                            preview_mode="tail",
                        )

                    # P1-3: 默认不返回详细列表，减少返回体大小
                    if include_items:
                        inline_limit = max_rows
                        if large_items and "is_truncated" in large_items:
                            inline_limit = max(1, min(max_rows, 120))
                        items_df = df.tail(inline_limit) if len(df) > inline_limit else df
                        daily_data["items"] = items_df.to_dict("records")
                        daily_data["items_truncated"] = len(df) > inline_limit
                        if len(df) > inline_limit:
                            note = f"仅内联最近 {inline_limit} 条，共 {len(df)} 条"
                            if large_items and "is_truncated" in large_items:
                                note += f"；完整数据请读取 {large_items['resource_uri']}"
                            daily_data["items_note"] = note
                        if large_items and "is_truncated" in large_items:
                            daily_data["items_resource_uri"] = large_items["resource_uri"]
                else:
                    daily_data = {"error": "无历史数据"}
            else:
                daily_data = {"error": "数据服务不可用（Pro 接口未配置）"}

            if daily_data and not daily_data.get("error"):
                # 计算 asset_type
                _market = api.get_market(ts_code)
                if _market == "HK":
                    _asset_type = "hk"
                elif _market == "US":
                    _asset_type = "us"
                elif api.is_index_code(ts_code):
                    _asset_type = "index"
                else:
                    _asset_type = "stock"

                structured = {
                    "success": True,
                    "ts_code": ts_code,
                    "asset_type": _asset_type,
                    "daily_data": daily_data,
                    "days": days,
                    "start_date": start_date,
                    "end_date": end_date,
                    "timestamp": datetime.now().isoformat()
                }
                if large_items and "is_truncated" in large_items:
                    structured = merge_large_data_payload(structured, large_items)
                # Build text summary for LLM
                _stats = daily_data.get("price_statistics", {})
                _trend = daily_data.get("trend_statistics", {})
                _chg = _trend.get("total_change", 0)
                _chg_s = f"+{_chg}%" if _chg >= 0 else f"{_chg}%"
                _summary = f"{ts_code}: 最新{_stats.get('latest_price','-')}, 区间{_chg_s}, 最高{_stats.get('max_price','-')}, 最低{_stats.get('min_price','-')}, {daily_data.get('data_count',0)}个交易日"
                _items_count = len(daily_data.get("items", []) or [])
                _items_truncated = bool(daily_data.get("items_truncated", False))
                _vol = _stats.get("price_volatility")
                _max_up = _stats.get("max_single_day_gain")
                _max_dn = _stats.get("max_single_day_loss")
                _extra = None
                if _vol is not None and _max_up is not None and _max_dn is not None:
                    _extra = f"波动率{_vol}%, 最大单日涨+{_max_up}%/跌{_max_dn}%"
                _data_uri = large_items.get("resource_uri") if (large_items and "is_truncated" in large_items) else None
                _summary = append_hint_to_summary(
                    _summary,
                    "ui://findata/kline-chart",
                    items_path="daily_data.items",
                    items_count=_items_count,
                    truncated=_items_truncated,
                    extra_stats=_extra,
                    data_resource_uri=_data_uri,
                )
                return ToolResult(
                    content=[TextContent(type="text", text=_summary)],
                    structured_content=structured,
                )
            else:
                return {
                    "success": False,
                    "error": daily_data.get("error", "无法获取历史数据"),
                    "ts_code": ts_code
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取历史数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"行情数据"}, annotations=READONLY_ANNOTATIONS, app=MONEYFLOW_CHART_APP)
    async def get_moneyflow(
        ts_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        stock_code: Optional[str] = None,  # 兼容旧参数名
        code: Optional[str] = None  # 兼容 code 别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """获取个股资金流向（主力/散户净流入，仅A股）

        Args:
            ts_code: A股代码，支持 '600519.SH' 或 '600519'
            start_date: 开始日期(YYYYMMDD)，默认最近30天
            end_date: 结束日期(YYYYMMDD)，默认今天
            stock_code: ts_code 的别名
            code: ts_code 的别名
        """
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

            large_payload, _, ui_rows = prepare_large_data_view(
                data,
                "get_moneyflow",
                {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
                preview_rows=30,
                preview_mode="tail",
            )
            structured = {
                "success": True,
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
                "count": len(data),
                "data": ui_rows,
                "timestamp": datetime.now().isoformat()
            }
            structured = merge_large_data_payload(structured, large_payload)
            if "is_truncated" in large_payload:
                structured["data_note"] = f"图表内联 {len(ui_rows)} 条，完整数据请读取 {large_payload['resource_uri']}"

            # Text summary for LLM
            _net_total = sum((r.get("net_mf_amount") or 0) for r in data) / 100000  # 亿
            _net_sign = "+" if _net_total >= 0 else ""
            _summary = f"{ts_code} 资金流向: {start_date}~{end_date}, {len(data)}个交易日, 净流入{_net_sign}{_net_total:.2f}亿"
            _data_uri = large_payload.get("resource_uri") if "is_truncated" in large_payload else None
            _summary = append_hint_to_summary(
                _summary,
                "ui://findata/moneyflow-chart",
                items_path="data",
                items_count=len(ui_rows),
                truncated=bool("is_truncated" in large_payload),
                data_resource_uri=_data_uri,
            )
            return ToolResult(
                content=[TextContent(type="text", text=_summary)],
                structured_content=structured,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"获取资金流向数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }