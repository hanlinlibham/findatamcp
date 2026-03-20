"""基金数据工具

提供公募基金MCP工具：
- get_fund_data: 综合基金信息（基本面+净值+经理+规模）
- get_fund_nav: 基金净值时间序列
- get_fund_portfolio: 基金持仓明细 / 反查个股被持仓
"""

from typing import Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP
import asyncio
import logging

from ..cache import cache
from ..utils.tushare_api import TushareAPI
from .constants import READONLY_ANNOTATIONS

logger = logging.getLogger(__name__)


def register_fund_tools(mcp: FastMCP, api: TushareAPI):
    """注册基金数据工具"""

    @mcp.tool(tags={"基金数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_fund_data(ts_code: str = "", stock_code: str = "", code: str = "") -> Dict[str, Any]:
        """获取基金综合信息（基本面、最新净值、基金经理、份额规模）

        Args:
            ts_code: 基金代码，如 '510300.SH'(沪深300ETF)、'000001.OF'(华夏成长)
        """
        try:
            if not api.is_available():
                return {"success": False, "error": "Tushare Pro not available"}

            result: Dict[str, Any] = {"success": True, "ts_code": ts_code}

            # 并发获取基本信息、最新净值、基金经理、份额
            tasks = {
                "basic": cache.cached_call(
                    api.pro.fund_basic, cache_type="basic", ts_code=ts_code
                ),
                "nav": cache.cached_call(
                    api.pro.fund_nav, cache_type="daily", ts_code=ts_code, limit=1
                ),
                "manager": cache.cached_call(
                    api.pro.fund_manager, cache_type="basic", ts_code=ts_code
                ),
                "share": cache.cached_call(
                    api.pro.fund_share, cache_type="daily", ts_code=ts_code, limit=1
                ),
            }
            # ETF 额外获取 etf_basic（含追踪指数、ETF类型）
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供基金代码（参数名: ts_code, stock_code 或 code）"}
            is_etf = api.is_fund_code(ts_code)
            if is_etf:
                tasks["etf"] = cache.cached_call(
                    api.pro.etf_basic, cache_type="basic", ts_code=ts_code,
                    fields="ts_code,extname,index_code,index_name,mgr_name,mgt_fee,etf_type"
                )

            keys = list(tasks.keys())
            results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
            fetched = dict(zip(keys, results_list))

            basic_df = fetched["basic"]
            nav_df = fetched["nav"]
            mgr_df = fetched["manager"]
            share_df = fetched["share"]

            # 基本信息
            if not isinstance(basic_df, Exception) and basic_df is not None and not basic_df.empty:
                row = basic_df.iloc[0]
                result["basic"] = {
                    "name": row.get("name"),
                    "fund_type": row.get("fund_type"),
                    "invest_type": row.get("invest_type"),
                    "type": row.get("type"),
                    "management": row.get("management"),
                    "custodian": row.get("custodian"),
                    "benchmark": row.get("benchmark"),
                    "found_date": row.get("found_date"),
                    "list_date": row.get("list_date"),
                    "status": row.get("status"),
                    "m_fee": row.get("m_fee"),
                    "c_fee": row.get("c_fee"),
                    "market": row.get("market"),
                }
            else:
                result["basic"] = None

            # ETF 专属信息（追踪指数、ETF类型）
            if is_etf:
                etf_df = fetched.get("etf")
                if not isinstance(etf_df, Exception) and etf_df is not None and not etf_df.empty:
                    row = etf_df.iloc[0]
                    result["etf_info"] = {
                        "index_code": row.get("index_code"),
                        "index_name": row.get("index_name"),
                        "etf_type": row.get("etf_type"),
                        "mgr_name": row.get("mgr_name"),
                        "mgt_fee": row.get("mgt_fee"),
                    }
                else:
                    result["etf_info"] = None

            # 最新净值
            if not isinstance(nav_df, Exception) and nav_df is not None and not nav_df.empty:
                row = nav_df.iloc[0]
                result["latest_nav"] = {
                    "nav_date": row.get("nav_date"),
                    "unit_nav": row.get("unit_nav"),
                    "accum_nav": row.get("accum_nav"),
                    "adj_nav": row.get("adj_nav"),
                    "net_asset": row.get("net_asset"),
                }
            else:
                result["latest_nav"] = None

            # 基金经理（当前在任）
            if not isinstance(mgr_df, Exception) and mgr_df is not None and not mgr_df.empty:
                # end_date 为空表示当前在任
                if "end_date" in mgr_df.columns:
                    current = mgr_df[mgr_df["end_date"].isna() | (mgr_df["end_date"] == "")]
                    if current.empty:
                        current = mgr_df.head(1)
                else:
                    current = mgr_df.head(1)
                managers = []
                for _, row in current.iterrows():
                    managers.append({
                        "name": row.get("name"),
                        "begin_date": row.get("begin_date"),
                        "edu": row.get("edu"),
                        "gender": row.get("gender"),
                    })
                result["managers"] = managers
            else:
                result["managers"] = []

            # 最新份额
            if not isinstance(share_df, Exception) and share_df is not None and not share_df.empty:
                row = share_df.iloc[0]
                result["latest_share"] = {
                    "trade_date": row.get("trade_date"),
                    "fd_share": row.get("fd_share"),  # 万份
                }
            else:
                result["latest_share"] = None

            result["timestamp"] = datetime.now().isoformat()
            return result

        except Exception as e:
            return {"success": False, "error": f"获取基金数据异常: {str(e)}", "ts_code": ts_code}

    @mcp.tool(tags={"基金数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_fund_nav(
        ts_code: str = "",
        stock_code: str = "",
        code: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        market: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取基金净值时间序列（单位净值、累计净值、调整净值）

        Args:
            ts_code: 基金代码，如 '510300.SH'、'000001.OF'
            start_date: 开始日期(YYYYMMDD)
            end_date: 结束日期(YYYYMMDD)
            market: E(场内) / O(场外)，可选
        """
        try:
            if not api.is_available():
                return {"success": False, "error": "Tushare Pro not available"}

            kwargs: Dict[str, Any] = {"ts_code": ts_code}
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date
            if market:
                kwargs["market"] = market

            df = await cache.cached_call(api.pro.fund_nav, cache_type="daily", **kwargs)

            if df is None or df.empty:
                return {
                    "success": False,
                    "error": f"未找到基金 {ts_code} 的净值数据",
                    "ts_code": ts_code,
                }

            df = df.sort_values("nav_date")
            data = df.to_dict("records")

            return {
                "success": True,
                "ts_code": ts_code,
                "count": len(data),
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": f"获取基金净值异常: {str(e)}", "ts_code": ts_code}

    @mcp.tool(tags={"基金数据"}, annotations=READONLY_ANNOTATIONS)
    async def get_fund_portfolio(
        ts_code: Optional[str] = None,
        symbol: Optional[str] = None,
        ann_date: Optional[str] = None,
        period: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取基金持仓明细（季度），或反查某股票被哪些基金持有

        Args:
            ts_code: 基金代码，如 '001753.OF'（查某只基金持仓）
            symbol: 股票代码，如 '600519'（反查哪些基金持有该股）
            ann_date: 公告日期(YYYYMMDD)
            period: 报告期(YYYYMMDD)，如 '20251231' 表示2025年报
            start_date: 报告期开始(YYYYMMDD)
            end_date: 报告期结束(YYYYMMDD)
        """
        try:
            if not api.is_available():
                return {"success": False, "error": "Tushare Pro not available"}

            if not ts_code and not symbol and not ann_date and not period:
                return {
                    "success": False,
                    "error": "至少需要提供 ts_code、symbol、ann_date 或 period 之一",
                }

            kwargs: Dict[str, Any] = {}
            if ts_code:
                kwargs["ts_code"] = ts_code
            if symbol:
                kwargs["symbol"] = symbol
            if ann_date:
                kwargs["ann_date"] = ann_date
            if period:
                kwargs["period"] = period
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date

            df = await cache.cached_call(api.pro.fund_portfolio, cache_type="daily", **kwargs)

            if df is None or df.empty:
                label = ts_code or symbol or period or ann_date
                return {
                    "success": False,
                    "error": f"未找到 {label} 的持仓数据",
                }

            # 按持仓市值降序
            if "mkv" in df.columns:
                df = df.sort_values("mkv", ascending=False)

            data = df.to_dict("records")

            return {
                "success": True,
                "query": {"ts_code": ts_code, "symbol": symbol, "period": period},
                "count": len(data),
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": f"获取基金持仓异常: {str(e)}"}
