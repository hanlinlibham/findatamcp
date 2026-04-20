"""
市场统计聚合工具 (P0-1)

提供全市场统计数据，包括：
- get_market_summary: 全市场均值/中位数/分位数/涨跌家数
- get_market_extremes: 涨幅/跌幅 Top N
- get_batch_pct_chg: 批量股票区间累计涨跌幅
"""

import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
import pandas as pd
import numpy as np
import logging

from ..cache import cache
from ..utils.tushare_api import TushareAPI, fetch_daily_data
from ..utils.data_processing import adjust_date_to_trading_day, get_latest_trading_day
from ..utils.response import build_success_response, build_error_response, build_meta
from ..utils.errors import ErrorCode
from ..utils.ui_hint import append_hint_to_summary
from ..utils.artifact_payload import finalize_artifact_result, AS_FILE_INCLUDE_UI_DECISION_GUIDE

logger = logging.getLogger(__name__)

MARKET_DASHBOARD_APP = AppConfig(
    resource_uri="ui://findata/market-dashboard",
    visibility=["model", "app"],
)
MARKET_DASHBOARD_APP_ONLY = AppConfig(
    resource_uri="ui://findata/market-dashboard",
    visibility=["app"],
)
DATA_TABLE_APP = AppConfig(
    resource_uri="ui://findata/data-table",
    visibility=["model", "app"],
)


def register_market_statistics_tools(mcp: FastMCP, api: TushareAPI):
    """注册市场统计工具"""

    @mcp.tool(tags={"市场统计"}, app=MARKET_DASHBOARD_APP)
    async def get_market_summary(
        trade_date: Optional[str] = None,
        market: str = "all",
        include_st: bool = False,
        as_file: bool = False,
        include_ui: bool = True,
    ) -> Union[ToolResult, Dict[str, Any]]:
        """
        【市场概况】一次调用获取A股整体涨跌/成交/涨停跌停统计

        这是回答"市场整体表现"类问题的首选工具。

        📌 适用场景 (高优先级):
        - "今天A股平均涨幅是多少" → 用此工具
        - "今天上涨的股票有多少只"
        - "今天有多少只涨停"
        - "创业板整体表现如何" → market="CYB"
        - "今天成交额是多少"
        - 任何关于"市场整体/平均"的问题

        📌 不适用场景:
        - 问某只具体股票 → 用 get_latest_daily_close
        - 问涨幅最高的是哪只 → 用 get_market_extremes
        - 问行业均值 → 用 get_sector_top_stocks + get_batch_pct_chg

        Args:
            trade_date: 交易日期 (YYYYMMDD)，默认自动取最近交易日
            market: 市场筛选
                   - "all": 全部A股（默认，最常用）
                   - "CYB": 创业板（300开头）
                   - "KCB": 科创板（688开头）
                   - "SH": 上海主板 / "SZ": 深圳主板 / "BJ": 北交所
            include_st: 是否包含ST股票，默认 False

        Returns:
            {
              "success": true,
              "data": {
                "trade_date": "20260127",
                "total_stocks": 5200,
                "pct_chg_stats": {
                  "mean": 0.85,      # ⭐ 平均涨幅%
                  "median": 0.65,    # 中位数
                  "max": 20.01,      # 最大涨幅
                  "min": -10.03      # 最大跌幅
                },
                "advance_decline": {
                  "advance": 3500,   # ⭐ 上涨家数
                  "decline": 1500,   # ⭐ 下跌家数
                  "flat": 200
                },
                "limit_stats": {
                  "limit_up": 85,    # ⭐ 涨停数
                  "limit_down": 12   # ⭐ 跌停数
                },
                "amount_stats": {
                  "total": 12500.5   # ⭐ 总成交额(亿元)
                }
              }
            }
        """
        try:
            if not api.is_available():
                return build_error_response("数据服务不可用（Pro 接口未配置）", ErrorCode.PRO_REQUIRED)

            # 日期处理
            if not trade_date:
                trade_date = datetime.now().strftime('%Y%m%d')

            # 日期容错
            adjusted_date, date_msg = await adjust_date_to_trading_day(cache, api, trade_date)
            date_adjusted = bool(date_msg)

            # 获取全市场日线数据
            try:
                df_daily = await cache.cached_call(
                    api.pro.daily,
                    cache_type="daily",
                    trade_date=adjusted_date
                )
            except Exception as e:
                return build_error_response(f"获取日线数据失败: {str(e)}", ErrorCode.UPSTREAM_ERROR)

            if df_daily.empty:
                return build_error_response(
                    f"未找到 {adjusted_date} 的市场数据",
                    ErrorCode.NO_DATA
                )

            # 市场筛选
            if market != "all":
                market_filters = {
                    "SH": lambda x: x.endswith('.SH') and x[:3] == '600',
                    "SZ": lambda x: x.endswith('.SZ') and x[:3] == '000',
                    "CYB": lambda x: x.endswith('.SZ') and x[:3] == '300',
                    "KCB": lambda x: x.endswith('.SH') and x[:3] == '688',
                    "BJ": lambda x: x.endswith('.BJ')
                }
                if market in market_filters:
                    mask = df_daily['ts_code'].apply(market_filters[market])
                    df_daily = df_daily[mask]

            # 排除 ST 股票
            if not include_st:
                # 获取股票基本信息来过滤 ST
                try:
                    df_basic = await cache.cached_call(
                        api.pro.stock_basic,
                        cache_type="basic",
                        exchange='',
                        list_status='L',
                        fields='ts_code,name'
                    )
                    if not df_basic.empty:
                        st_codes = df_basic[df_basic['name'].str.contains('ST', case=False, na=False)]['ts_code'].tolist()
                        df_daily = df_daily[~df_daily['ts_code'].isin(st_codes)]
                except Exception as e:
                    logger.warning(f"⚠️ 过滤ST股票失败: {e}")

            total_stocks = len(df_daily)
            if total_stocks == 0:
                return build_error_response("筛选后无数据", ErrorCode.NO_DATA)

            # 计算统计数据
            pct_chg = df_daily['pct_chg'].dropna()

            # 涨跌幅统计
            pct_chg_stats = {
                "mean": round(float(pct_chg.mean()), 4),
                "median": round(float(pct_chg.median()), 4),
                "std": round(float(pct_chg.std()), 4),
                "min": round(float(pct_chg.min()), 4),
                "max": round(float(pct_chg.max()), 4),
                "q25": round(float(pct_chg.quantile(0.25)), 4),
                "q75": round(float(pct_chg.quantile(0.75)), 4),
                "q10": round(float(pct_chg.quantile(0.10)), 4),
                "q90": round(float(pct_chg.quantile(0.90)), 4)
            }

            # 涨跌家数
            advance = int((pct_chg > 0).sum())
            decline = int((pct_chg < 0).sum())
            flat = int((pct_chg == 0).sum())

            advance_decline = {
                "advance": advance,
                "decline": decline,
                "flat": flat,
                "advance_ratio": round(advance / total_stocks * 100, 2),
                "decline_ratio": round(decline / total_stocks * 100, 2)
            }

            # 涨停跌停统计
            limit_up = int((pct_chg >= 9.9).sum())  # 简化判断，实际可能需要考虑ST
            limit_down = int((pct_chg <= -9.9).sum())

            limit_stats = {
                "limit_up": limit_up,
                "limit_down": limit_down,
                "limit_up_ratio": round(limit_up / total_stocks * 100, 2),
                "limit_down_ratio": round(limit_down / total_stocks * 100, 2)
            }

            # 成交额统计（亿元）
            amount = df_daily['amount'].dropna() / 10000  # 千元 -> 亿元
            amount_stats = {
                "total": round(float(amount.sum()), 2),
                "mean": round(float(amount.mean()), 4),
                "median": round(float(amount.median()), 4),
                "max": round(float(amount.max()), 2)
            }

            # 换手率统计（如果有数据）
            turnover_stats = None
            try:
                df_basic_daily = await cache.cached_call(
                    api.pro.daily_basic,
                    cache_type="daily",
                    trade_date=adjusted_date,
                    fields='ts_code,turnover_rate,pe_ttm,pb,total_mv'
                )
                if not df_basic_daily.empty:
                    # 合并筛选
                    df_basic_daily = df_basic_daily[df_basic_daily['ts_code'].isin(df_daily['ts_code'])]
                    turnover = df_basic_daily['turnover_rate'].dropna()
                    if len(turnover) > 0:
                        turnover_stats = {
                            "mean": round(float(turnover.mean()), 4),
                            "median": round(float(turnover.median()), 4),
                            "max": round(float(turnover.max()), 2)
                        }

                    # PE/PB 统计
                    pe = df_basic_daily['pe_ttm'].dropna()
                    pb = df_basic_daily['pb'].dropna()
                    # 过滤异常值
                    pe = pe[(pe > 0) & (pe < 1000)]
                    pb = pb[(pb > 0) & (pb < 100)]

                    valuation_stats = {
                        "pe_median": round(float(pe.median()), 2) if len(pe) > 0 else None,
                        "pb_median": round(float(pb.median()), 2) if len(pb) > 0 else None
                    }
            except Exception as e:
                logger.warning(f"⚠️ 获取换手率/估值数据失败: {e}")
                valuation_stats = {}

            # 构建响应
            data = {
                "trade_date": adjusted_date,
                "market": market,
                "include_st": include_st,
                "total_stocks": total_stocks,
                "pct_chg_stats": pct_chg_stats,
                "advance_decline": advance_decline,
                "limit_stats": limit_stats,
                "amount_stats": amount_stats
            }

            if turnover_stats:
                data["turnover_stats"] = turnover_stats

            if valuation_stats:
                data["valuation_stats"] = valuation_stats

            meta = build_meta(
                trade_date=adjusted_date,
                date_adjusted=date_adjusted,
                date_adjust_message=date_msg if date_adjusted else None,
                coverage=total_stocks,
                market_filter=market
            )

            # Build concise text summary for LLM (~100 tokens)
            market_label = {"all": "A股", "CYB": "创业板", "KCB": "科创板", "SH": "沪主板", "SZ": "深主板", "BJ": "北交所"}.get(market, "A股")
            mean_sign = "+" if pct_chg_stats["mean"] >= 0 else ""
            summary = (
                f"{market_label}({adjusted_date}): "
                f"上涨{advance}只({advance_decline['advance_ratio']}%), "
                f"下跌{decline}只, "
                f"涨停{limit_up}只, "
                f"成交{int(amount_stats['total'])}亿. "
                f"平均涨幅{mean_sign}{pct_chg_stats['mean']}%"
            )

            structured = {
                "success": True,
                "data": data,
                "meta": meta,
                "timestamp": datetime.now().isoformat()
            }

            _ms_rows = [data] if isinstance(data, dict) else list(data or [])
            return finalize_artifact_result(
                rows=_ms_rows,
                result=structured,
                tool_name="get_market_summary",
                query_params={"trade_date": adjusted_date, "market": market, "include_st": include_st},
                ui_uri="ui://findata/market-dashboard",
                as_file=as_file,
                include_ui=include_ui,
                header_text=summary,
            )

        except Exception as e:
            logger.error(f"❌ get_market_summary error: {e}")
            return build_error_response(f"获取市场统计异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"市场统计"})
    async def get_market_extremes(
        trade_date: Optional[str] = None,
        metric: str = "pct_chg",
        market: str = "all",
        top_n: int = 10,
        include_st: bool = False
    ) -> Union[ToolResult, Dict[str, Any]]:
        """
        【涨跌排行】获取涨幅/跌幅最大的股票列表

        同时返回涨幅 Top N 和跌幅 Top N 两个列表。

        📌 适用场景 (高优先级):
        - "今天涨幅最高的股票是哪几只" → 用此工具
        - "跌幅最大的前10名"
        - "创业板涨幅排名"
        - "今天成交额最大的股票" → metric="amount"
        - "换手率最高的股票" → metric="turnover_rate"

        📌 不适用场景:
        - 问市场平均涨幅 → 用 get_market_summary
        - 问某只具体股票涨跌 → 用 get_latest_daily_close
        - 问行业整体表现 → 用 get_sector_top_stocks

        Args:
            trade_date: 交易日期 (YYYYMMDD)，默认最近交易日
            metric: 排序指标
                   - "pct_chg": 涨跌幅（默认，最常用）
                   - "amount": 成交额
                   - "turnover_rate": 换手率
            market: 市场筛选 ("all"/"CYB"/"KCB"/"SH"/"SZ"/"BJ")
            top_n: 返回数量，默认 10，最大 50
            include_st: 是否包含 ST，默认 False

        Returns:
            {
              "success": true,
              "data": {
                "trade_date": "20260127",
                "top_gainers": [
                  {"ts_code": "301xxx.SZ", "name": "某某股份", "pct_chg": 20.01, "close": 25.6, "industry": "电子"},
                  ...
                ],
                "top_losers": [
                  {"ts_code": "300xxx.SZ", "name": "某某科技", "pct_chg": -10.03, "close": 8.5, "industry": "软件"},
                  ...
                ],
                "total_stocks": 5200
              }
            }
        """
        try:
            if not api.is_available():
                return build_error_response("数据服务不可用（Pro 接口未配置）", ErrorCode.PRO_REQUIRED)

            # 日期处理
            if not trade_date:
                trade_date = datetime.now().strftime('%Y%m%d')

            adjusted_date, date_msg = await adjust_date_to_trading_day(cache, api, trade_date)
            date_adjusted = bool(date_msg)

            # 获取日线数据
            df_daily = await cache.cached_call(
                api.pro.daily,
                cache_type="daily",
                trade_date=adjusted_date
            )

            if df_daily.empty:
                return build_error_response(f"未找到 {adjusted_date} 的市场数据", ErrorCode.NO_DATA)

            # 获取股票名称
            df_basic = await cache.cached_call(
                api.pro.stock_basic,
                cache_type="basic",
                exchange='',
                list_status='L',
                fields='ts_code,name,industry'
            )

            # 合并名称
            if not df_basic.empty:
                df_daily = df_daily.merge(df_basic[['ts_code', 'name', 'industry']], on='ts_code', how='left')

                # 排除 ST
                if not include_st:
                    df_daily = df_daily[~df_daily['name'].str.contains('ST', case=False, na=False)]

            # 市场筛选
            if market != "all":
                market_filters = {
                    "SH": lambda x: x.endswith('.SH') and x[:3] == '600',
                    "SZ": lambda x: x.endswith('.SZ') and x[:3] == '000',
                    "CYB": lambda x: x.endswith('.SZ') and x[:3] == '300',
                    "KCB": lambda x: x.endswith('.SH') and x[:3] == '688',
                    "BJ": lambda x: x.endswith('.BJ')
                }
                if market in market_filters:
                    mask = df_daily['ts_code'].apply(market_filters[market])
                    df_daily = df_daily[mask]

            if len(df_daily) == 0:
                return build_error_response("筛选后无数据", ErrorCode.NO_DATA)

            # 根据指标排序
            sort_col = metric
            if metric == "turnover_rate":
                # 需要获取 daily_basic 数据
                df_basic_daily = await cache.cached_call(
                    api.pro.daily_basic,
                    cache_type="daily",
                    trade_date=adjusted_date,
                    fields='ts_code,turnover_rate'
                )
                if not df_basic_daily.empty:
                    df_daily = df_daily.merge(df_basic_daily, on='ts_code', how='left')
                else:
                    return build_error_response("无法获取换手率数据", ErrorCode.NO_DATA)

            # 涨幅 Top N
            df_sorted_desc = df_daily.sort_values(sort_col, ascending=False).head(top_n)
            top_gainers = []
            for _, row in df_sorted_desc.iterrows():
                item = {
                    "ts_code": row['ts_code'],
                    "name": row.get('name', row['ts_code']),
                    "industry": row.get('industry', ''),
                    "close": round(float(row['close']), 2),
                    "pct_chg": round(float(row['pct_chg']), 2),
                    "amount": round(float(row['amount']) / 10000, 2)  # 亿元
                }
                if metric == "turnover_rate" and 'turnover_rate' in row:
                    item["turnover_rate"] = round(float(row['turnover_rate']), 2)
                top_gainers.append(item)

            # 跌幅 Top N
            df_sorted_asc = df_daily.sort_values(sort_col, ascending=True).head(top_n)
            top_losers = []
            for _, row in df_sorted_asc.iterrows():
                item = {
                    "ts_code": row['ts_code'],
                    "name": row.get('name', row['ts_code']),
                    "industry": row.get('industry', ''),
                    "close": round(float(row['close']), 2),
                    "pct_chg": round(float(row['pct_chg']), 2),
                    "amount": round(float(row['amount']) / 10000, 2)
                }
                if metric == "turnover_rate" and 'turnover_rate' in row:
                    item["turnover_rate"] = round(float(row['turnover_rate']), 2)
                top_losers.append(item)

            data = {
                "trade_date": adjusted_date,
                "metric": metric,
                "market": market,
                "top_n": top_n,
                "top_gainers": top_gainers,
                "top_losers": top_losers,
                "total_stocks": len(df_daily)
            }

            meta = build_meta(
                trade_date=adjusted_date,
                date_adjusted=date_adjusted,
                date_adjust_message=date_msg if date_adjusted else None,
                coverage=len(df_daily)
            )

            # Build concise text summary for LLM
            top3_gain = "; ".join(
                f"{g['name']} {'+' if g['pct_chg'] >= 0 else ''}{g['pct_chg']}%"
                for g in top_gainers[:3]
            )
            top3_loss = "; ".join(
                f"{l['name']} {l['pct_chg']}%"
                for l in top_losers[:3]
            )
            summary = f"涨幅前3: {top3_gain}; 跌幅前3: {top3_loss}"

            structured = {
                "success": True,
                "data": data,
                "meta": meta,
                "timestamp": datetime.now().isoformat()
            }

            return ToolResult(
                content=[TextContent(type="text", text=summary)],
                structured_content=structured,
            )

        except Exception as e:
            logger.error(f"❌ get_market_extremes error: {e}")
            return build_error_response(f"获取市场极值异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"市场统计"}, app=DATA_TABLE_APP)
    async def get_batch_pct_chg(
        stock_codes: Optional[List[str]] = None,
        start_date: str = "",
        end_date: Optional[str] = None,
        as_file: bool = False,
        include_ui: bool = True,
        ts_codes: Optional[List[str]] = None,  # 兼容别名
        codes: Optional[List[str]] = None  # 兼容别名
    ) -> Union[ToolResult, Dict[str, Any]]:
        """
        【批量涨跌幅】计算多只股票的区间累计涨跌幅，并返回均值

        ⭐ 这是计算"行业均值"的核心工具，通常配合 get_sector_top_stocks 使用。

        📌 适用场景:
        - "白酒行业今年涨了多少" → 先 get_sector_top_stocks 获取白酒股，再用此工具
        - "这几只股票近3个月表现如何"
        - "我的持仓组合收益率是多少"
        - 需要计算多只股票的平均涨跌幅

        📌 推荐使用流程:
        1. get_sector_top_stocks(sector_name="白酒") → 获取 codes 列表
        2. get_batch_pct_chg(codes, "20260101") → 获取区间涨跌幅
        3. 取 statistics.mean 即为行业均值

        📌 不适用场景:
        - 只有一只股票 → 用 get_historical_data
        - 需要单日涨跌 → 用 get_latest_daily_close

        Args:
            stock_codes: 股票代码列表，如 ["600519.SH", "000858.SZ"]
                        ⭐ 可直接传入 get_sector_top_stocks 返回的 codes 字段
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)，默认最近交易日

        Returns:
            {
              "success": true,
              "data": {
                "results": [
                  {"ts_code": "600519.SH", "name": "贵州茅台", "pct_chg": 15.6, "start_price": 1500, "end_price": 1734},
                  {"ts_code": "000858.SZ", "name": "五粮液", "pct_chg": 8.2, ...},
                  ...
                ],
                "statistics": {
                  "mean": 10.5,     # ⭐ 行业/组合均值
                  "median": 9.8,
                  "std": 4.2,
                  "min": 2.1,
                  "max": 18.3,
                  "count": 10
                }
              }
            }
        """
        try:
            # 兼容别名参数
            stock_codes = stock_codes or ts_codes or codes
            if not start_date:
                return build_error_response("请提供开始日期（参数名: start_date）", ErrorCode.SCHEMA_ERROR)

            if not api.is_available():
                return build_error_response("数据服务不可用（Pro 接口未配置）", ErrorCode.PRO_REQUIRED)

            if not stock_codes:
                return build_error_response("股票代码列表不能为空（参数名: stock_codes, ts_codes 或 codes）", ErrorCode.SCHEMA_ERROR)

            # 日期处理
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')

            adjusted_end, end_msg = await adjust_date_to_trading_day(cache, api, end_date)
            date_adjusted = bool(end_msg)

            # 标准化股票代码
            normalized_codes = [api.normalize_stock_code(c) for c in stock_codes]

            # 获取 A 股名称
            df_basic = await cache.cached_call(
                api.pro.stock_basic,
                cache_type="basic",
                exchange='',
                list_status='L',
                fields='ts_code,name'
            )
            name_map = {}
            if not df_basic.empty:
                name_map = dict(zip(df_basic['ts_code'], df_basic['name']))

            # 获取指数名称
            index_codes = [c for c in normalized_codes if api.get_market(c) == "A" and api.is_index_code(c)]
            if index_codes:
                try:
                    idx_df = await cache.cached_call(
                        api.pro.index_basic,
                        cache_type="basic",
                        fields='ts_code,name'
                    )
                    if idx_df is not None and not idx_df.empty:
                        name_map.update(dict(zip(idx_df['ts_code'], idx_df['name'])))
                except Exception as e:
                    logger.warning(f"⚠️ 获取指数名称失败: {e}")

            # 获取港股名称
            hk_codes = [c for c in normalized_codes if api.get_market(c) == "HK"]
            if hk_codes:
                try:
                    hk_df = await cache.cached_call(
                        api.pro.hk_basic,
                        cache_type="basic",
                        fields='ts_code,name'
                    )
                    if hk_df is not None and not hk_df.empty:
                        name_map.update(dict(zip(hk_df['ts_code'], hk_df['name'])))
                except Exception as e:
                    logger.warning(f"⚠️ 获取港股名称失败: {e}")

            # 获取美股名称
            us_codes = [c for c in normalized_codes if api.get_market(c) == "US"]
            if us_codes:
                try:
                    us_df = await cache.cached_call(
                        api.pro.us_basic,
                        cache_type="basic",
                        fields='ts_code,name,enname'
                    )
                    if us_df is not None and not us_df.empty:
                        name_map.update(dict(zip(us_df['ts_code'], us_df['name'])))
                except Exception as e:
                    logger.warning(f"⚠️ 获取美股名称失败: {e}")

            # 批量获取数据
            results = []
            pct_changes = []

            # 分批处理，每批 20 只
            batch_size = 20
            for i in range(0, len(normalized_codes), batch_size):
                batch_codes = normalized_codes[i:i + batch_size]

                # 并发获取（自动路由股票/指数 API）
                tasks = []
                for code in batch_codes:
                    tasks.append(
                        fetch_daily_data(
                            cache, api, code,
                            cache_type="daily",
                            start_date=start_date,
                            end_date=adjusted_end
                        )
                    )

                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for code, df in zip(batch_codes, batch_results):
                    if isinstance(df, Exception):
                        results.append({
                            "ts_code": code,
                            "name": name_map.get(code, code),
                            "error": str(df)
                        })
                        continue

                    if df is None or df.empty:
                        results.append({
                            "ts_code": code,
                            "name": name_map.get(code, code),
                            "error": "无数据"
                        })
                        continue

                    df = df.sort_values('trade_date')
                    start_price = float(df['pre_close'].iloc[0]) if 'pre_close' in df.columns and pd.notna(df['pre_close'].iloc[0]) else float(df['close'].iloc[0])
                    end_price = float(df['close'].iloc[-1])
                    pct_change = round((end_price / start_price - 1) * 100, 4)

                    pct_changes.append(pct_change)
                    results.append({
                        "ts_code": code,
                        "name": name_map.get(code, code),
                        "start_price": round(start_price, 2),
                        "end_price": round(end_price, 2),
                        "pct_chg": pct_change,
                        "data_points": len(df),
                        "actual_start": df['trade_date'].iloc[0],
                        "actual_end": df['trade_date'].iloc[-1]
                    })

                # 批次间延迟
                if i + batch_size < len(normalized_codes):
                    await asyncio.sleep(0.1)

            # 计算统计数据
            statistics = {}
            if pct_changes:
                pct_series = pd.Series(pct_changes)
                statistics = {
                    "mean": round(float(pct_series.mean()), 4),
                    "median": round(float(pct_series.median()), 4),
                    "std": round(float(pct_series.std()), 4),
                    "min": round(float(pct_series.min()), 4),
                    "max": round(float(pct_series.max()), 4),
                    "count": len(pct_changes)
                }

            data = {
                "start_date": start_date,
                "end_date": adjusted_end,
                "stock_count": len(stock_codes),
                "success_count": len(pct_changes),
                "results": results,
                "statistics": statistics
            }

            meta = build_meta(
                date_range=f"{start_date}-{adjusted_end}",
                date_adjusted=date_adjusted,
                date_adjust_message=end_msg if date_adjusted else None,
                coverage=len(pct_changes),
                expected_coverage=len(stock_codes)
            )

            # Build concise text summary for LLM
            mean_str = f"{'+' if statistics.get('mean', 0) >= 0 else ''}{statistics.get('mean', 'N/A')}%"
            median_str = f"{'+' if statistics.get('median', 0) >= 0 else ''}{statistics.get('median', 'N/A')}%"
            max_str = f"{'+' if statistics.get('max', 0) >= 0 else ''}{statistics.get('max', 'N/A')}%"
            summary = (
                f"{len(pct_changes)}只股票({start_date}-{adjusted_end})区间涨跌: "
                f"均值{mean_str}, 中位数{median_str}, 最大{max_str}"
            )

            structured = {
                "success": True,
                "data": data,
                "meta": meta,
                "timestamp": datetime.now().isoformat()
            }

            return finalize_artifact_result(
                rows=results or [],
                result=structured,
                tool_name="get_batch_pct_chg",
                query_params={"stock_codes": ",".join(stock_codes or []), "start_date": start_date, "end_date": adjusted_end},
                ui_uri="ui://findata/data-table",
                as_file=as_file,
                include_ui=include_ui,
                header_text=summary,
            )

        except Exception as e:
            logger.error(f"❌ get_batch_pct_chg error: {e}")
            return build_error_response(f"批量获取涨跌幅异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(
        tags={"市场统计"},
        app=MARKET_DASHBOARD_APP_ONLY,
    )
    async def refresh_market_data(
        market: str = "all",
        include_st: bool = False
    ) -> Dict[str, Any]:
        """刷新市场数据（仅 UI 调用，对 LLM 隐藏）

        Args:
            market: 市场筛选 ("all"/"CYB"/"KCB"/"SH"/"SZ"/"BJ")
            include_st: 是否包含ST股票
        """
        return await get_market_summary(market=market, include_st=include_st)

