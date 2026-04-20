"""财务数据工具

提供股票财务数据相关的MCP工具，包括：
- get_financial_indicators: 获取财务指标
- get_financial_indicator: 获取财务指标数据（ROE/ROA等）
- get_basic_info: 获取基本信息
- get_income_statement: 获取利润表
- get_balance_sheet: 获取资产负债表
- get_cashflow_statement: 获取现金流量表
"""

from typing import Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP

from ..cache import cache
from ..utils.tushare_api import TushareAPI


def register_financial_tools(mcp: FastMCP, api: TushareAPI):
    """注册财务数据工具"""

    @mcp.tool(tags={"财务数据"})
    async def get_financial_indicators(
        ts_code: str = "",
        stock_code: str = "",
        code: str = "",
    ) -> Dict[str, Any]:
        """获取股票核心财务指标（仅支持A股）

        Args:
            ts_code: A股代码，支持 '600519.SH' 或 '600519'（自动补全后缀）。也可用 stock_code 参数名

        Returns:
            income_core: 核心利润表数据（营收、净利润）
            balance_core: 核心资产负债表数据（总资产、净资产）
        """
        try:
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 财务数据仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {"success": False, "error": f"财务数据仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"}

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            financial_data = {}

            # 获取最近一年的利润表核心数据
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

            if financial_data:
                return {
                    "success": True,
                    "ts_code": ts_code,
                    "financial_data": financial_data,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "未找到财务数据",
                    "ts_code": ts_code
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取财务指标异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"财务数据"})
    async def get_basic_info(
        ts_code: str,
    ) -> Dict[str, Any]:
        """获取股票基本信息

        支持 A 股、港股、美股。

        Args:
            ts_code: 股票代码，支持 '600519.SH'、'00700.HK'(港股)、'AAPL'(美股)

        Returns:
            name/industry/area/market/list_date: 基本信息字段
        """
        try:
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            _market = api.get_market(ts_code)

            if _market == "HK":
                df = await cache.cached_call(
                    api.pro.hk_basic,
                    cache_type="basic",
                    ts_code=ts_code,
                    fields='ts_code,name,enname,market,list_status,list_date,delist_date'
                )
            elif _market == "US":
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

                # 公司详细信息仅 A 股支持
                if _market == "A":
                    company_df = await cache.cached_call(
                        api.pro.stock_company,
                        cache_type="basic",
                        ts_code=ts_code
                    )

                    if not company_df.empty:
                        company_info = company_df.iloc[0].to_dict()
                        basic_info.update({
                            'chairman': company_info.get('chairman', ''),
                            'manager': company_info.get('manager', ''),
                            'secretary': company_info.get('secretary', ''),
                            'reg_capital': company_info.get('reg_capital', ''),
                            'setup_date': company_info.get('setup_date', ''),
                            'province': company_info.get('province', ''),
                            'city': company_info.get('city', ''),
                            'introduction': company_info.get('introduction', '')
                        })

                return {
                    "success": True,
                    "ts_code": ts_code,
                    "basic_info": basic_info,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "未找到股票基本信息",
                    "ts_code": ts_code
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取基本信息异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"财务数据"})
    async def get_income_statement(
        ts_code: str = "",
        period: str = "20231231",
        report_type: str = "1",
        stock_code: str = "",
        code: str = "",
    ) -> Dict[str, Any]:
        """获取利润表数据（仅支持A股）

        【数据可用性】period 必须使用已公布的报告期（YYYYMMDD 格式）：
        - 年报(12/31): 次年4月底前披露  - 半年报(06/30): 8月底前披露
        - 一季报(03/31): 4月底前披露    - 三季报(09/30): 10月底前披露
        查询未公布的报告期会返回空数据，请勿查询未来日期。

        Args:
            ts_code: A股代码，支持 '600519.SH' 或 '600519'（自动补全后缀）。也可用 stock_code 参数名
            period: 报告期(YYYYMMDD)，如 20241231, 20240930。默认'20231231'
            report_type: 1-合并报表,2-单季合并,3-调整单季,4-调整合并

        Returns:
            total_revenue/revenue/operate_profit/total_profit/n_income: 利润表字段
        """
        try:
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 财务数据仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {"success": False, "error": f"财务数据仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"}

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            df = await cache.cached_call(
                api.pro.income,
                cache_type="financial",
                ts_code=ts_code,
                period=period,
                report_type=report_type
            )

            if df.empty:
                return {"success": False, "error": "未找到利润表数据", "ts_code": ts_code, "period": period}

            # 转换为字典
            data = df.iloc[0].to_dict()

            return {
                "success": True,
                "ts_code": ts_code,
                "period": period,
                "report_type": report_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取利润表数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"财务数据"})
    async def get_balance_sheet(
        ts_code: str = "",
        period: str = "20231231",
        report_type: str = "1",
        stock_code: str = "",
        code: str = "",
    ) -> Dict[str, Any]:
        """获取资产负债表数据（仅支持A股）

        Args:
            ts_code: A股代码，支持 '600519.SH' 或 '600519'（自动补全后缀）。也可用 stock_code 参数名
            period: 报告期(YYYYMMDD)，如 20241231, 20240930。未公布的报告期会返回空数据，默认'20231231'
            report_type: 1-合并报表,2-单季合并,3-调整单季,4-调整合并

        Returns:
            total_assets/total_liab/total_hldr_eqy_exc_min_int: 资产负债表字段
        """
        try:
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 财务数据仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {"success": False, "error": f"财务数据仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"}

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            df = await cache.cached_call(
                api.pro.balancesheet,
                cache_type="financial",
                ts_code=ts_code,
                period=period,
                report_type=report_type
            )

            if df.empty:
                return {"success": False, "error": "未找到资产负债表数据", "ts_code": ts_code, "period": period}

            data = df.iloc[0].to_dict()

            return {
                "success": True,
                "ts_code": ts_code,
                "period": period,
                "report_type": report_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取资产负债表数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"财务数据"})
    async def get_cashflow_statement(
        ts_code: str = "",
        period: str = "20231231",
        report_type: str = "1",
        stock_code: str = "",
        code: str = "",
    ) -> Dict[str, Any]:
        """获取现金流量表数据（仅支持A股）

        Args:
            ts_code: A股代码，支持 '600519.SH' 或 '600519'（自动补全后缀）。也可用 stock_code 参数名
            period: 报告期(YYYYMMDD)，如 20241231, 20240930。未公布的报告期会返回空数据，默认'20231231'
            report_type: 1-合并报表,2-单季合并,3-调整单季,4-调整合并

        Returns:
            n_cashflow_act/n_cashflow_inv_act/n_cash_flows_fnc_act: 现金流量表字段
        """
        try:
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 财务数据仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {"success": False, "error": f"财务数据仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"}

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            df = await cache.cached_call(
                api.pro.cashflow,
                cache_type="financial",
                ts_code=ts_code,
                period=period,
                report_type=report_type
            )

            if df.empty:
                return {"success": False, "error": "未找到现金流量表数据", "ts_code": ts_code, "period": period}

            data = df.iloc[0].to_dict()

            return {
                "success": True,
                "ts_code": ts_code,
                "period": period,
                "report_type": report_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取现金流量表数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }

    @mcp.tool(tags={"财务数据"})
    async def get_financial_indicator(
        ts_code: str = "",
        period: str = "20231231",
        stock_code: str = "",
        code: str = "",
    ) -> Dict[str, Any]:
        """获取财务指标数据（ROE/ROA/毛利率/净利率等，仅支持A股）

        Args:
            ts_code: A股代码，支持 '600519.SH' 或 '600519'（自动补全后缀）。也可用 stock_code 参数名
            period: 报告期(YYYYMMDD)，默认'20231231'

        Returns:
            roe/roa/grossprofit_margin/netprofit_margin/debt_to_assets/eps/bps: 财务指标字段
        """
        try:
            # 兼容参数别名
            ts_code = ts_code or stock_code or code
            if not ts_code:
                return {"success": False, "error": "请提供股票代码（参数名: ts_code, stock_code 或 code）"}
            ts_code = api.normalize_stock_code(ts_code)

            # 财务数据仅支持 A 股
            _market = api.get_market(ts_code)
            if _market != "A":
                return {"success": False, "error": f"财务数据仅支持A股，当前代码 {ts_code} 为{'港股' if _market == 'HK' else '美股'}"}

            if not api.is_available():
                return {"success": False, "error": "数据服务不可用（Pro 接口未配置）"}

            df = await cache.cached_call(
                api.pro.fina_indicator,
                cache_type="financial",
                ts_code=ts_code,
                period=period
            )

            if df.empty:
                return {"success": False, "error": "未找到财务指标数据", "ts_code": ts_code, "period": period}

            data = df.iloc[0].to_dict()

            return {
                "success": True,
                "ts_code": ts_code,
                "period": period,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取财务指标数据异常: {str(e)}",
                "ts_code": ts_code if 'ts_code' in locals() else None
            }
