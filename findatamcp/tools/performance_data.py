"""业绩数据工具

提供股票业绩数据相关的MCP工具，包括：
- get_forecast: 获取业绩预告
- get_express: 获取业绩快报
"""

from typing import Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP

from ..utils.tushare_api import TushareAPI


def register_performance_tools(mcp: FastMCP, api: TushareAPI):
    """注册业绩数据工具"""

    @mcp.tool(tags={"财务数据"})
    async def get_forecast(
        ts_code: str = "",
        stock_code: str = "",
        code: str = "",
        year: Optional[str] = None,
    ) -> Dict[str, Any]:
        """【业绩预告】获取 A 股业绩预告（预增/预减/扭亏/首亏），披露财报前的盈利信号

        Args:
            ts_code: 股票代码，支持 '600519.SH' 或 '600519'（自动补全后缀）
            year: 年份，例如 '2024'，不传则获取最新

        Returns:
            type/p_change_min/p_change_max/net_profit_min/net_profit_max/summary: 业绩预告字段
        """
        try:
            # 兼容旧参数名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            # 如果没有指定年份，获取最近一年的数据
            if not year:
                current_year = datetime.now().year
                year = str(current_year)

            df = api.pro.forecast(ts_code=ts_code, end_date=f"{year}1231")

            if df.empty:
                return {"success": False, "error": "未找到业绩预告数据", "ts_code": ts_code, "year": year}

            # 转换为列表
            data = df.to_dict('records')

            return {
                "success": True,
                "ts_code": ts_code,
                "year": year,
                "count": len(data),
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取业绩预告数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"财务数据"})
    async def get_express(
        ts_code: str = "",
        stock_code: str = "",
        code: str = "",
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """【业绩快报】获取 A 股业绩快报数据（正式财报披露前的核心利润表速报）

        Args:
            ts_code: 股票代码，支持 '600519.SH' 或 '600519'（自动补全后缀）
            period: 报告期(YYYYMMDD)，例如 '20231231'，不传则获取最新

        Returns:
            revenue/operate_profit/total_profit/n_income/total_assets/roe/eps/bps: 业绩快报字段
        """
        try:
            # 兼容旧参数名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            if period:
                df = api.pro.express(ts_code=ts_code, period=period)
            else:
                df = api.pro.express(ts_code=ts_code)

            if df.empty:
                return {"success": False, "error": "未找到业绩快报数据", "ts_code": ts_code}

            # 获取最新一条
            data = df.iloc[0].to_dict()

            return {
                "success": True,
                "ts_code": ts_code,
                "period": data.get('end_date', period),
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取业绩快报数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }
