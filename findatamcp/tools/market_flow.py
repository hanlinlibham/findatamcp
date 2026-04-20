"""市场流向工具

提供市场流向和板块分析相关的MCP工具，包括：
- get_sector_top_stocks: 获取行业龙头股
- get_top_list: 获取龙虎榜数据
"""

from typing import Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig

from ..cache import cache
from ..utils.tushare_api import TushareAPI
from ..utils.ui_hint import attach_hint_to_dict, build_ui_hint as build_ui_hint_local
from ..utils.artifact_payload import finalize_artifact_result, AS_FILE_INCLUDE_UI_DECISION_GUIDE

DATA_TABLE_APP = AppConfig(
    resource_uri="ui://findata/data-table",
    visibility=["model", "app"],
)


def register_market_flow_tools(mcp: FastMCP, api: TushareAPI):
    """注册市场流向工具"""

    @mcp.tool(tags={"行业板块"}, app=DATA_TABLE_APP)
    async def get_sector_top_stocks(
        sector_name: str,
        limit: int = 10,
        date: Optional[str] = None,
        as_file: bool = False,
        include_ui: bool = True,
    ) -> Dict[str, Any]:
        """
        获取某行业/板块的龙头股列表（按市值排序）

        解决"白酒行业"、"银行板块"等语义泛化问题。
        优先使用申万行业分类（更精准），fallback到通用行业分类。

        Args:
            sector_name: 行业名称，如 "白酒", "银行", "半导体", "新能源"
            limit: 返回数量，默认 10（建议 5-20）
            date: 指定日期（YYYYMMDD），已废弃，自动使用最新数据

        Returns:
            股票代码列表和名称，可直接传给 analyze_stock_performance 工具

        Examples:
            >>> # 获取白酒行业前10大龙头股
            >>> result = await get_sector_top_stocks("白酒", limit=10)
            >>> codes = result['codes']  # ['600519.SH', '000858.SZ', ...]
            >>>
            >>> # 然后将 codes 传给量化分析工具
            >>> perf = await analyze_stock_performance(codes, "20230101", "20231231", "comprehensive")
        """
        try:
            if not api.is_available():
                return {"success": False, "error": "Pro data access required"}

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
                    return {"success": False, "error": "无法获取股票基础数据"}

                # 模糊匹配行业名称
                sector_mask = df_basic['industry'].str.contains(sector_name, case=False, na=False)
                sector_stocks = df_basic[sector_mask]

                if sector_stocks.empty:
                    # 在名称中搜索
                    name_mask = df_basic['name'].str.contains(sector_name, case=False, na=False)
                    sector_stocks = df_basic[name_mask]

                    if sector_stocks.empty:
                        return {
                            "success": False,
                            "error": f"未找到包含 '{sector_name}' 的板块。建议：\n"
                                    f"1. 尝试更通用名称（如'酒'而不是'高端白酒'）\n"
                                    f"2. 标准行业名称：白酒、银行、半导体、新能源"
                        }

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
                        fields='ts_code,trade_date,total_mv,circ_mv,pe_ttm,pb',
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
                return {
                    "success": False,
                    "error": f"无法获取任何股票的市值数据（{len(failed_codes)}只失败）",
                    "sector": sector_name
                }

            # 合并数据
            import pandas as pd
            df_mv = pd.concat(all_mv_data, ignore_index=True)

            # ===== 第3步：合并排序 =====
            merged = pd.merge(sector_stocks, df_mv, on='ts_code', how='inner')
            merged = merged[merged['total_mv'].notna()]
            top_stocks = merged.sort_values('total_mv', ascending=False).head(limit)

            # ===== 第4步：格式化输出 =====
            result_list = []
            for _, row in top_stocks.iterrows():
                mv_yi = row['total_mv'] / 10000  # 万元 -> 亿元
                result_list.append({
                    "ts_code": row['ts_code'],
                    "name": row['name'],
                    "industry": row.get('industry', data_source),
                    "market": row['market'],
                    "market_cap_billion": round(mv_yi, 2),
                    "pe_ttm": round(row['pe_ttm'], 2) if pd.notna(row['pe_ttm']) else None,
                    "pb": round(row['pb'], 2) if pd.notna(row['pb']) else None
                })

            codes_only = [item['ts_code'] for item in result_list]

            _sector_result = {
                "success": True,
                "sector_name": sector_name,
                "data_source": data_source,
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
            _header = f"{sector_name} 行业龙头 | {data_source} | 前 {len(result_list)} 只"
            return finalize_artifact_result(
                rows=result_list,
                result=_sector_result,
                tool_name="get_sector_top_stocks",
                query_params={"sector_name": sector_name, "limit": limit, "date": date},
                ui_uri="ui://findata/data-table",
                as_file=as_file,
                include_ui=include_ui,
                header_text=_header,
            )

        except Exception as e:
            return {
                "success": False,
                "error": f"获取行业龙头股异常: {str(e)}",
                "sector_name": sector_name
            }

    @mcp.tool(tags={"行业板块"}, app=DATA_TABLE_APP)
    async def get_top_list(trade_date: str, market_type: str = "SH", as_file: bool = False, include_ui: bool = True) -> Dict[str, Any]:
        """
        获取龙虎榜数据

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
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            df = api.pro.top_list(trade_date=trade_date)

            if df.empty:
                return {"success": False, "error": "未找到龙虎榜数据", "trade_date": trade_date}

            # 筛选市场
            if market_type:
                df = df[df['ts_code'].str.endswith(f'.{market_type}')]

            data = df.to_dict('records')

            _header = f"龙虎榜 {trade_date} | {market_type}市场 | {len(data)} 条"
            return finalize_artifact_result(
                rows=data,
                result={
                    "success": True,
                    "trade_date": trade_date,
                    "market_type": market_type,
                    "timestamp": datetime.now().isoformat(),
                },
                tool_name="get_top_list",
                query_params={"trade_date": trade_date, "market_type": market_type},
                ui_uri="ui://findata/data-table",
                header_text=_header,
                as_file=as_file,
                include_ui=include_ui,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"获取龙虎榜数据异常: {str(e)}",
                "trade_date": trade_date
            }
