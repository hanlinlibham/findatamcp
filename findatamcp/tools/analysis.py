"""高级分析工具

提供企业级的量化分析工具，包括：
- get_financial_metrics: 财务指标聚合分析（支持CAGR/YoY/QoQ/TTM）
- analyze_price_correlation: 量化分析引擎（相关性/Beta/波动率/回撤）
- analyze_stock_performance: 深度量化分析（Sharpe/Sortino/RSI/MACD）
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
import pandas as pd
import numpy as np
import logging

from ..cache import cache
from ..cache.calc_cache import calc_metrics_cache
from ..utils.tushare_api import TushareAPI, fetch_daily_data
from ..utils.large_data_handler import sample_rows
from ..utils.ui_hint import attach_hint_to_dict
from ..utils.artifact_payload import finalize_artifact_result, AS_FILE_INCLUDE_UI_DECISION_GUIDE
# P0-2: 使用共享的日期容错工具
from ..utils.data_processing import adjust_end_date_to_latest_trading_day as _adjust_end_date_to_latest_trading_day

logger = logging.getLogger(__name__)
from ..utils.technical_indicators import (
    calculate_sharpe_ratio, calculate_max_drawdown, calculate_var,
    calculate_beta, calculate_pe_percentile, calculate_pb_percentile,
    calculate_dividend_yield, calculate_rsi, calculate_macd, calculate_bollinger_bands,
    calculate_kdj, calculate_williams, calculate_cci, calculate_roc, calculate_trix,
    calculate_obv, calculate_volume_ratio, calculate_atr, calculate_relative_strength,
    calculate_moving_averages
)

CORRELATION_MATRIX_APP = AppConfig(
    resource_uri="ui://findata/correlation-matrix",
    visibility=["model", "app"],
)
FINANCIAL_METRICS_CHART_APP = AppConfig(
    resource_uri="ui://findata/financial-metrics-chart",
    visibility=["model", "app"],
)

_METRIC_LABELS = {
    "pe": "PE",
    "pb": "PB",
    "ps": "PS",
    "dividend_yield": "股息率",
    "roe": "ROE",
    "roa": "ROA",
    "grossprofit_margin": "毛利率",
    "netprofit_margin": "净利率",
    "debt_to_assets": "资产负债率",
    "revenue": "营业收入",
    "profit": "净利润",
}

_PERCENT_METRICS = {
    "dividend_yield",
    "roe",
    "roa",
    "grossprofit_margin",
    "netprofit_margin",
    "debt_to_assets",
}


def _calculate_metric_stats(values: pd.Series, calc_type: str) -> Dict[str, Any]:
    """计算指标统计信息"""
    try:
        result = {}

        if calc_type == "raw":
            # 原始值
            result["values"] = values.tolist()
            result["latest"] = values.iloc[-1] if not values.empty else None
            result["mean"] = values.mean()
            result["std"] = values.std()
            result["min"] = values.min()
            result["max"] = values.max()

        elif calc_type == "yoy":
            # 同比增长率
            if len(values) >= 5:  # 至少需要5个季度的数据
                yoy_growth = []
                for i in range(4, len(values)):
                    if values.iloc[i-4] != 0:
                        growth = (values.iloc[i] - values.iloc[i-4]) / abs(values.iloc[i-4]) * 100
                        yoy_growth.append(growth)
                if yoy_growth:
                    result["yoy_growth_rates"] = yoy_growth
                    result["avg_yoy_growth"] = np.mean(yoy_growth)
                    result["latest_yoy_growth"] = yoy_growth[-1]

        elif calc_type == "cagr":
            # 复合年增长率
            if len(values) >= 8:  # 至少需要2年的数据（8个季度）
                periods = len(values) - 1
                if periods > 0 and values.iloc[0] != 0:
                    cagr = (values.iloc[-1] / values.iloc[0]) ** (1 / (periods / 4)) - 1
                    result["cagr"] = cagr * 100  # 转换为百分比

        elif calc_type == "ttm":
            # 滚动12月（最近4个季度总和）
            if len(values) >= 4:
                ttm_values = []
                for i in range(3, len(values)):
                    ttm = values.iloc[i-3:i+1].sum()
                    ttm_values.append(ttm)
                if ttm_values:
                    result["ttm_values"] = ttm_values
                    result["latest_ttm"] = ttm_values[-1]

        return result

    except Exception as e:
        return {"error": f"计算统计信息失败: {str(e)}"}


def _align_stock_data(stock_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """对齐多只股票的数据，确保在相同交易日都有数据"""
    try:
        # 合并所有数据，使用trade_date作为索引
        aligned_dfs = []
        for ts_code, df in stock_data.items():
            df_copy = df.copy()
            df_copy['trade_date'] = pd.to_datetime(df_copy['trade_date'])
            df_copy.set_index('trade_date', inplace=True)
            # 保留 close 和 pre_close（用于正确计算区间涨跌幅）
            keep_cols = ['close']
            if 'pre_close' in df_copy.columns:
                keep_cols.append('pre_close')
            df_copy = df_copy[keep_cols]
            rename_map = {'close': f"{ts_code}_close"}
            if 'pre_close' in df_copy.columns:
                rename_map['pre_close'] = f"{ts_code}_pre_close"
            df_copy = df_copy.rename(columns=rename_map)
            # 计算收益率
            df_copy[f"{ts_code}_returns"] = df_copy[f"{ts_code}_close"].pct_change()
            aligned_dfs.append(df_copy)

        # 合并所有数据框
        if aligned_dfs:
            result = pd.concat(aligned_dfs, axis=1, join='inner')  # 只保留所有股票都有数据的日期
            return result
        else:
            return pd.DataFrame()

    except Exception as e:
        return pd.DataFrame()


def _metric_panel_from_stats(metric: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """将财务指标统计结果转换为图表 panel。"""
    labels = payload.get("source_dates") or []
    values = None
    chart_type = "line"

    if payload.get("values"):
        values = payload["values"]
    elif payload.get("yoy_growth_rates"):
        values = payload["yoy_growth_rates"]
        labels = labels[4:] if len(labels) >= len(values) + 4 else labels[-len(values):]
    elif payload.get("ttm_values"):
        values = payload["ttm_values"]
        labels = labels[3:] if len(labels) >= len(values) + 3 else labels[-len(values):]
    elif payload.get("cagr") is not None:
        values = [payload["cagr"]]
        labels = [labels[-1] if labels else "CAGR"]
        chart_type = "bar"

    if not values:
        return None

    if not labels or len(labels) != len(values):
        labels = [f"P{i + 1}" for i in range(len(values))]

    y_axis = {"name": "%", "format": "percent"} if metric in _PERCENT_METRICS else {"name": "数值"}
    series_name = _METRIC_LABELS.get(metric, metric)
    return {
        "title": series_name,
        "categories": [str(item) for item in labels],
        "series": [{"name": series_name, "data": values, "type": chart_type}],
        "yAxis": y_axis,
        "note": f"分位数 {payload['percentile']}%" if payload.get("percentile") is not None else None,
    }


def _build_financial_metrics_ui(ts_code: str, period: str, calc_type: str, metrics_payload: Dict[str, Any]) -> Dict[str, Any]:
    """构建财务指标图表 view model。"""
    cards = []
    panels = []

    for metric, payload in metrics_payload.items():
        if not isinstance(payload, dict):
            continue
        panel = _metric_panel_from_stats(metric, payload)
        if panel:
            panels.append(panel)

        latest_value = payload.get("current")
        if latest_value is None:
            latest_value = payload.get("latest")
        if latest_value is None and payload.get("cagr") is not None:
            latest_value = payload.get("cagr")

        if latest_value is not None:
            suffix = "%" if metric in _PERCENT_METRICS or payload.get("cagr") is not None else ""
            note = None
            if payload.get("percentile") is not None:
                note = f"历史分位 {payload['percentile']}%"
            cards.append({
                "label": _METRIC_LABELS.get(metric, metric),
                "value": f"{round(float(latest_value), 2)}{suffix}" if isinstance(latest_value, (int, float, np.floating)) else f"{latest_value}{suffix}",
                "note": note,
            })

    return {
        "kind": "financial-metrics-chart",
        "title": f"{ts_code} 财务指标趋势",
        "subtitle": f"{period} · {calc_type}",
        "cards": cards,
        "panels": panels,
    }


def _build_correlation_ui(title: str, subtitle: str, correlation_matrix: Dict[str, Dict[str, Any]], time_series: Dict[str, List[Dict[str, Any]]], stock_names: Dict[str, str]) -> Dict[str, Any]:
    """构建相关性矩阵图表 view model。"""
    labels = list(correlation_matrix.keys())
    sorted_series = {
        code: sorted(series, key=lambda item: str(item.get("date") or ""))
        for code, series in time_series.items()
    }

    best_pair = None
    worst_pair = None
    for i, left in enumerate(labels):
        for right in labels[i + 1:]:
            value = correlation_matrix.get(left, {}).get(right)
            if value is None:
                continue
            pair = {
                "left": stock_names.get(left, left),
                "right": stock_names.get(right, right),
                "value": round(float(value), 3),
            }
            if best_pair is None or value > best_pair["value"]:
                best_pair = pair
            if worst_pair is None or value < worst_pair["value"]:
                worst_pair = pair

    stats = []
    if best_pair:
        stats.append({
            "label": "最强正相关",
            "value": f"{best_pair['left']} / {best_pair['right']}",
            "note": f"{best_pair['value']}",
        })
    if worst_pair:
        stats.append({
            "label": "最弱相关",
            "value": f"{worst_pair['left']} / {worst_pair['right']}",
            "note": f"{worst_pair['value']}",
        })

    return {
        "kind": "correlation-matrix",
        "title": title,
        "subtitle": subtitle,
        "labels": labels,
        "stockNames": stock_names,
        "correlationMatrix": correlation_matrix,
        "timeSeries": sorted_series,
        "stats": stats,
    }


def register_analysis_tools(mcp: FastMCP, api: TushareAPI):
    """注册高级分析工具"""

    @mcp.tool(tags={"量化分析"}, app=FINANCIAL_METRICS_CHART_APP)
    async def get_financial_metrics(
        ts_code: str = "",
        stock_code: str = "",
        code: str = "",
        metrics: List[str] = ["pe", "roe", "revenue_yoy"],
        period: str = "3y",
        calc_type: str = "raw",
        as_file: bool = False,
        include_ui: bool = True,
    ) -> Dict[str, Any]:
        """
        获取财务指标与增长分析（聚合工具）

        返回原始财务数据，并可计算增长率、复合增速等衍生指标。

        Args:
            ts_code: 股票代码，例如 '600519.SH', '000001.SZ'。也可用 stock_code 或 code 参数名
                    也支持 '600519', '000001'（自动补全后缀）
            metrics: 指标列表，可选值：
                估值类（来自 daily_basic，TTM 口径）:
                  - pe: 市盈率 PE_TTM（总市值/最近4季归母净利润）
                  - pb: 市净率（总市值/最新归母净资产）
                  - ps: 市销率 PS_TTM（总市值/最近4季营收）
                  - dividend_yield: 股息率 TTM（近12月分红/当前股价）
                财务类（来自 fina_indicator / income）:
                  - roe: 净资产收益率
                  - roa: 总资产收益率
                  - grossprofit_margin: 毛利率
                  - netprofit_margin: 净利率
                  - debt_to_assets: 资产负债率
                  - revenue: 营业收入
                  - profit: 净利润
            period: 时间周期，1y/2y/3y/5y/all
            calc_type: 计算类型，raw=原始值序列，yoy=同比增长率，cagr=复合年增长率，ttm=滚动12月

        Returns:
            metrics: 各指标的统计结果，估值类附带 current（最新值）、field（实际字段名）、percentile（PE/PB 3年历史分位数）

        Examples:
            >>> await get_financial_metrics("600519.SH", ["pe", "pb", "ps", "dividend_yield"], "3y")
            >>> await get_financial_metrics("600036.SH", ["revenue", "profit", "roe"], "3y", "cagr")
        """
        try:
            # 兼容旧参数名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 财务指标仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {"success": False, "error": f"财务指标仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"}

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            # 计算时间范围
            period_limits = {
                "1y": 4,   # 最近4个季度
                "2y": 8,   # 最近8个季度
                "3y": 12,  # 最近12个季度
                "5y": 20,  # 最近20个季度
                "all": 50  # 全部可用数据
            }

            limit = period_limits.get(period, 12)

            result = {
                "ts_code": ts_code,
                "period": period,
                "calc_type": calc_type,
                "metrics": {},
                "timestamp": datetime.now().isoformat()
            }

            # 获取财务指标数据
            if "pe" in metrics or "pb" in metrics or "ps" in metrics or "dividend_yield" in metrics:
                try:
                    # 获取每日指标数据用于PE/PB等估值指标
                    daily_basic_df = await cache.cached_call(
                        api.pro.daily_basic,
                        cache_type="financial",
                        ts_code=ts_code,
                        limit=limit
                    )

                    if not daily_basic_df.empty:
                        daily_basic_df = daily_basic_df.sort_values('trade_date')

                        if "pe" in metrics:
                            pe_values = daily_basic_df['pe_ttm'].dropna()
                            if len(pe_values) > 0:
                                result["metrics"]["pe"] = _calculate_metric_stats(pe_values, calc_type)
                                result["metrics"]["pe"]["current"] = pe_values.iloc[-1]
                                result["metrics"]["pe"]["field"] = "pe_ttm"
                                result["metrics"]["pe"]["percentile"] = calculate_pe_percentile(ts_code, api)
                                result["metrics"]["pe"]["source_dates"] = daily_basic_df.loc[pe_values.index, "trade_date"].astype(str).tolist()

                        if "pb" in metrics:
                            pb_values = daily_basic_df['pb'].dropna()
                            if len(pb_values) > 0:
                                result["metrics"]["pb"] = _calculate_metric_stats(pb_values, calc_type)
                                result["metrics"]["pb"]["current"] = pb_values.iloc[-1]
                                result["metrics"]["pb"]["percentile"] = calculate_pb_percentile(ts_code, api)
                                result["metrics"]["pb"]["source_dates"] = daily_basic_df.loc[pb_values.index, "trade_date"].astype(str).tolist()

                        if "ps" in metrics:
                            ps_values = daily_basic_df['ps_ttm'].dropna()
                            if len(ps_values) > 0:
                                result["metrics"]["ps"] = _calculate_metric_stats(ps_values, calc_type)
                                result["metrics"]["ps"]["current"] = ps_values.iloc[-1]
                                result["metrics"]["ps"]["field"] = "ps_ttm"
                                result["metrics"]["ps"]["source_dates"] = daily_basic_df.loc[ps_values.index, "trade_date"].astype(str).tolist()

                        if "dividend_yield" in metrics:
                            dv_values = daily_basic_df['dv_ttm'].dropna()
                            if len(dv_values) > 0:
                                result["metrics"]["dividend_yield"] = _calculate_metric_stats(dv_values, calc_type)
                                result["metrics"]["dividend_yield"]["current"] = dv_values.iloc[-1]
                                result["metrics"]["dividend_yield"]["field"] = "dv_ttm"
                                result["metrics"]["dividend_yield"]["source_dates"] = daily_basic_df.loc[dv_values.index, "trade_date"].astype(str).tolist()

                except Exception as e:
                    result["metrics"]["valuation_error"] = f"获取估值数据失败: {str(e)}"

            # 获取财务数据
            try:
                fina_indicator_df = await cache.cached_call(
                    api.pro.fina_indicator,
                    cache_type="financial",
                    ts_code=ts_code,
                    limit=limit
                )

                if not fina_indicator_df.empty:
                    if 'end_date' in fina_indicator_df.columns:
                        fina_indicator_df = fina_indicator_df.sort_values('end_date')

                    # 处理财务指标
                    for metric in metrics:
                        if metric in ['roe', 'roa', 'grossprofit_margin', 'netprofit_margin', 'debt_to_assets']:
                            col_mapping = {
                                'roe': 'roe',
                                'roa': 'roa',
                                'grossprofit_margin': 'grossprofit_margin',
                                'netprofit_margin': 'netprofit_margin',
                                'debt_to_assets': 'debt_to_assets'
                            }

                            if metric in col_mapping and col_mapping[metric] in fina_indicator_df.columns:
                                values = fina_indicator_df[col_mapping[metric]].dropna()
                                if len(values) > 0:
                                    result["metrics"][metric] = _calculate_metric_stats(values, calc_type)
                                    result["metrics"][metric]["current"] = values.iloc[-1]
                                    result["metrics"][metric]["source_dates"] = fina_indicator_df.loc[values.index, "end_date"].astype(str).tolist()

            except Exception as e:
                result["metrics"]["financial_error"] = f"获取财务数据失败: {str(e)}"

            # 获取利润表数据
            try:
                income_df = await cache.cached_call(
                    api.pro.income,
                    cache_type="financial",
                    ts_code=ts_code,
                    limit=limit
                )

                if not income_df.empty:
                    if 'end_date' in income_df.columns:
                        income_df = income_df.sort_values('end_date')

                    revenue_col = 'total_revenue' if 'total_revenue' in income_df.columns else 'revenue'
                    profit_col = 'n_income' if 'n_income' in income_df.columns else 'net_profit'

                    if "revenue" in metrics and revenue_col in income_df.columns:
                        revenue_values = income_df[revenue_col].dropna()
                        if len(revenue_values) > 0:
                            result["metrics"]["revenue"] = _calculate_metric_stats(revenue_values, calc_type)
                            result["metrics"]["revenue"]["current"] = revenue_values.iloc[-1]
                            result["metrics"]["revenue"]["source_dates"] = income_df.loc[revenue_values.index, "end_date"].astype(str).tolist()

                    if "profit" in metrics and profit_col in income_df.columns:
                        profit_values = income_df[profit_col].dropna()
                        if len(profit_values) > 0:
                            result["metrics"]["profit"] = _calculate_metric_stats(profit_values, calc_type)
                            result["metrics"]["profit"]["current"] = profit_values.iloc[-1]
                            result["metrics"]["profit"]["source_dates"] = income_df.loc[profit_values.index, "end_date"].astype(str).tolist()

            except Exception as e:
                result["metrics"]["income_error"] = f"获取利润表数据失败: {str(e)}"

            if result["metrics"]:
                result["success"] = True
                result["ui"] = _build_financial_metrics_ui(ts_code, period, calc_type, result["metrics"])
                _fm_rows = [
                    {"metric": k, **(v if isinstance(v, dict) else {"value": v})}
                    for k, v in result["metrics"].items()
                ]
                _header = f"{ts_code} 财务指标 | period={period} calc={calc_type} | {len(_fm_rows)} 个指标"
                return finalize_artifact_result(
                    rows=_fm_rows,
                    result=result,
                    tool_name="get_financial_metrics",
                    query_params={"ts_code": ts_code, "period": period, "calc_type": calc_type, "metrics": ",".join(metrics or [])},
                    ui_uri="ui://findata/financial-metrics-chart",
                    as_file=as_file,
                    include_ui=include_ui,
                    header_text=_header,
                )
            else:
                return {
                    "success": False,
                    "error": "未找到任何财务指标数据",
                    "ts_code": ts_code
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"获取财务指标异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"量化分析"}, app=CORRELATION_MATRIX_APP)
    async def analyze_price_correlation(
        stock_codes: List[str],
        start_date: str = None,
        end_date: str = None,
        analysis_type: str = "correlation",
        as_file: bool = False,
        include_ui: bool = True,
    ) -> Dict[str, Any]:
        """
        量化分析工具（相关性、贝塔、业绩对比）

        专门处理多只股票的时间序列计算，自动处理数据对齐和缺失值。

        Args:
            stock_codes: 股票代码列表，至少2个，例如 ["600519.SH", "000858.SZ"]
            start_date: 开始日期，格式 YYYYMMDD，可选，默认为最近1年
            end_date: 结束日期，格式 YYYYMMDD，可选，默认为昨天
            analysis_type: 分析类型，correlation=相关性，beta=贝塔系数，comparison=业绩对比

        Returns:
            量化分析结果

        Examples:
            >>> result = await analyze_price_correlation(["000001", "600036"], "20230101", "20231231")
            >>> print(f"相关系数: {result['correlation_matrix']['000001.SZ']['600036.SH']}")
        """
        # 设置默认日期
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')  # 🔥 先设为今天，后续会自动调整

        # 参数验证
        if not isinstance(stock_codes, list):
            return {
                "success": False,
                "error": f"参数 stock_codes 必须是列表类型，当前收到: {type(stock_codes)} = {stock_codes[:100] if isinstance(stock_codes, str) else stock_codes}",
                "hint": "请从 get_sector_top_stocks 工具的返回结果中提取 'codes' 字段，例如: result['codes']"
            }

        if len(stock_codes) < 2:
            return {"success": False, "error": "至少需要2个股票代码进行相关性分析"}
        """
        量化分析工具（相关性、贝塔、业绩对比）

        专门处理多只股票的时间序列计算，自动处理数据对齐和缺失值。

        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
            analysis_type: 分析类型，correlation=相关性，beta=贝塔系数，comparison=业绩对比

        Returns:
            量化分析结果

        Examples:
            >>> result = await analyze_price_correlation(["000001", "600036"], "20230101", "20231231")
            >>> print(f"相关系数: {result['correlation_matrix']['000001.SZ']['600036.SH']}")
        """
        date_adjust_msg = ""  # 🔥 日期调整说明
        try:
            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            # 🔥 日期容错：自动调整结束日期到最近交易日
            end_date, date_adjust_msg = await _adjust_end_date_to_latest_trading_day(cache, api, end_date)
            logger.info(f"📅 [analyze_price_correlation] Using date range: {start_date} - {end_date}")

            if len(stock_codes) < 2:
                return {"success": False, "error": "至少需要2只股票进行相关性分析"}

            # 获取所有股票/指数的历史数据
            stock_data = {}
            for stock_code in stock_codes:
                ts_code = api.normalize_stock_code(stock_code)
                try:
                    df = await fetch_daily_data(
                        cache, api, ts_code,
                        cache_type="daily",
                        start_date=start_date,
                        end_date=end_date
                    )

                    if df is not None and not df.empty:
                        df = df.sort_values('trade_date')
                        # 计算收益率
                        df['returns'] = df['close'].pct_change()
                        stock_data[ts_code] = df
                    else:
                        return {"success": False, "error": f"未找到股票 {stock_code} 的历史数据"}

                except Exception as e:
                    return {"success": False, "error": f"获取股票 {stock_code} 数据失败: {str(e)}"}

            # 对齐数据（确保所有股票在相同交易日有数据）
            aligned_data = _align_stock_data(stock_data)

            if aligned_data.empty:
                return {"success": False, "error": "数据对齐失败，没有足够的重叠交易日"}

            result = {
                "success": True,
                "stock_codes": stock_codes,
                "start_date": start_date,
                "end_date": end_date,
                "analysis_type": analysis_type,
                "data_points": len(aligned_data),
                "timestamp": datetime.now().isoformat()
            }
            
            # 🔥 添加日期调整说明（如果有的话）
            if date_adjust_msg:
                result["date_adjusted"] = True
                result["date_adjust_message"] = date_adjust_msg

            if analysis_type == "correlation":
                # 计算相关性矩阵
                returns_data = aligned_data.filter(regex='_returns$')
                correlation_matrix = returns_data.corr()

                # 转换为字典格式
                result["correlation_matrix"] = {}
                for stock1 in stock_codes:
                    ts_code1 = api.normalize_stock_code(stock1)
                    col1 = f"{ts_code1}_returns"
                    if col1 in correlation_matrix.columns:
                        result["correlation_matrix"][ts_code1] = {}
                        for stock2 in stock_codes:
                            ts_code2 = api.normalize_stock_code(stock2)
                            col2 = f"{ts_code2}_returns"
                            if col2 in correlation_matrix.columns:
                                corr_value = correlation_matrix.loc[col1, col2]
                                result["correlation_matrix"][ts_code1][ts_code2] = float(corr_value) if not np.isnan(corr_value) else None
                
                # 🔥 构建时间序列数据（计算的副产品）
                # 格式: { "600519.SH": [{"date": "20241201", "close": 1500.0}, ...], ... }
                time_series = {}
                ts_codes_list = []
                for stock_code in stock_codes:
                    ts_code = api.normalize_stock_code(stock_code)
                    ts_codes_list.append(ts_code)
                    close_col = f"{ts_code}_close"
                    if close_col in aligned_data.columns:
                        series_data = []
                        for date_idx, row in aligned_data.iterrows():
                            price = row[close_col]
                            if pd.notna(price):
                                # date_idx 是 datetime 对象，转换为 YYYYMMDD 格式字符串
                                date_str = date_idx.strftime('%Y%m%d') if hasattr(date_idx, 'strftime') else str(date_idx)
                                series_data.append({
                                    "date": date_str,
                                    "close": round(float(price), 2)
                                })
                        time_series[ts_code] = series_data
                
                # 🔥 将副产品存储到缓存，生成资源引用
                calc_id = calc_metrics_cache.store(
                    stock_codes=ts_codes_list,
                    start_date=start_date,
                    end_date=end_date,
                    time_series=time_series,
                    correlation_matrix=result["correlation_matrix"]
                )
                
                # 资源 URI：stock://calc_metrics/{calc_id}
                # 查询特定股票对：stock://calc_metrics/{calc_id}?{stock_a}_{stock_b}
                sampled_time_series = {
                    code: sample_rows(series, max_points=120)
                    for code, series in time_series.items()
                }
                result["calc_id"] = calc_id
                result["resource_uri"] = f"stock://calc_metrics/{calc_id}"
                result["time_series"] = sampled_time_series

            elif analysis_type == "beta":
                # 计算贝塔系数（相对于第一只股票）
                if len(stock_codes) >= 2:
                    base_stock = api.normalize_stock_code(stock_codes[0])
                    base_returns = aligned_data[f"{base_stock}_returns"]

                    result["beta_analysis"] = {}
                    for stock_code in stock_codes[1:]:
                        ts_code = api.normalize_stock_code(stock_code)
                        stock_returns = aligned_data[f"{ts_code}_returns"]

                        # 计算贝塔系数
                        covariance = np.cov(stock_returns.dropna(), base_returns.dropna())[0][1]
                        base_variance = np.var(base_returns.dropna())

                        beta = covariance / base_variance if base_variance > 0 else None
                        result["beta_analysis"][ts_code] = {
                            "beta_vs_" + base_stock: float(beta) if beta is not None else None,
                            "correlation": float(stock_returns.corr(base_returns))
                        }

            elif analysis_type == "comparison":
                # 业绩对比
                result["performance_comparison"] = {}

                for stock_code in stock_codes:
                    ts_code = api.normalize_stock_code(stock_code)
                    stock_prices = aligned_data[f"{ts_code}_close"]
                    stock_returns = aligned_data[f"{ts_code}_returns"]

                    if not stock_prices.empty:
                        # 计算业绩指标（优先用 pre_close 作为基准，覆盖假期跳空）
                        pre_close_col = f"{ts_code}_pre_close"
                        if pre_close_col in aligned_data.columns and pd.notna(aligned_data[pre_close_col].iloc[0]):
                            _base = aligned_data[pre_close_col].iloc[0]
                        else:
                            _base = stock_prices.iloc[0]
                        total_return = (stock_prices.iloc[-1] / _base - 1) * 100
                        volatility = stock_returns.std() * np.sqrt(252) * 100  # 年化波动率
                        sharpe = calculate_sharpe_ratio(stock_returns.values) if len(stock_returns.dropna()) > 0 else None
                        max_drawdown = calculate_max_drawdown(stock_prices.values)

                        result["performance_comparison"][ts_code] = {
                            "total_return_pct": float(total_return),
                            "annual_volatility_pct": float(volatility),
                            "sharpe_ratio": float(sharpe) if sharpe is not None else None,
                            "max_drawdown_pct": float(max_drawdown) if max_drawdown is not None else None,
                            "avg_daily_return_pct": float(stock_returns.mean() * 100),
                            "positive_days_ratio": float((stock_returns > 0).sum() / len(stock_returns.dropna()))
                        }

            # 🔥 新增：获取股票/指数名称映射，避免LLM自行推断名称时出错
            stock_names = {}
            try:
                normalized = [api.normalize_stock_code(c) for c in stock_codes]
                a_stock_codes_only = [c for c in normalized if api.get_market(c) == "A" and not api.is_index_code(c)]
                index_codes_only = [c for c in normalized if api.get_market(c) == "A" and api.is_index_code(c)]
                hk_codes = [c for c in normalized if api.get_market(c) == "HK"]
                us_codes = [c for c in normalized if api.get_market(c) == "US"]

                # 批量获取 A 股基本信息
                if a_stock_codes_only:
                    ts_codes_str = ",".join(a_stock_codes_only)
                    basic_df = await cache.cached_call(
                        api.pro.stock_basic,
                        cache_type="basic",
                        ts_code=ts_codes_str,
                        fields='ts_code,name'
                    )
                    if not basic_df.empty:
                        for _, row in basic_df.iterrows():
                            stock_names[row['ts_code']] = row['name']

                # 获取指数名称
                if index_codes_only:
                    idx_df = await cache.cached_call(
                        api.pro.index_basic,
                        cache_type="basic",
                        fields='ts_code,name'
                    )
                    if idx_df is not None and not idx_df.empty:
                        idx_map = dict(zip(idx_df['ts_code'], idx_df['name']))
                        for code in index_codes_only:
                            if code in idx_map:
                                stock_names[code] = idx_map[code]

                # 获取港股名称
                if hk_codes:
                    hk_df = await cache.cached_call(
                        api.pro.hk_basic,
                        cache_type="basic",
                        fields='ts_code,name'
                    )
                    if hk_df is not None and not hk_df.empty:
                        hk_map = dict(zip(hk_df['ts_code'], hk_df['name']))
                        for code in hk_codes:
                            if code in hk_map:
                                stock_names[code] = hk_map[code]

                # 获取美股名称
                if us_codes:
                    us_df = await cache.cached_call(
                        api.pro.us_basic,
                        cache_type="basic",
                        fields='ts_code,name,enname'
                    )
                    if us_df is not None and not us_df.empty:
                        us_map = dict(zip(us_df['ts_code'], us_df['name']))
                        for code in us_codes:
                            if code in us_map:
                                stock_names[code] = us_map[code]

                logger.info(f"📛 [analyze_price_correlation] Names: {stock_names}")
            except Exception as name_err:
                logger.warning(f"⚠️ [analyze_price_correlation] 获取名称失败: {name_err}")
                # 回退：使用代码作为名称
                for stock_code in stock_codes:
                    ts_code = api.normalize_stock_code(stock_code)
                    stock_names[ts_code] = ts_code

            result["stock_names"] = stock_names

            if result.get("correlation_matrix") and result.get("time_series"):
                result["ui"] = _build_correlation_ui(
                    title="价格相关性矩阵",
                    subtitle=f"{start_date} - {end_date} · {len(stock_names)} 个标的",
                    correlation_matrix=result["correlation_matrix"],
                    time_series=result["time_series"],
                    stock_names=stock_names,
                )

            # 把相关性矩阵展平为行：每行 {a, b, value}，方便 as_file 导出
            _corr_rows = []
            for a, inner in (result.get("correlation_matrix") or {}).items():
                if isinstance(inner, dict):
                    for b, val in inner.items():
                        _corr_rows.append({"stock_a": a, "stock_b": b, "correlation": val})
            _header = f"相关性分析 | {len(stock_names)} 个标的 × {start_date}~{end_date} | {len(_corr_rows)} 对"
            return finalize_artifact_result(
                rows=_corr_rows,
                result=result,
                tool_name="analyze_price_correlation",
                query_params={"stock_codes": ",".join(stock_codes or []), "start_date": start_date, "end_date": end_date, "analysis_type": analysis_type},
                ui_uri="ui://findata/correlation-matrix",
                as_file=as_file,
                include_ui=include_ui,
                header_text=_header,
            )

        except Exception as e:
            return {
                "success": False,
                "error": f"量化分析异常: {str(e)}",
                "stock_codes": stock_codes
            }

    @mcp.tool(tags={"量化分析"})
    async def analyze_stock_performance(
        stock_codes: List[str],
        start_date: str = None,
        end_date: str = None,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """
        深度量化分析引擎（企业级）

        集成技术指标、风险调整收益、相关性分析的全能工具。

        Args:
            stock_codes: 股票代码列表，例如 ["600519.SH", "000858.SZ"]
            start_date: 开始日期，格式 YYYYMMDD，可选，默认为最近1年
            end_date: 结束日期，格式 YYYYMMDD，可选，默认为昨天
            analysis_type: 分析类型，comprehensive=综合分析，technical=技术指标，risk=风险分析

        Returns:
            深度量化分析结果

        Examples:
            >>> result = await analyze_stock_performance(["000001"], "20230101", "20231231", "comprehensive")
            >>> print(f"夏普比率: {result['performance']['sharpe_ratio']}")
        """
        # 设置默认日期
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')  # 🔥 先设为今天，后续会自动调整

        # 参数验证
        if not isinstance(stock_codes, list):
            return {
                "success": False,
                "error": f"参数 stock_codes 必须是列表类型，当前收到: {type(stock_codes)} = {stock_codes[:100] if isinstance(stock_codes, str) else stock_codes}",
                "hint": "请从 get_sector_top_stocks 工具的返回结果中提取 'codes' 字段，例如: result['codes']"
            }

        if not stock_codes:
            return {
                "success": False,
                "error": "股票代码列表不能为空",
                "hint": "请先调用 get_sector_top_stocks 获取股票代码列表，然后使用返回结果中的 'codes' 字段"
            }
        """
        深度量化分析引擎（企业级）

        集成技术指标、风险调整收益、相关性分析的全能工具。

        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
            analysis_type: 分析类型，comprehensive=综合分析，technical=技术指标，risk=风险分析

        Returns:
            深度量化分析结果

        Examples:
            >>> result = await analyze_stock_performance(["000001"], "20230101", "20231231", "comprehensive")
            >>> print(f"夏普比率: {result['performance']['sharpe_ratio']}")
        """
        date_adjust_msg = ""  # 🔥 日期调整说明
        try:
            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}
            
            # 🔥 日期容错：自动调整结束日期到最近交易日
            end_date, date_adjust_msg = await _adjust_end_date_to_latest_trading_day(cache, api, end_date)
            logger.info(f"📅 [analyze_stock_performance] Using date range: {start_date} - {end_date}")

            if len(stock_codes) != 1:
                return {"success": False, "error": "此工具目前只支持单只股票分析"}

            stock_code = stock_codes[0]
            ts_code = api.normalize_stock_code(stock_code)

            # 获取历史数据（支持指数）
            df = await fetch_daily_data(
                cache, api, ts_code,
                cache_type="daily",
                start_date=start_date,
                end_date=end_date
            )

            if df is None or df.empty:
                return {"success": False, "error": f"未找到 {stock_code} 的历史数据"}

            df = df.sort_values('trade_date')
            df.reset_index(drop=True, inplace=True)

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

            result = {
                "success": True,
                "stock_code": stock_code,
                "ts_code": ts_code,
                "asset_type": _asset_type,
                "start_date": start_date,
                "end_date": end_date,
                "analysis_type": analysis_type,
                "data_points": len(df),
                "timestamp": datetime.now().isoformat()
            }
            
            # 🔥 添加日期调整说明（如果有的话）
            if date_adjust_msg:
                result["date_adjusted"] = True
                result["date_adjust_message"] = date_adjust_msg

            close_prices = df['close'].values
            # 区间基准价：优先用首日 pre_close（前一交易日收盘），正确覆盖假期跳空
            if 'pre_close' in df.columns and pd.notna(df['pre_close'].iloc[0]):
                _base_px = float(df['pre_close'].iloc[0])
            else:
                _base_px = float(close_prices[0])
            returns = np.diff(np.log(close_prices))

            # 基础业绩分析
            if analysis_type in ["comprehensive", "performance"]:
                result["performance"] = {
                    "total_return": ((close_prices[-1] / _base_px) - 1) * 100,
                    "annual_return": (((close_prices[-1] / _base_px) ** (252 / len(close_prices))) - 1) * 100,
                    "volatility": np.std(returns) * np.sqrt(252) * 100,
                    "sharpe_ratio": calculate_sharpe_ratio(returns),
                    "max_drawdown": calculate_max_drawdown(close_prices),
                    "var_95": calculate_var(returns, 0.95),
                    "beta": calculate_beta(df),
                    "avg_daily_return": np.mean(returns) * 100,
                    "positive_days_ratio": (np.sum(returns > 0) / len(returns)) * 100
                }

            # 技术指标分析
            if analysis_type in ["comprehensive", "technical"]:
                result["technical_indicators"] = {}

                # 移动平均线
                ma_indicators = calculate_moving_averages(pd.Series(close_prices))
                result["technical_indicators"]["moving_averages"] = ma_indicators

                # RSI
                if len(close_prices) >= 14:
                    result["technical_indicators"]["rsi_14"] = calculate_rsi(pd.Series(close_prices), 14)
                    result["technical_indicators"]["rsi_6"] = calculate_rsi(pd.Series(close_prices), 6)

                # MACD
                if len(close_prices) >= 34:
                    result["technical_indicators"]["macd"] = calculate_macd(pd.Series(close_prices))

                # 布林带
                if len(close_prices) >= 20:
                    result["technical_indicators"]["bollinger_bands"] = calculate_bollinger_bands(pd.Series(close_prices))

                # KDJ指标
                if len(df) >= 9:
                    result["technical_indicators"]["kdj"] = calculate_kdj(df)

                # 威廉指标
                if len(df) >= 14:
                    result["technical_indicators"]["williams_r"] = calculate_williams(df, 14)

                # CCI指标
                if len(df) >= 20:
                    result["technical_indicators"]["cci"] = calculate_cci(df, 20)

                # ROC指标
                if len(close_prices) >= 12:
                    result["technical_indicators"]["roc_12"] = calculate_roc(pd.Series(close_prices), 12)

                # TRIX指标
                if len(close_prices) >= 20:
                    result["technical_indicators"]["trix"] = calculate_trix(pd.Series(close_prices))

                # OBV指标
                if len(df) >= 10:
                    result["technical_indicators"]["obv"] = calculate_obv(df)

                # 量比
                if len(df) > 5:
                    result["technical_indicators"]["volume_ratio"] = calculate_volume_ratio(df)

                # ATR指标
                if len(df) >= 14:
                    result["technical_indicators"]["atr"] = calculate_atr(df, 14)

                # 相对强弱
                result["technical_indicators"]["relative_strength"] = calculate_relative_strength(df)

            # 风险分析
            if analysis_type in ["comprehensive", "risk"]:
                result["risk_analysis"] = {
                    "sharpe_ratio": calculate_sharpe_ratio(returns),
                    "max_drawdown": calculate_max_drawdown(close_prices),
                    "var_95": calculate_var(returns, 0.95),
                    "beta": calculate_beta(df),
                    "total_volatility": np.std(returns) * np.sqrt(252) * 100,
                    "downside_risk": None  # 需要实现downside_risk函数
                }

                # 计算下行风险（如果有足够数据）
                if len(returns) > 0:
                    from ..utils.technical_indicators import calculate_downside_risk
                    result["risk_analysis"]["downside_risk"] = calculate_downside_risk(returns)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"深度量化分析异常: {str(e)}",
                "stock_codes": stock_codes
            }

    @mcp.tool(tags={"量化分析"}, app=CORRELATION_MATRIX_APP)
    async def calculate_metrics(stock_codes: List[str], start_date: str = None, end_date: str = None, metric: str = "close", as_file: bool = False, include_ui: bool = True) -> Dict[str, Any]:
        """
        计算一组股票的金融指标（相关性矩阵）

        Args:
            stock_codes: 股票代码列表，例如 ["600519.SH", "000858.SZ"]
            start_date: 开始日期 (YYYYMMDD)，可选，默认为最近1年
            end_date: 结束日期 (YYYYMMDD)，可选，默认为昨天
            metric: 计算基于的字段 (close/vol/pct_chg)，默认为收盘价 close

        Returns:
            包含相关性矩阵和统计信息的字典
        """
        # 🔧 智能参数解析：处理MCP客户端参数传递错误的情况
        # 有时候客户端会把所有参数都传给第一个参数
        if isinstance(stock_codes, list) and len(stock_codes) >= 3:
            # 检查是否是参数混乱的情况
            first_param = stock_codes[0]
            if isinstance(first_param, str) and (first_param.startswith('<') or first_param.startswith('%')):
                # 检测到模板字符串，尝试重新解析参数
                try:
                    actual_stock_codes = stock_codes[0]  # 这里应该是列表，但现在是字符串
                    if isinstance(actual_stock_codes, str) and (actual_stock_codes.startswith('[') or actual_stock_codes.startswith('%')):
                        # 如果是字符串格式的列表，尝试解析
                        # 但这里可能需要从上一个工具的结果中提取
                        pass

                    # 使用后续参数
                    if len(stock_codes) >= 2:
                        start_date = stock_codes[1] if isinstance(stock_codes[1], str) else start_date
                    if len(stock_codes) >= 3:
                        end_date = stock_codes[2] if isinstance(stock_codes[2], str) else end_date
                    if len(stock_codes) >= 4:
                        metric = stock_codes[3] if isinstance(stock_codes[3], str) else metric

                    # 尝试从get_sector_top_stocks的结果中提取codes
                    # 这里假设stock_codes[0]包含了上一个工具的结果
                    stock_codes = []  # 重置为空，后续会报错并给出提示

                except Exception as e:
                    return {
                        "success": False,
                        "error": f"参数解析失败: {str(e)}",
                        "hint": "请确保参数格式正确，或者使用 get_sector_top_stocks 的返回结果中的 'codes' 字段"
                    }

        # 设置默认日期
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')  # 🔥 先设为今天，后续会自动调整

        # 参数验证：检查 stock_codes 是否为有效的列表
        if not isinstance(stock_codes, list):
            return {
                "success": False,
                "error": f"参数 stock_codes 必须是列表类型，当前收到: {type(stock_codes)} = {stock_codes[:100] if isinstance(stock_codes, str) else stock_codes}",
                "hint": "请从 get_sector_top_stocks 工具的返回结果中提取 'codes' 字段，例如: result['codes']"
            }

        if not stock_codes:
            return {
                "success": False,
                "error": "股票代码列表不能为空",
                "hint": "请先调用 get_sector_top_stocks 获取股票代码列表，然后使用返回结果中的 'codes' 字段"
            }
        """
        计算一组股票的金融指标（相关性矩阵）

        Args:
            stock_codes: 股票代码列表，例如 ["600519.SH", "000858.SZ"]
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            metric: 计算基于的字段 (close/vol/pct_chg)，默认为收盘价 close

        Returns:
            包含相关性矩阵和统计信息的字典
        """
        date_adjust_msg = ""  # 🔥 日期调整说明
        try:
            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}
            
            # 🔥 日期容错：自动调整结束日期到最近交易日
            end_date, date_adjust_msg = await _adjust_end_date_to_latest_trading_day(cache, api, end_date)
            logger.info(f"📅 [calculate_metrics] Using date range: {start_date} - {end_date}")

            # 分离股票、指数、港股、美股代码
            normalized = [api.normalize_stock_code(c) for c in stock_codes]
            stock_only = [c for c in normalized if api.get_market(c) == "A" and not api.is_index_code(c)]
            index_only = [c for c in normalized if api.get_market(c) == "A" and api.is_index_code(c)]
            hk_only = [c for c in normalized if api.get_market(c) == "HK"]
            us_only = [c for c in normalized if api.get_market(c) == "US"]

            dfs = []
            # A 股：批量查询
            if stock_only:
                ts_codes_str = ",".join(stock_only)
                df_stocks = await cache.cached_call(
                    api.pro.daily,
                    cache_type="daily",
                    ts_code=ts_codes_str,
                    start_date=start_date,
                    end_date=end_date
                )
                if df_stocks is not None and not df_stocks.empty:
                    dfs.append(df_stocks)

            # 指数：逐个查询（不同指数走不同 API）
            for idx_code in index_only:
                df_idx = await fetch_daily_data(
                    cache, api, idx_code,
                    cache_type="daily",
                    start_date=start_date,
                    end_date=end_date
                )
                if df_idx is not None and not df_idx.empty:
                    dfs.append(df_idx)

            # 港股：逐个查询
            for hk_code in hk_only:
                df_hk = await fetch_daily_data(
                    cache, api, hk_code,
                    cache_type="daily",
                    start_date=start_date,
                    end_date=end_date
                )
                if df_hk is not None and not df_hk.empty:
                    dfs.append(df_hk)

            # 美股：逐个查询
            for us_code in us_only:
                df_us = await fetch_daily_data(
                    cache, api, us_code,
                    cache_type="daily",
                    start_date=start_date,
                    end_date=end_date
                )
                if df_us is not None and not df_us.empty:
                    dfs.append(df_us)

            if not dfs:
                return {"success": False, "error": "未获取到数据"}

            df_all = pd.concat(dfs, ignore_index=True)

            if df_all.empty:
                return {"success": False, "error": "未获取到数据"}

            # 透视表：行=日期，列=股票代码，值=metric
            pivot_df = df_all.pivot(index='trade_date', columns='ts_code', values=metric)

            # 按日期排序（上游API返回可能是倒序）
            pivot_df = pivot_df.sort_index()

            if pivot_df.empty:
                return {"success": False, "error": "数据透视后为空"}

            # 🔥 重要修复：使用收益率计算相关性（金融标准做法）
            # 原始价格相关性受趋势影响大，不能准确反映股票联动性
            # 收益率相关性才是衡量两只股票日涨跌联动性的正确指标
            returns_df = pivot_df.pct_change().dropna()  # 计算日收益率
            
            if returns_df.empty or len(returns_df) < 2:
                # 如果收益率数据不足，回退到原始价格
                corr_matrix = pivot_df.corr()
                logger.warning("⚠️ [calculate_metrics] 收益率数据不足，回退到原始价格相关性")
            else:
                corr_matrix = returns_df.corr()  # 使用收益率计算相关性

            # 转换为 Markdown 表格
            markdown_table = corr_matrix.to_markdown()
            
            # 🔥 修复：处理 NaN 值，转换为可序列化的字典格式
            def corr_matrix_to_safe_dict(matrix: pd.DataFrame) -> dict:
                """将相关性矩阵转换为 JSON 安全的字典格式，处理 NaN 值"""
                result = {}
                for row_key in matrix.index:
                    result[row_key] = {}
                    for col_key in matrix.columns:
                        value = matrix.loc[row_key, col_key]
                        # NaN 转为 None（JSON null），保留有效数值
                        result[row_key][col_key] = float(value) if pd.notna(value) else None
                return result
            
            safe_corr_dict = corr_matrix_to_safe_dict(corr_matrix)
            
            # 🔥 新增：构建时间序列数据用于前端图表展示
            # 格式: { "600519.SH": [{"date": "20241201", "close": 1500.0}, ...], ... }
            time_series = {}
            ts_codes_list = list(pivot_df.columns)
            for ts_code in ts_codes_list:
                series_data = []
                for date_str, price in pivot_df[ts_code].items():
                    if pd.notna(price):
                        series_data.append({
                            "date": str(date_str),
                            "close": round(float(price), 2)
                        })
                time_series[ts_code] = series_data

            # 🔥 新增：获取股票/指数名称映射，避免LLM自行推断名称时出错
            stock_names = {}
            try:
                # 批量获取 A 股基本信息
                if stock_only:
                    basic_df = await cache.cached_call(
                        api.pro.stock_basic,
                        cache_type="basic",
                        ts_code=",".join(stock_only),
                        fields='ts_code,name'
                    )
                    if not basic_df.empty:
                        for _, row in basic_df.iterrows():
                            stock_names[row['ts_code']] = row['name']

                # 获取指数名称
                if index_only:
                    idx_df = await cache.cached_call(
                        api.pro.index_basic,
                        cache_type="basic",
                        fields='ts_code,name'
                    )
                    if idx_df is not None and not idx_df.empty:
                        idx_map = dict(zip(idx_df['ts_code'], idx_df['name']))
                        for code in index_only:
                            if code in idx_map:
                                stock_names[code] = idx_map[code]

                # 获取港股名称
                if hk_only:
                    hk_df = await cache.cached_call(
                        api.pro.hk_basic,
                        cache_type="basic",
                        fields='ts_code,name'
                    )
                    if hk_df is not None and not hk_df.empty:
                        hk_map = dict(zip(hk_df['ts_code'], hk_df['name']))
                        for code in hk_only:
                            if code in hk_map:
                                stock_names[code] = hk_map[code]

                # 获取美股名称
                if us_only:
                    us_df = await cache.cached_call(
                        api.pro.us_basic,
                        cache_type="basic",
                        fields='ts_code,name,enname'
                    )
                    if us_df is not None and not us_df.empty:
                        us_map = dict(zip(us_df['ts_code'], us_df['name']))
                        for code in us_only:
                            if code in us_map:
                                stock_names[code] = us_map[code]

                logger.info(f"📛 [calculate_metrics] Names: {stock_names}")
            except Exception as name_err:
                logger.warning(f"⚠️ [calculate_metrics] 获取名称失败: {name_err}")
                # 回退：使用代码作为名称
                for ts_code in ts_codes_list:
                    stock_names[ts_code] = ts_code
            
            # 🔥 将副产品存储到缓存，生成资源引用（与 analyze_price_correlation 保持一致）
            calc_id = calc_metrics_cache.store(
                stock_codes=ts_codes_list,
                start_date=start_date,
                end_date=end_date,
                time_series=time_series,
                correlation_matrix=safe_corr_dict  # 🔥 使用处理过 NaN 的字典
            )

            sampled_time_series = {
                code: sample_rows(series, max_points=120)
                for code, series in time_series.items()
            }
            result = {
                "success": True,
                "type": "text",
                "content": f"## 股价相关性矩阵 ({metric}, {start_date}-{end_date})\n\n{markdown_table}",
                "correlation_matrix": safe_corr_dict,  # 🔥 使用处理过 NaN 的字典
                "stock_count": len(pivot_df.columns),
                "date_range": f"{pivot_df.index[0]} - {pivot_df.index[-1]}",
                # 🔥 新增：股票代码到名称的映射，方便LLM准确解读
                "stock_names": stock_names,
                # 🔥 新增：时间序列数据，用于前端绘制股价对比图
                "time_series": sampled_time_series,
                # 🔥 新增：资源 URI，支持前端按需加载派生指标
                "calc_id": calc_id,
                "resource_uri": f"stock://calc_metrics/{calc_id}",
                "ui": _build_correlation_ui(
                    title=f"{metric} 相关性矩阵",
                    subtitle=f"{start_date} - {end_date} · {len(ts_codes_list)} 个标的",
                    correlation_matrix=safe_corr_dict,
                    time_series=sampled_time_series,
                    stock_names=stock_names,
                ),
            }
            
            # 🔥 添加日期调整说明（如果有的话）
            if date_adjust_msg:
                result["date_adjusted"] = True
                result["date_adjust_message"] = date_adjust_msg

            # 相关性矩阵展平为行
            _corr_rows = []
            for a, inner in (safe_corr_dict or {}).items():
                if isinstance(inner, dict):
                    for b, val in inner.items():
                        _corr_rows.append({"stock_a": a, "stock_b": b, "correlation": val})
            _header = f"{metric} 相关性矩阵 | {len(ts_codes_list)} 个标的 × {start_date}~{end_date} | {len(_corr_rows)} 对"
            return finalize_artifact_result(
                rows=_corr_rows,
                result=result,
                tool_name="calculate_metrics",
                query_params={"stock_codes": ",".join(ts_codes_list or []), "start_date": start_date, "end_date": end_date, "metric": metric},
                ui_uri="ui://findata/correlation-matrix",
                as_file=as_file,
                include_ui=include_ui,
                header_text=_header,
            )

        except Exception as e:
            return {"success": False, "error": f"计算指标异常: {str(e)}"}
