"""市场流向工具

提供市场流向和板块分析相关的MCP工具，包括：
- get_sector_top_stocks: 获取行业龙头股
- get_top_list: 获取龙虎榜数据
"""

import logging
from typing import Annotated, Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
from pydantic import Field

from ..cache import cache
from ..utils.tushare_api import TushareAPI
from ..utils.ui_hint import attach_hint_to_dict, build_ui_hint as build_ui_hint_local
from ..utils.artifact_payload import finalize_artifact_result, AS_FILE_INCLUDE_UI_DECISION_GUIDE
from ..utils.response import build_error_response
from ..utils.errors import ErrorCode
from .routing import attach_next_steps
from .constants import INCLUDE_UI_DESCRIPTION

DATA_TABLE_APP = AppConfig(
    resource_uri="ui://findata/data-table",
    visibility=["model", "app"],
)

logger = logging.getLogger("findatamcp.market_flow")


def register_market_flow_tools(mcp: FastMCP, api: TushareAPI):
    """注册市场流向工具"""

    @mcp.tool(tags={"行业板块"}, app=AppConfig(resource_uri="ui://findata/data-table", visibility=["model", "app"]))
    async def get_sector_top_stocks(
        sector_name: str,
        limit: int = 10,
        sort_by: str = "market_cap",
        date: Optional[str] = None,
        as_file: bool = False,
        include_ui: Annotated[bool, Field(description=INCLUDE_UI_DESCRIPTION)] = False,
    ) -> Dict[str, Any]:
        """
        【行业龙头/行业当日排行】查询白酒/银行/半导体/有色金属等行业的个股排行，
        支持按市值（默认）、当日成交额、当日涨跌幅、换手率排序

        既回答"白酒龙头有哪些"（静态属性，sort_by="market_cap"），
        也回答"有色金属今天成交额前3是谁"（当日行情，sort_by="amount"）。
        每条结果都带当日行情快照字段（close/pct_chg/amount_billion），
        无需再逐只调用 get_latest_daily_close / get_historical_data。

        优先使用申万行业分类（更精准），fallback到通用行业分类。

        Args:
            sector_name: 行业名称，如 "白酒", "银行", "半导体", "有色金属"
            limit: 返回数量，默认 10（建议 5-20）
            sort_by: 排序字段：
                - "market_cap"（默认）总市值降序 —— 谁是龙头
                - "amount" 当日成交额降序 —— 今天谁交易最活跃
                - "pct_chg" 当日涨跌幅降序 —— 今天谁涨最多
                - "turnover_rate" 当日换手率降序
            date: 指定日期（YYYYMMDD），已废弃，自动使用最新数据

        Returns:
            个股排行列表（含 market_cap_billion / close / pct_chg /
            amount_billion / turnover_rate），codes 可直接传给
            analyze_stock_performance / get_batch_pct_chg

        Examples:
            >>> # 白酒市值前10龙头
            >>> result = await get_sector_top_stocks("白酒", limit=10)
            >>> # 有色金属今日成交额前3
            >>> result = await get_sector_top_stocks("有色金属", limit=3, sort_by="amount")
        """
        try:
            if not api.is_available():
                return build_error_response("Pro data access required", ErrorCode.PRO_REQUIRED)

            _SORT_COLUMNS = {
                "market_cap": "total_mv",
                "amount": "amount",
                "pct_chg": "pct_chg",
                "turnover_rate": "turnover_rate",
            }
            if sort_by not in _SORT_COLUMNS:
                return build_error_response(
                    error=f"sort_by 不支持 '{sort_by}'，可选: {', '.join(_SORT_COLUMNS)}",
                    error_code=ErrorCode.SCHEMA_ERROR,
                    data={"sort_by": sort_by},
                )

            # ===== 第1步：获取行业股票列表 =====
            target_codes = []
            sector_stocks = None
            data_source = None

            # 方案A: 优先尝试申万行业指数（最精准）
            try:
                df_sw_index = await cache.cached_call(
                    api.pro.index_basic,
                    cache_type="basic",
                    market='SW',
                    fields='ts_code,name'
                )

                if not df_sw_index.empty:
                    # 模糊匹配行业名称
                    matched = df_sw_index[df_sw_index['name'].str.contains(sector_name, case=False, na=False)]

                    if not matched.empty:
                        # 优先选择二级行业（包含"Ⅱ"），更精准
                        level2 = matched[matched['name'].str.contains('Ⅱ', na=False)]
                        index_code = level2['ts_code'].iloc[0] if not level2.empty else matched['ts_code'].iloc[0]
                        index_name = level2['name'].iloc[0] if not level2.empty else matched['name'].iloc[0]

                        # 获取成分股
                        df_members = await cache.cached_call(
                            api.pro.index_member,
                            cache_type="basic",
                            index_code=index_code
                        )

                        if not df_members.empty:
                            target_codes = df_members['con_code'].tolist()
                            data_source = f"申万指数-{index_name}"

                            # 获取股票名称等基本信息
                            df_basic = await cache.cached_call(
                                api.pro.stock_basic,
                                cache_type="basic",
                                exchange='',
                                list_status='L',
                                fields='ts_code,symbol,name,industry,market'
                            )
                            sector_stocks = df_basic[df_basic['ts_code'].isin(target_codes)]

            except Exception as e:
                pass  # fallback到通用分类

            # 方案B: Fallback到 stock_basic 的 industry 字段
            if not target_codes:
                df_basic = await cache.cached_call(
                    api.pro.stock_basic,
                    cache_type="basic",
                    exchange='',
                    list_status='L',
                    fields='ts_code,symbol,name,industry,market'
                )

                if df_basic.empty:
                    return build_error_response("无法获取股票基础数据", ErrorCode.NO_DATA)

                # 模糊匹配行业名称
                sector_mask = df_basic['industry'].str.contains(sector_name, case=False, na=False)
                sector_stocks = df_basic[sector_mask]

                if sector_stocks.empty:
                    # 在名称中搜索
                    name_mask = df_basic['name'].str.contains(sector_name, case=False, na=False)
                    sector_stocks = df_basic[name_mask]

                    if sector_stocks.empty:
                        return build_error_response(
                            error=f"未找到包含 '{sector_name}' 的板块。建议：\n"
                                  f"1. 尝试更通用名称（如'酒'而不是'高端白酒'）\n"
                                  f"2. 标准行业名称：白酒、银行、半导体、新能源",
                            error_code=ErrorCode.INVALID_SECTOR,
                            data={"sector_name": sector_name},
                        )

                target_codes = sector_stocks['ts_code'].tolist()
                data_source = "通用行业分类"

            # ===== 第2步：并发获取市值数据 =====
            # 限制数量避免过多API调用
            if len(target_codes) > 100:
                target_codes = target_codes[:100]

            # 分批并发（每批20只），避免触发频控
            import asyncio
            batch_size = 20
            all_mv_data = []
            failed_codes = []

            for i in range(0, len(target_codes), batch_size):
                batch_codes = target_codes[i:i+batch_size]

                # 并发查询这一批
                tasks = [
                    cache.cached_call(
                        api.pro.daily_basic,
                        cache_type="daily",
                        ts_code=code,
                        fields='ts_code,trade_date,total_mv,circ_mv,pe_ttm,pb,turnover_rate',
                        limit=1
                    )
                    for code in batch_codes
                ]

                # 等待这一批完成
                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for code, result in zip(batch_codes, results):
                        if isinstance(result, Exception):
                            failed_codes.append(code)
                        elif result is not None and not result.empty:
                            all_mv_data.append(result)
                        else:
                            failed_codes.append(code)

                except Exception as e:
                    failed_codes.extend(batch_codes)

                # 批次间延迟，避免频控
                if i + batch_size < len(target_codes):
                    await asyncio.sleep(0.1)

            if not all_mv_data:
                return build_error_response(
                    error=f"无法获取任何股票的市值数据（{len(failed_codes)}只失败）",
                    error_code=ErrorCode.NO_DATA,
                    data={"sector": sector_name},
                )

            # 合并数据
            import pandas as pd
            df_mv = pd.concat(all_mv_data, ignore_index=True)

            # ===== 第2.5步：当日行情快照（close/pct_chg/amount）=====
            # pro.daily(trade_date=...) 一次取全市场，零逐只调用 —— agent 复盘
            # (2026-06-12 conv 7ce1ff6f)反馈"逐只查成交额撞预算上限"的根治。
            snap_date = str(df_mv['trade_date'].max())
            df_daily = None
            try:
                df_daily = await cache.cached_call(
                    api.pro.daily,
                    cache_type="daily",
                    trade_date=snap_date,
                    fields='ts_code,close,pct_chg,amount'
                )
            except Exception as e:
                logger.warning(f"⚠️ 当日行情快照获取失败({snap_date}): {e}")
            if df_daily is not None and not df_daily.empty:
                df_mv = pd.merge(df_mv, df_daily, on='ts_code', how='left')
            else:
                if sort_by in ("amount", "pct_chg"):
                    return build_error_response(
                        error=f"无法获取 {snap_date} 当日行情，sort_by='{sort_by}' 不可用；"
                              f"可改用 sort_by='market_cap'",
                        error_code=ErrorCode.NO_DATA,
                        data={"sector": sector_name, "trade_date": snap_date},
                    )
                df_mv['close'] = None
                df_mv['pct_chg'] = None
                df_mv['amount'] = None

            # ===== 第3步：合并排序 =====
            merged = pd.merge(sector_stocks, df_mv, on='ts_code', how='inner')
            merged = merged[merged['total_mv'].notna()]
            # index_member 含历史进出记录，同一股票可能多行 —— 去重防榜单重复
            merged = merged.drop_duplicates(subset='ts_code', keep='first')
            sort_col = _SORT_COLUMNS[sort_by]
            if sort_col not in merged.columns:
                sort_col = 'total_mv'
            top_stocks = merged.sort_values(sort_col, ascending=False, na_position='last').head(limit)

            # ===== 第4步：格式化输出 =====
            result_list = []
            for _, row in top_stocks.iterrows():
                mv_yi = row['total_mv'] / 10000  # 万元 -> 亿元
                amount = row.get('amount')
                result_list.append({
                    "ts_code": row['ts_code'],
                    "name": row['name'],
                    "industry": row.get('industry', data_source),
                    "market": row['market'],
                    "market_cap_billion": round(mv_yi, 2),
                    "pe_ttm": round(row['pe_ttm'], 2) if pd.notna(row['pe_ttm']) else None,
                    "pb": round(row['pb'], 2) if pd.notna(row['pb']) else None,
                    # 当日行情快照（trade_date 见外层 snapshot_date）
                    "close": round(row['close'], 2) if pd.notna(row.get('close')) else None,
                    "pct_chg": round(row['pct_chg'], 2) if pd.notna(row.get('pct_chg')) else None,
                    # tushare daily.amount 单位千元 -> 亿元
                    "amount_billion": round(amount / 100000, 2) if pd.notna(amount) else None,
                    "turnover_rate": round(row['turnover_rate'], 2) if pd.notna(row.get('turnover_rate')) else None,
                })

            codes_only = [item['ts_code'] for item in result_list]

            _sector_result = {
                "success": True,
                "sector_name": sector_name,
                "data_source": data_source,
                "sort_by": sort_by,
                "snapshot_date": snap_date,
                "count": len(result_list),
                "data": result_list,
                "stocks": result_list,
                "codes": codes_only,
                "limit": limit,
                "timestamp": datetime.now().isoformat(),
                # P1-4: 添加 next_action 提示
                "next_actions": {
                    "analyze_performance": {
                        "tool": "analyze_stock_performance",
                        "params": {"stock_codes": codes_only[:5]},
                        "description": "对龙头股进行量化分析"
                    },
                    "calculate_sector_return": {
                        "tool": "get_batch_pct_chg",
                        "params": {"stock_codes": codes_only},
                        "description": "计算行业整体涨跌幅"
                    },
                    "compare_correlation": {
                        "tool": "analyze_price_correlation",
                        "params": {"stock_codes": codes_only[:5]},
                        "description": "分析龙头股相关性"
                    }
                }
            }
            if sort_by == "market_cap":
                _sector_result["next_tool_suggestion"] = (
                    "如需当日成交额/涨跌幅/换手率排名，重调本工具并传 "
                    "sort_by='amount'|'pct_chg'|'turnover_rate'，无需逐只查行情"
                )
            _sort_label = {"market_cap": "市值", "amount": "当日成交额",
                           "pct_chg": "当日涨跌幅", "turnover_rate": "当日换手率"}[sort_by]
            _header = f"{sector_name} 行业{_sort_label}排行 | {data_source} | 前 {len(result_list)} 只"
            _sector_result = attach_next_steps(_sector_result, "get_sector_top_stocks")
            return finalize_artifact_result(
                rows=result_list,
                result=_sector_result,
                tool_name="get_sector_top_stocks",
                query_params={"sector_name": sector_name, "limit": limit, "sort_by": sort_by, "date": date},
                ui_uri="ui://findata/data-table",
                as_file=as_file,
                include_ui=include_ui,
                header_text=_header,
            )

        except Exception as e:
            return build_error_response(
                error=f"获取行业龙头股异常: {str(e)}",
                error_code=ErrorCode.UPSTREAM_ERROR,
                data={"sector_name": sector_name},
            )

    @mcp.tool(tags={"行业板块"}, app=AppConfig(resource_uri="ui://findata/data-table", visibility=["model", "app"]))
    async def get_top_list(
        trade_date: str,
        market_type: str = "SH",
        as_file: bool = False,
        include_ui: Annotated[bool, Field(description=INCLUDE_UI_DESCRIPTION)] = False,
    ) -> Dict[str, Any]:
        """
        【龙虎榜】获取每日上榜股票、营业部买卖明细、净买入额，沪深京三市异动追踪

        Args:
            trade_date: 交易日期，格式 YYYYMMDD
            market_type: 市场类型，SH-上海，SZ-深圳，BJ-北京

        Returns:
            龙虎榜数据，包括：
            - ts_code: 股票代码
            - name: 股票名称
            - close: 收盘价
            - pct_chg: 涨跌幅
            - turnover_rate: 换手率
            - amount: 总成交额
            - l_sell: 龙虎榜卖出额
            - l_buy: 龙虎榜买入额
            - l_amount: 龙虎榜成交额
            - net_amount: 龙虎榜净买入
            - net_rate: 龙虎榜净买额占比
            - reason: 上榜原因

        Examples:
            >>> result = await get_top_list("20240115", "SH")
            >>> for item in result['data']:
            ...     print(f"{item['name']}: {item['reason']}, 净买入 {item['net_amount']} 万元")
        """
        try:
            if not api.is_available():
                return build_error_response("数据服务不可用（Pro 接口未配置）", ErrorCode.PRO_REQUIRED)

            df = api.pro.top_list(trade_date=trade_date)

            if df.empty:
                return build_error_response(
                    error="未找到龙虎榜数据",
                    error_code=ErrorCode.NO_DATA,
                    data={"trade_date": trade_date},
                )

            # 筛选市场
            if market_type:
                df = df[df['ts_code'].str.endswith(f'.{market_type}')]

            data = df.to_dict('records')

            _header = f"龙虎榜 {trade_date} | {market_type}市场 | {len(data)} 条"
            _top_result = {
                "success": True,
                "trade_date": trade_date,
                "market_type": market_type,
                "timestamp": datetime.now().isoformat(),
            }
            _top_result = attach_next_steps(_top_result, "get_top_list")
            return finalize_artifact_result(
                rows=data,
                result=_top_result,
                tool_name="get_top_list",
                query_params={"trade_date": trade_date, "market_type": market_type},
                ui_uri="ui://findata/data-table",
                header_text=_header,
                as_file=as_file,
                include_ui=include_ui,
            )
        except Exception as e:
            return build_error_response(
                error=f"获取龙虎榜数据异常: {str(e)}",
                error_code=ErrorCode.UPSTREAM_ERROR,
                data={"trade_date": trade_date},
            )
