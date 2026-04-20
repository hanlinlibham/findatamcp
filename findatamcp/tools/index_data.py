"""指数数据工具

提供指数专属的MCP工具，包括：
- get_index_weight: 获取指数成分股及权重
- get_index_valuation: 获取指数估值数据（PE/PB/换手率/市值）
- get_industry_overview: 行业分类与成分查询（申万/中信）
"""

from typing import Literal, Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
import logging

from ..cache import cache
from ..utils.tushare_api import TushareAPI
from ..utils.large_data_handler import handle_large_data, merge_large_data_payload, prepare_large_data_view
from ..utils.ui_hint import attach_hint_to_dict
from ..utils.artifact_payload import finalize_artifact_result, AS_FILE_INCLUDE_UI_DECISION_GUIDE
from .constants import READONLY_ANNOTATIONS

logger = logging.getLogger(__name__)

SERIES_CHART_APP = AppConfig(
    resource_uri="ui://findata/series-chart",
    visibility=["model", "app"],
)


def _build_index_valuation_ui(ts_code: str, rows: list[dict[str, Any]]) -> Dict[str, Any]:
    """构建指数估值通用图表 view model。"""
    chart_rows = sorted(rows, key=lambda item: str(item.get("trade_date") or ""))
    latest = chart_rows[-1] if chart_rows else {}
    sample = chart_rows[-1] if chart_rows else {}

    panels = []

    valuation_series = []
    for field, name in [("pe", "PE"), ("pe_ttm", "PE_TTM"), ("pb", "PB")]:
        if field in sample:
            valuation_series.append({"name": name, "field": field})
    if valuation_series:
        panels.append({
            "title": "估值指标",
            "xField": "trade_date",
            "data": chart_rows,
            "series": valuation_series,
            "yAxes": [{"name": "倍数"}],
        })

    mv_series = []
    for field, name in [("total_mv", "总市值"), ("float_mv", "流通市值")]:
        if field in sample:
            mv_series.append({"name": name, "field": field})
    if mv_series:
        panels.append({
            "title": "市值变化",
            "xField": "trade_date",
            "data": chart_rows,
            "series": mv_series,
            "yAxes": [{"name": "亿元"}],
        })

    turnover_series = []
    for field, name in [("turnover_rate", "换手率"), ("turnover_rate_f", "自由流通换手率")]:
        if field in sample:
            turnover_series.append({"name": name, "field": field})
    if turnover_series:
        panels.append({
            "title": "市场活跃度",
            "xField": "trade_date",
            "data": chart_rows,
            "series": turnover_series,
            "yAxes": [{"name": "%", "format": "percent"}],
        })

    stats = [{"label": "样本数", "value": str(len(chart_rows))}]
    for field, label in [("pe", "最新PE"), ("pe_ttm", "最新PE_TTM"), ("pb", "最新PB"), ("turnover_rate", "最新换手率")]:
        if latest.get(field) is not None:
            suffix = "%" if "turnover" in field else ""
            stats.append({"label": label, "value": f"{latest.get(field)}{suffix}"})

    return {
        "kind": "series-chart",
        "title": f"{ts_code} 指数估值走势",
        "subtitle": f"{len(chart_rows)} 条记录",
        "stats": stats,
        "panels": panels,
    }


def register_index_tools(mcp: FastMCP, api: TushareAPI):
    """注册指数数据工具"""

    @mcp.tool(tags={"指数数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_index_weight(
        index_code: str,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取指数成分股及权重（按权重降序）

        Args:
            index_code: 指数代码，如 '000300.SH'(沪深300)、'000016.SH'(上证50)
            trade_date: 交易日期(YYYYMMDD)，获取该日快照
            start_date: 开始日期(YYYYMMDD)
            end_date: 结束日期(YYYYMMDD)
        """
        try:
            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            kwargs = {"index_code": index_code}
            if trade_date:
                kwargs["trade_date"] = trade_date
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date

            df = await cache.cached_call(
                api.pro.index_weight,
                cache_type="daily",
                **kwargs
            )

            if df is None or df.empty:
                return {
                    "success": False,
                    "error": f"未找到指数 {index_code} 的成分股数据",
                    "index_code": index_code
                }

            # 按权重降序排列
            df = df.sort_values('weight', ascending=False)

            constituents = df.to_dict('records')

            result = {
                "success": True,
                "index_code": index_code,
                "count": len(constituents),
                "timestamp": datetime.now().isoformat()
            }
            large = handle_large_data(constituents, "get_index_weight", {"index_code": index_code, "trade_date": trade_date}, preview_rows=20)
            if "is_truncated" in large:
                result.update(large)
            else:
                result["constituents"] = large["data"]
            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"获取指数成分股异常: {str(e)}",
                "index_code": index_code
            }

    @mcp.tool(tags={"指数数据"}, annotations=READONLY_ANNOTATIONS, app=SERIES_CHART_APP)
    async def get_index_valuation(
        ts_code: str = "",
        stock_code: str = "",
        code: str = "",
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        as_file: bool = False,
        include_ui: bool = True,
    ) -> Dict[str, Any]:
        """获取指数估值数据（PE/PB/换手率/市值，支持宽基和申万指数）。
返回形态（默认）：内嵌估值曲线 UI（ui://findata/series-chart）+ 结构化数据预览。

Args:
    ts_code: 指数代码，如 '000300.SH'(沪深300)、'801010.SI'(申万农林牧渔)
    trade_date: 交易日期(YYYYMMDD)
    start_date: 开始日期(YYYYMMDD)
    end_date: 结束日期(YYYYMMDD)
    as_file: 为 True 时把完整估值序列写成 .jsonl 文件
    include_ui: 为 False 时不附加内嵌估值曲线 UI
""" + AS_FILE_INCLUDE_UI_DECISION_GUIDE
        try:
            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供指数代码（参数名: ts_code, stock_code 或 code）"}

            kwargs = {"ts_code": ts_code}
            if trade_date:
                kwargs["trade_date"] = trade_date
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date

            df = None

            # 申万行业指数：sw_daily 自带 pe/pb/total_mv/float_mv
            if ts_code.upper().endswith('.SI'):
                raw = await cache.cached_call(
                    api.pro.sw_daily,
                    cache_type="daily",
                    **kwargs
                )
                if raw is not None and not raw.empty:
                    # 只保留估值相关列
                    keep_cols = ['ts_code', 'trade_date', 'pe', 'pb', 'total_mv', 'float_mv']
                    available = [c for c in keep_cols if c in raw.columns]
                    df = raw[available].copy()
            else:
                # 宽基指数：index_dailybasic
                df = await cache.cached_call(
                    api.pro.index_dailybasic,
                    cache_type="daily",
                    **kwargs
                )

            if df is None or df.empty:
                return {
                    "success": False,
                    "error": f"未找到指数 {ts_code} 的估值数据",
                    "ts_code": ts_code
                }

            df = df.sort_values('trade_date')
            data = df.to_dict('records')

            _latest = data[-1] if data else {}
            _header = f"{ts_code} 指数估值 | {len(data)} 条记录 | 最新 {_latest.get('trade_date','-')} PE={_latest.get('pe','-')} PB={_latest.get('pb','-')}"

            result = {
                "success": True,
                "ts_code": ts_code,
                "ui": _build_index_valuation_ui(ts_code, data[-120:] if len(data) > 120 else data),
                "timestamp": datetime.now().isoformat()
            }
            return finalize_artifact_result(
                rows=data,
                result=result,
                tool_name="get_index_valuation",
                query_params={"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date},
                ui_uri="ui://findata/series-chart",
                as_file=as_file,
                include_ui=include_ui,
                header_text=_header,
            )

        except Exception as e:
            return {
                "success": False,
                "error": f"获取指数估值数据异常: {str(e)}",
                "ts_code": ts_code
            }

    @mcp.tool(tags={"指数数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_industry_overview(
        action: Literal["classify", "sw_members", "ci_members"],
        level: Optional[str] = None,
        src: Optional[str] = None,
        index_code: Optional[str] = None,
        ts_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """行业分类与成分股查询（申万/中信）

        Args:
            action: 仅支持以下 3 个值（区分大小写）：classify(行业分类列表) / sw_members(申万成分股) / ci_members(中信成分股)。不要传其他值
            level: 行业级别，仅 classify 用，L1/L2/L3
            src: 分类来源，仅 classify 用，如 "SW2021"
            index_code: 行业指数代码，如 "801010.SI"
            ts_code: 个股代码，查询所属行业
        """
        try:
            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            if action == "classify":
                kwargs = {}
                if level:
                    kwargs["level"] = level
                if src:
                    kwargs["src"] = src

                df = await cache.cached_call(
                    api.pro.index_classify,
                    cache_type="basic",
                    **kwargs
                )

                if df is None or df.empty:
                    return {"success": False, "error": "未找到行业分类数据"}

                data = df.to_dict('records')
                return {
                    "success": True,
                    "action": action,
                    "count": len(data),
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "sw_members":
                kwargs = {}
                if index_code:
                    # 申万代码层级：L1=801xxx, L2=8011xx/8012xx等(4位前缀), L3=更细分
                    # 先匹配更具体的层级，再回退到 L1
                    numeric = index_code.split('.')[0]
                    if len(numeric) == 6 and numeric[:3] == '801':
                        # 检查第4位是否为0：801xx0 通常是 L1，否则是 L2/L3
                        if len(numeric) >= 4 and numeric[3] != '0':
                            kwargs["l2_code"] = index_code
                        else:
                            kwargs["l1_code"] = index_code
                    else:
                        kwargs["l1_code"] = index_code
                if ts_code:
                    kwargs["ts_code"] = ts_code

                df = await cache.cached_call(
                    api.pro.index_member_all,
                    cache_type="basic",
                    **kwargs
                )

                if df is None or df.empty:
                    return {"success": False, "error": "未找到申万行业成分数据"}

                data = df.to_dict('records')
                result = {
                    "success": True,
                    "action": action,
                    "count": len(data),
                    "timestamp": datetime.now().isoformat()
                }
                large = handle_large_data(data, "get_industry_overview_sw", {"index_code": index_code, "ts_code": ts_code}, preview_rows=20)
                if "is_truncated" in large:
                    result.update(large)
                else:
                    result["data"] = large["data"]
                return result

            elif action == "ci_members":
                kwargs = {}
                if index_code:
                    kwargs["l1_code"] = index_code
                if ts_code:
                    kwargs["ts_code"] = ts_code

                df = await cache.cached_call(
                    api.pro.ci_index_member,
                    cache_type="basic",
                    **kwargs
                )

                if df is None or df.empty:
                    return {"success": False, "error": "未找到中信行业成分数据"}

                data = df.to_dict('records')
                result = {
                    "success": True,
                    "action": action,
                    "count": len(data),
                    "timestamp": datetime.now().isoformat()
                }
                large = handle_large_data(data, "get_industry_overview_ci", {"index_code": index_code, "ts_code": ts_code}, preview_rows=20)
                if "is_truncated" in large:
                    result.update(large)
                else:
                    result["data"] = large["data"]
                return result

            else:
                return {
                    "success": False,
                    "error": f"不支持的 action: {action}，请使用 classify/sw_members/ci_members"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"行业查询异常: {str(e)}",
                "action": action
            }
