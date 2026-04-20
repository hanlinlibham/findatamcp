"""股票数据资源

提供计算副产品的按需访问：
- stock://calc_metrics/{calc_id}: 获取计算结果的完整数据
- stock://calc_metrics/{calc_id}?{stock_a}_{stock_b}: 获取指定股票对的数据和派生指标

架构设计：
1. analyze_price_correlation 计算相关性时，时间序列是副产品
2. 副产品存储到缓存，生成资源 URI（如 stock://calc_metrics/abc123）
3. 前端点击单元格时，通过资源 URI 查询已存储的数据
4. 支持派生计算：波动率、最大回撤、月度对比等
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from fastmcp import FastMCP
import pandas as pd

from ..utils.tushare_api import TushareAPI
from ..cache import cache
from ..cache.calc_cache import calc_metrics_cache


def register_stock_data_resources(mcp: FastMCP, api: TushareAPI):
    """注册股票数据资源"""

    @mcp.resource("stock://calc_metrics/{calc_id}/pair/{stock_a}/{stock_b}")
    async def get_calc_metrics_pair_resource(calc_id: str, stock_a: str, stock_b: str) -> str:
        """
        获取指定股票对的计算数据和派生指标（动态 Resource）

        URL 格式：stock://calc_metrics/{calc_id}/pair/{stock_a}/{stock_b}
        
        示例：stock://calc_metrics/abc123/pair/600519.SH/000858.SZ

        返回示例：
        {
            "uri": "stock://calc_metrics/abc123/pair/600519.SH/000858.SZ",
            "data": {
                "stock_a": "600519.SH",
                "stock_b": "000858.SZ",
                "correlation": 0.75,
                "time_series": {...},
                "derived_metrics": {
                    "volatility": {"stock_a": 25.5, "stock_b": 30.2, "unit": "%"},
                    "max_drawdown": {"stock_a": 15.3, "stock_b": 20.1, "unit": "%"},
                    "total_return": {...},
                    "monthly_comparison": [...],
                    "sharpe_ratio": {...}
                }
            }
        }
        """
        try:
            pair_data = calc_metrics_cache.get_pair_data(calc_id, stock_a, stock_b)
            if pair_data:
                return json.dumps({
                    "uri": f"stock://calc_metrics/{calc_id}/pair/{stock_a}/{stock_b}",
                    "mimeType": "application/json",
                    "description": f"股票对比数据：{stock_a} vs {stock_b}",
                    "data": pair_data,
                    "timestamp": datetime.now().isoformat()
                }, ensure_ascii=False, indent=2)
            else:
                # 尝试获取缓存数据以提供可用股票列表
                cached_data = calc_metrics_cache.get(calc_id)
                return json.dumps({
                    "uri": f"stock://calc_metrics/{calc_id}/pair/{stock_a}/{stock_b}",
                    "error": f"未找到股票对数据: {stock_a} vs {stock_b}",
                    "hint": "请确保股票代码格式正确（如 600519.SH）",
                    "available_stocks": cached_data.stock_codes if cached_data else []
                }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "uri": f"stock://calc_metrics/{calc_id}/pair/{stock_a}/{stock_b}",
                "error": f"获取股票对数据异常: {str(e)}"
            }, ensure_ascii=False)

    @mcp.resource("stock://calc_metrics/{calc_id}")
    async def get_calc_metrics_resource(calc_id: str) -> str:
        """
        获取计算副产品数据（动态 Resource）

        URL 格式：
        - stock://calc_metrics/{calc_id} - 获取完整计算数据
        - stock://calc_metrics/{calc_id}/pair/{stock_a}/{stock_b} - 获取指定股票对的数据（推荐）

        这是 analyze_price_correlation 工具的副产品查询接口。
        工具计算相关性时产生的时间序列数据被存储起来，
        通过此资源可以按需查询，并获取派生计算（波动率、回撤等）。
        """
        try:
            # 🔥 兼容旧格式：解析查询参数（股票对）
            stock_pair = None
            actual_calc_id = calc_id
            if '?' in calc_id:
                actual_calc_id, query = calc_id.split('?', 1)
                if '_' in query:
                    parts = query.split('_')
                    if len(parts) >= 2:
                        stock_pair = (parts[0], parts[1])
            
            # 使用解析后的 calc_id
            calc_id = actual_calc_id

            # 从缓存获取数据
            cached_data = calc_metrics_cache.get(calc_id)
            
            if not cached_data:
                return json.dumps({
                    "uri": f"stock://calc_metrics/{calc_id}",
                    "error": f"计算数据已过期或不存在: {calc_id}",
                    "hint": "请重新执行 analyze_price_correlation 工具"
                }, ensure_ascii=False)

            # 如果指定了股票对，返回该股票对的详细数据
            if stock_pair:
                pair_data = calc_metrics_cache.get_pair_data(calc_id, stock_pair[0], stock_pair[1])
                if pair_data:
                    return json.dumps({
                        "uri": f"stock://calc_metrics/{calc_id}?{stock_pair[0]}_{stock_pair[1]}",
                        "mimeType": "application/json",
                        "description": f"股票对比数据：{stock_pair[0]} vs {stock_pair[1]}",
                        "data": pair_data,
                        "timestamp": datetime.now().isoformat()
                    }, ensure_ascii=False, indent=2)
                else:
                    return json.dumps({
                        "uri": f"stock://calc_metrics/{calc_id}?{stock_pair[0]}_{stock_pair[1]}",
                        "error": f"未找到股票对数据: {stock_pair[0]} vs {stock_pair[1]}",
                        "available_stocks": cached_data.stock_codes
                    }, ensure_ascii=False)

            # 返回完整的计算数据
            return json.dumps({
                "uri": f"stock://calc_metrics/{calc_id}",
                "mimeType": "application/json",
                "description": f"相关性计算数据（{len(cached_data.stock_codes)} 只股票）",
                "data": {
                    "calc_id": cached_data.calc_id,
                    "stock_codes": cached_data.stock_codes,
                    "start_date": cached_data.start_date,
                    "end_date": cached_data.end_date,
                    "correlation_matrix": cached_data.correlation_matrix,
                    "time_series": cached_data.time_series,
                    "created_at": cached_data.created_at,
                    "expires_at": cached_data.expires_at
                },
                "timestamp": datetime.now().isoformat()
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            return json.dumps({
                "uri": f"stock://calc_metrics/{calc_id}",
                "error": f"获取计算数据异常: {str(e)}"
            }, ensure_ascii=False)

    @mcp.resource("stock://time_series/{stock_codes}")
    async def get_time_series_resource(stock_codes: str) -> str:
        """
        获取股票时间序列数据（动态 Resource）

        URL 格式：stock://time_series/{stock_codes}?start={start}&end={end}
        
        参数：
        - stock_codes: 逗号分隔的股票代码，如 "600519.SH,000858.SZ"
        - start: 开始日期 (YYYYMMDD)，可选，默认近1年
        - end: 结束日期 (YYYYMMDD)，可选，默认昨天

        返回：
        {
            "uri": "stock://time_series/600519.SH,000858.SZ",
            "data": {
                "600519.SH": [{"date": "20241201", "close": 1500.0}, ...],
                "000858.SZ": [{"date": "20241201", "close": 150.0}, ...]
            }
        }

        使用场景：
        - 用户点击相关性矩阵单元格后，前端调用此资源获取两只股票的时间序列数据
        - 用于绘制股价对比图
        """
        try:
            if not api.is_available():
                return json.dumps({"error": "Tushare Pro not available"})

            # 解析股票代码
            codes = [c.strip() for c in stock_codes.split(',') if c.strip()]
            if not codes:
                return json.dumps({"error": "No stock codes provided"})

            # 默认日期范围：最近1年
            end_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

            # 获取所有股票的历史数据
            time_series: Dict[str, List[Dict[str, Any]]] = {}
            
            for code in codes:
                ts_code = api.normalize_stock_code(code)
                try:
                    df = await cache.cached_call(
                        api.pro.daily,
                        cache_type="daily",
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date
                    )

                    if not df.empty:
                        df = df.sort_values('trade_date')
                        series_data = []
                        for _, row in df.iterrows():
                            series_data.append({
                                "date": row['trade_date'],
                                "close": round(float(row['close']), 2)
                            })
                        time_series[ts_code] = series_data
                    else:
                        time_series[ts_code] = []

                except Exception as e:
                    time_series[ts_code] = {"error": str(e)}

            return json.dumps({
                "uri": f"stock://time_series/{stock_codes}",
                "mimeType": "application/json",
                "description": f"股票时间序列数据：{stock_codes}",
                "data": time_series,
                "start_date": start_date,
                "end_date": end_date,
                "timestamp": datetime.now().isoformat()
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            return json.dumps({"error": f"获取时间序列数据异常: {str(e)}"})

    @mcp.resource("stock://correlation_data/{stock_a}/{stock_b}")
    async def get_correlation_data_resource(stock_a: str, stock_b: str) -> str:
        """
        获取两只股票的相关性对比数据（动态 Resource）

        URL 格式：stock://correlation_data/{stock_a}/{stock_b}

        参数：
        - stock_a: 股票A代码，如 "600519.SH"
        - stock_b: 股票B代码，如 "000858.SZ"

        返回：
        {
            "uri": "stock://correlation_data/600519.SH/000858.SZ",
            "data": {
                "correlation": 0.75,
                "time_series": {
                    "600519.SH": [...],
                    "000858.SZ": [...]
                }
            }
        }

        使用场景：
        - 用户点击相关性矩阵单元格后，前端调用此资源
        - 一次性获取相关性值和时间序列数据
        """
        try:
            if not api.is_available():
                return json.dumps({"error": "Tushare Pro not available"})

            # 标准化股票代码
            ts_code_a = api.normalize_stock_code(stock_a)
            ts_code_b = api.normalize_stock_code(stock_b)

            # 默认日期范围
            end_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

            # 获取两只股票的数据
            time_series: Dict[str, List[Dict[str, Any]]] = {}
            dfs = {}
            
            for ts_code in [ts_code_a, ts_code_b]:
                try:
                    df = await cache.cached_call(
                        api.pro.daily,
                        cache_type="daily",
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date
                    )

                    if not df.empty:
                        df = df.sort_values('trade_date')
                        dfs[ts_code] = df
                        
                        series_data = []
                        for _, row in df.iterrows():
                            series_data.append({
                                "date": row['trade_date'],
                                "close": round(float(row['close']), 2)
                            })
                        time_series[ts_code] = series_data

                except Exception as e:
                    return json.dumps({"error": f"获取股票 {ts_code} 数据失败: {str(e)}"})

            # 计算相关性
            correlation = None
            if ts_code_a in dfs and ts_code_b in dfs:
                df_a = dfs[ts_code_a].set_index('trade_date')['close']
                df_b = dfs[ts_code_b].set_index('trade_date')['close']
                
                # 对齐数据
                aligned = pd.concat([df_a, df_b], axis=1, join='inner')
                aligned.columns = ['A', 'B']
                
                if len(aligned) > 2:
                    # 计算收益率相关性
                    returns = aligned.pct_change().dropna()
                    correlation = float(returns['A'].corr(returns['B']))

            return json.dumps({
                "uri": f"stock://correlation_data/{stock_a}/{stock_b}",
                "mimeType": "application/json",
                "description": f"股票对比数据：{stock_a} vs {stock_b}",
                "data": {
                    "stock_a": ts_code_a,
                    "stock_b": ts_code_b,
                    "correlation": correlation,
                    "time_series": time_series,
                    "data_points": len(time_series.get(ts_code_a, [])),
                },
                "start_date": start_date,
                "end_date": end_date,
                "timestamp": datetime.now().isoformat()
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            return json.dumps({"error": f"获取相关性数据异常: {str(e)}"})

