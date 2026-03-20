"""
宏观经济数据工具

提供中国宏观经济数据查询：
- get_macro_summary: 宏观经济概览（一站式）
- get_gdp_data: GDP数据
- get_cpi_data: CPI数据
- get_ppi_data: PPI数据
- get_pmi_data: PMI数据
- get_money_supply: 货币供应量 (M0/M1/M2)
- get_shibor_rates: SHIBOR利率
- get_lpr_rates: LPR利率
"""

import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
import pandas as pd
import logging

from ..cache import cache
from ..utils.tushare_api import TushareAPI
from ..utils.response import build_success_response, build_error_response, build_meta
from ..utils.errors import ErrorCode

logger = logging.getLogger(__name__)


def register_macro_tools(mcp: FastMCP, api: TushareAPI):
    """注册宏观数据工具"""

    @mcp.tool(tags={"宏观数据"})
    async def get_macro_summary() -> Union[ToolResult, Dict[str, Any]]:
        """
        【宏观概览】一次调用获取最新的关键宏观经济指标

        ⭐ 这是了解中国宏观经济环境的首选工具

        📌 适用场景:
        - "现在的宏观经济环境怎么样"
        - "最新的GDP、CPI、PMI是多少"
        - "当前的货币政策环境"
        - "利率水平是多少"
        - 作为投资分析的宏观背景

        📌 返回的关键指标:
        - GDP: 季度同比增速
        - CPI: 月度同比（通胀水平）
        - PPI: 工业品价格同比
        - PMI: 制造业采购经理指数（50以上为扩张）
        - M2: 广义货币同比增速
        - LPR: 贷款市场报价利率

        Returns:
            {
              "success": true,
              "data": {
                "gdp": {"quarter": "2024Q4", "gdp_yoy": 5.0},
                "cpi": {"month": "202412", "yoy": 0.1},
                "ppi": {"month": "202412", "yoy": -2.3},
                "pmi": {"month": "202412", "value": 50.1},
                "money": {"month": "202412", "m2_yoy": 7.3},
                "lpr": {"date": "20241220", "1y": 3.10, "5y": 3.60}
              },
              "analysis": {
                "economic_cycle": "复苏期",
                "inflation": "低通胀",
                "monetary_policy": "宽松"
              }
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            result = {
                "gdp": None,
                "cpi": None,
                "ppi": None,
                "pmi": None,
                "money": None,
                "lpr": None,
                "shibor": None
            }

            # 并发获取所有数据
            async def fetch_gdp():
                try:
                    df = await cache.cached_call(
                        api.pro.cn_gdp,
                        cache_type="financial",
                        limit=1
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        return {
                            "quarter": row.get('quarter'),
                            "gdp": float(row.get('gdp', 0)),
                            "gdp_yoy": float(row.get('gdp_yoy', 0)),
                            "unit": "亿元"
                        }
                except Exception as e:
                    logger.warning(f"获取GDP失败: {e}")
                return None

            async def fetch_cpi():
                try:
                    df = await cache.cached_call(
                        api.pro.cn_cpi,
                        cache_type="financial",
                        limit=1
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        return {
                            "month": row.get('month'),
                            "yoy": float(row.get('nt_yoy', 0)),
                            "mom": float(row.get('nt_mom', 0)),
                            "note": "同比/环比(%)"
                        }
                except Exception as e:
                    logger.warning(f"获取CPI失败: {e}")
                return None

            async def fetch_ppi():
                try:
                    df = await cache.cached_call(
                        api.pro.cn_ppi,
                        cache_type="financial",
                        limit=1
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        return {
                            "month": row.get('month'),
                            "yoy": float(row.get('ppi_yoy', 0)),
                            "mom": float(row.get('ppi_mom', 0)),
                            "note": "工业品出厂价格同比/环比(%)"
                        }
                except Exception as e:
                    logger.warning(f"获取PPI失败: {e}")
                return None

            async def fetch_pmi():
                try:
                    df = await cache.cached_call(
                        api.pro.cn_pmi,
                        cache_type="financial",
                        limit=1
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        # PMI010000 是制造业PMI
                        pmi_value = row.get('PMI010000')
                        return {
                            "month": row.get('MONTH'),
                            "manufacturing_pmi": float(pmi_value) if pmi_value else None,
                            "interpretation": "扩张" if pmi_value and float(pmi_value) >= 50 else "收缩",
                            "note": "50以上为扩张，以下为收缩"
                        }
                except Exception as e:
                    logger.warning(f"获取PMI失败: {e}")
                return None

            async def fetch_money():
                try:
                    df = await cache.cached_call(
                        api.pro.cn_m,
                        cache_type="financial",
                        limit=1
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        return {
                            "month": row.get('month'),
                            "m0": float(row.get('m0', 0)),
                            "m0_yoy": float(row.get('m0_yoy', 0)),
                            "m1": float(row.get('m1', 0)),
                            "m1_yoy": float(row.get('m1_yoy', 0)),
                            "m2": float(row.get('m2', 0)),
                            "m2_yoy": float(row.get('m2_yoy', 0)),
                            "unit": "亿元",
                            "note": "M2同比增速是观察货币政策松紧的关键指标"
                        }
                except Exception as e:
                    logger.warning(f"获取货币供应量失败: {e}")
                return None

            async def fetch_lpr():
                try:
                    df = await cache.cached_call(
                        api.pro.shibor_lpr,
                        cache_type="daily",
                        limit=1
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        return {
                            "date": row.get('date'),
                            "lpr_1y": float(row.get('1y', 0)),
                            "lpr_5y": float(row.get('5y', 0)),
                            "note": "1年期LPR影响短期贷款，5年期影响房贷"
                        }
                except Exception as e:
                    logger.warning(f"获取LPR失败: {e}")
                return None

            # 并发执行
            tasks = [
                fetch_gdp(),
                fetch_cpi(),
                fetch_ppi(),
                fetch_pmi(),
                fetch_money(),
                fetch_lpr()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            result["gdp"] = results[0] if not isinstance(results[0], Exception) else None
            result["cpi"] = results[1] if not isinstance(results[1], Exception) else None
            result["ppi"] = results[2] if not isinstance(results[2], Exception) else None
            result["pmi"] = results[3] if not isinstance(results[3], Exception) else None
            result["money"] = results[4] if not isinstance(results[4], Exception) else None
            result["lpr"] = results[5] if not isinstance(results[5], Exception) else None

            # 生成分析摘要
            analysis = {}

            # GDP 分析
            if result["gdp"] and result["gdp"].get("gdp_yoy"):
                gdp_yoy = result["gdp"]["gdp_yoy"]
                if gdp_yoy >= 6:
                    analysis["growth"] = "高速增长"
                elif gdp_yoy >= 5:
                    analysis["growth"] = "中高速增长"
                elif gdp_yoy >= 3:
                    analysis["growth"] = "中速增长"
                else:
                    analysis["growth"] = "低速增长"

            # CPI 分析
            if result["cpi"] and result["cpi"].get("yoy") is not None:
                cpi_yoy = result["cpi"]["yoy"]
                if cpi_yoy >= 3:
                    analysis["inflation"] = "通胀压力较大"
                elif cpi_yoy >= 2:
                    analysis["inflation"] = "温和通胀"
                elif cpi_yoy >= 0:
                    analysis["inflation"] = "低通胀"
                else:
                    analysis["inflation"] = "通缩风险"

            # PMI 分析
            if result["pmi"] and result["pmi"].get("manufacturing_pmi"):
                pmi = result["pmi"]["manufacturing_pmi"]
                if pmi >= 52:
                    analysis["manufacturing"] = "制造业强劲扩张"
                elif pmi >= 50:
                    analysis["manufacturing"] = "制造业温和扩张"
                elif pmi >= 48:
                    analysis["manufacturing"] = "制造业轻微收缩"
                else:
                    analysis["manufacturing"] = "制造业明显收缩"

            # M2 分析
            if result["money"] and result["money"].get("m2_yoy"):
                m2_yoy = result["money"]["m2_yoy"]
                if m2_yoy >= 10:
                    analysis["monetary_policy"] = "货币政策宽松"
                elif m2_yoy >= 8:
                    analysis["monetary_policy"] = "货币政策适度宽松"
                elif m2_yoy >= 6:
                    analysis["monetary_policy"] = "货币政策中性"
                else:
                    analysis["monetary_policy"] = "货币政策偏紧"

            # Build concise text summary for LLM (~100 tokens)
            parts = ["宏观概览:"]
            if result.get("gdp") and result["gdp"].get("gdp_yoy"):
                parts.append(f"GDP {result['gdp']['gdp_yoy']}%({analysis.get('growth', '')})")
            if result.get("cpi") and result["cpi"].get("yoy") is not None:
                parts.append(f"CPI {result['cpi']['yoy']}%({analysis.get('inflation', '')})")
            if result.get("pmi") and result["pmi"].get("manufacturing_pmi"):
                interp = result["pmi"].get("interpretation", "")
                parts.append(f"PMI {result['pmi']['manufacturing_pmi']}({interp})")
            if result.get("money") and result["money"].get("m2_yoy"):
                policy = analysis.get("monetary_policy", "")
                parts.append(f"M2 {result['money']['m2_yoy']}%({policy})")
            if result.get("lpr"):
                lpr = result["lpr"]
                parts.append(f"LPR {lpr.get('lpr_1y', 'N/A')}/{lpr.get('lpr_5y', 'N/A')}")
            summary = " ".join(parts)

            meta = build_meta(
                data_source="tushare_pro",
                coverage=sum(1 for v in result.values() if v is not None)
            )

            structured = {
                "success": True,
                "data": result,
                "analysis": analysis,
                "meta": meta,
                "timestamp": datetime.now().isoformat()
            }

            return ToolResult(
                content=[TextContent(type="text", text=summary)],
                structured_content=structured,
            )

        except Exception as e:
            logger.error(f"❌ get_macro_summary error: {e}")
            return build_error_response(f"获取宏观数据异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"宏观数据"})
    async def get_gdp_data(
        start_q: Optional[str] = None,
        end_q: Optional[str] = None,
        limit: int = 8
    ) -> Dict[str, Any]:
        """
        【GDP数据】获取中国季度GDP及分产业数据

        📌 适用场景:
        - "今年GDP增速是多少"
        - "第三产业占比多少"
        - "GDP同比增长趋势"

        Args:
            start_q: 开始季度，如 "2023Q1"
            end_q: 结束季度，如 "2024Q4"
            limit: 返回条数，默认8条（2年数据）

        Returns:
            {
              "data": [
                {
                  "quarter": "2024Q4",
                  "gdp": 1349083.5,       # GDP总量（亿元）
                  "gdp_yoy": 5.0,         # 同比增速(%)
                  "pi": 91413.9,          # 第一产业（农业）
                  "si": 492087.1,         # 第二产业（工业）
                  "ti": 765582.5          # 第三产业（服务业）
                }
              ]
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            kwargs = {"limit": limit}
            if start_q:
                kwargs["start_q"] = start_q
            if end_q:
                kwargs["end_q"] = end_q

            df = await cache.cached_call(
                api.pro.cn_gdp,
                cache_type="financial",
                **kwargs
            )

            if df is None or df.empty:
                return build_error_response("未找到GDP数据", ErrorCode.NO_DATA)

            data = []
            for _, row in df.iterrows():
                data.append({
                    "quarter": row.get('quarter'),
                    "gdp": float(row.get('gdp', 0)),
                    "gdp_yoy": float(row.get('gdp_yoy', 0)),
                    "pi": float(row.get('pi', 0)),  # 第一产业
                    "pi_yoy": float(row.get('pi_yoy', 0)),
                    "si": float(row.get('si', 0)),  # 第二产业
                    "si_yoy": float(row.get('si_yoy', 0)),
                    "ti": float(row.get('ti', 0)),  # 第三产业
                    "ti_yoy": float(row.get('ti_yoy', 0))
                })

            return {
                "success": True,
                "data": data,
                "meta": {
                    "data_source": "tushare_pro",
                    "count": len(data),
                    "unit": "亿元",
                    "fields": {
                        "gdp": "GDP总量",
                        "pi": "第一产业（农业）",
                        "si": "第二产业（工业）",
                        "ti": "第三产业（服务业）",
                        "yoy": "同比增速(%)"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ get_gdp_data error: {e}")
            return build_error_response(f"获取GDP数据异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"宏观数据"})
    async def get_cpi_data(
        start_m: Optional[str] = None,
        end_m: Optional[str] = None,
        limit: int = 12
    ) -> Dict[str, Any]:
        """
        【CPI数据】获取中国居民消费价格指数

        CPI是衡量通货膨胀的核心指标，影响货币政策和利率走向。

        📌 适用场景:
        - "现在的通胀水平是多少"
        - "CPI同比涨幅趋势"
        - "通胀对投资的影响"

        Args:
            start_m: 开始月份，如 "202301"
            end_m: 结束月份，如 "202412"
            limit: 返回条数，默认12条

        Returns:
            {
              "data": [
                {
                  "month": "202412",
                  "cpi_yoy": 0.1,         # 全国同比(%)
                  "cpi_mom": 0.0,         # 全国环比(%)
                  "town_yoy": 0.1,        # 城镇同比
                  "rural_yoy": 0.0        # 农村同比
                }
              ]
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            kwargs = {"limit": limit}
            if start_m:
                kwargs["start_m"] = start_m
            if end_m:
                kwargs["end_m"] = end_m

            df = await cache.cached_call(
                api.pro.cn_cpi,
                cache_type="financial",
                **kwargs
            )

            if df is None or df.empty:
                return build_error_response("未找到CPI数据", ErrorCode.NO_DATA)

            data = []
            for _, row in df.iterrows():
                data.append({
                    "month": row.get('month'),
                    "cpi_yoy": float(row.get('nt_yoy', 0)),
                    "cpi_mom": float(row.get('nt_mom', 0)),
                    "cpi_accu": float(row.get('nt_accu', 0)),
                    "town_yoy": float(row.get('town_yoy', 0)),
                    "rural_yoy": float(row.get('cnt_yoy', 0))
                })

            # 添加通胀分析
            latest = data[0] if data else {}
            cpi_yoy = latest.get('cpi_yoy', 0)
            inflation_level = (
                "通缩" if cpi_yoy < 0 else
                "低通胀" if cpi_yoy < 2 else
                "温和通胀" if cpi_yoy < 3 else
                "通胀压力"
            )

            return {
                "success": True,
                "data": data,
                "analysis": {
                    "latest_yoy": cpi_yoy,
                    "inflation_level": inflation_level,
                    "target": "央行目标通常为3%左右"
                },
                "meta": {
                    "data_source": "tushare_pro",
                    "count": len(data),
                    "fields": {
                        "cpi_yoy": "同比涨幅(%)",
                        "cpi_mom": "环比涨幅(%)",
                        "cpi_accu": "累计涨幅(%)"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ get_cpi_data error: {e}")
            return build_error_response(f"获取CPI数据异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"宏观数据"})
    async def get_pmi_data(
        start_m: Optional[str] = None,
        end_m: Optional[str] = None,
        limit: int = 12
    ) -> Dict[str, Any]:
        """
        【PMI数据】获取中国采购经理指数

        PMI是经济先行指标，50为荣枯线：>50表示扩张，<50表示收缩。

        📌 适用场景:
        - "制造业景气度如何"
        - "经济是在扩张还是收缩"
        - "PMI趋势判断经济拐点"

        Args:
            start_m: 开始月份，如 "202301"
            end_m: 结束月份，如 "202412"
            limit: 返回条数，默认12条

        Returns:
            {
              "data": [
                {
                  "month": "202412",
                  "pmi": 50.1,              # 制造业PMI
                  "interpretation": "扩张", # 解读
                  "new_orders": 51.0,       # 新订单指数
                  "production": 52.0        # 生产指数
                }
              ]
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            kwargs = {"limit": limit}
            if start_m:
                kwargs["start_m"] = start_m
            if end_m:
                kwargs["end_m"] = end_m

            df = await cache.cached_call(
                api.pro.cn_pmi,
                cache_type="financial",
                **kwargs
            )

            if df is None or df.empty:
                return build_error_response("未找到PMI数据", ErrorCode.NO_DATA)

            data = []
            for _, row in df.iterrows():
                pmi_value = row.get('PMI010000')  # 制造业PMI
                pmi = float(pmi_value) if pmi_value else None

                data.append({
                    "month": row.get('MONTH'),
                    "pmi": pmi,
                    "interpretation": "扩张" if pmi and pmi >= 50 else "收缩",
                    "new_orders": float(row.get('PMI010200', 0)) if row.get('PMI010200') else None,
                    "production": float(row.get('PMI010100', 0)) if row.get('PMI010100') else None,
                    "employment": float(row.get('PMI010500', 0)) if row.get('PMI010500') else None,
                    "raw_materials": float(row.get('PMI010300', 0)) if row.get('PMI010300') else None
                })

            # 趋势分析
            if len(data) >= 3:
                recent_pmi = [d['pmi'] for d in data[:3] if d['pmi']]
                if recent_pmi:
                    trend = "上升" if recent_pmi[0] > recent_pmi[-1] else "下降" if recent_pmi[0] < recent_pmi[-1] else "持平"
                else:
                    trend = "未知"
            else:
                trend = "数据不足"

            return {
                "success": True,
                "data": data,
                "analysis": {
                    "latest_pmi": data[0]['pmi'] if data else None,
                    "trend": trend,
                    "threshold": 50,
                    "note": "PMI > 50 表示经济扩张，< 50 表示收缩"
                },
                "meta": {
                    "data_source": "tushare_pro",
                    "count": len(data),
                    "fields": {
                        "pmi": "制造业PMI",
                        "new_orders": "新订单指数",
                        "production": "生产指数",
                        "employment": "从业人员指数"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ get_pmi_data error: {e}")
            return build_error_response(f"获取PMI数据异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"宏观数据"})
    async def get_money_supply(
        start_m: Optional[str] = None,
        end_m: Optional[str] = None,
        limit: int = 12
    ) -> Dict[str, Any]:
        """
        【货币供应量】获取M0/M1/M2数据

        M2同比增速是判断货币政策松紧的关键指标。

        📌 适用场景:
        - "现在的货币政策是松还是紧"
        - "M2增速趋势"
        - "流动性分析"

        📌 指标解读:
        - M0: 流通中的现金
        - M1: M0 + 活期存款（狭义货币，反映经济活跃度）
        - M2: M1 + 定期存款等（广义货币，反映货币政策）

        Args:
            start_m: 开始月份，如 "202301"
            end_m: 结束月份，如 "202412"
            limit: 返回条数，默认12条

        Returns:
            {
              "data": [
                {
                  "month": "202412",
                  "m0": 128194.16,         # 流通中现金（亿元）
                  "m0_yoy": 13.0,          # M0同比(%)
                  "m1": 1113069.00,        # 狭义货币
                  "m1_yoy": 1.2,
                  "m2": 3135322.30,        # 广义货币
                  "m2_yoy": 7.3
                }
              ]
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            kwargs = {"limit": limit}
            if start_m:
                kwargs["start_m"] = start_m
            if end_m:
                kwargs["end_m"] = end_m

            df = await cache.cached_call(
                api.pro.cn_m,
                cache_type="financial",
                **kwargs
            )

            if df is None or df.empty:
                return build_error_response("未找到货币供应量数据", ErrorCode.NO_DATA)

            data = []
            for _, row in df.iterrows():
                data.append({
                    "month": row.get('month'),
                    "m0": float(row.get('m0', 0)),
                    "m0_yoy": float(row.get('m0_yoy', 0)),
                    "m0_mom": float(row.get('m0_mom', 0)),
                    "m1": float(row.get('m1', 0)),
                    "m1_yoy": float(row.get('m1_yoy', 0)),
                    "m1_mom": float(row.get('m1_mom', 0)),
                    "m2": float(row.get('m2', 0)),
                    "m2_yoy": float(row.get('m2_yoy', 0)),
                    "m2_mom": float(row.get('m2_mom', 0))
                })

            # 货币政策分析
            latest = data[0] if data else {}
            m2_yoy = latest.get('m2_yoy', 0)
            m1_yoy = latest.get('m1_yoy', 0)

            policy = (
                "宽松" if m2_yoy >= 10 else
                "适度宽松" if m2_yoy >= 8 else
                "中性" if m2_yoy >= 6 else
                "偏紧"
            )

            # M1-M2剪刀差分析
            scissor = m1_yoy - m2_yoy
            liquidity = (
                "流动性活跃，资金入市意愿强" if scissor > 0 else
                "流动性偏弱，资金观望为主"
            )

            return {
                "success": True,
                "data": data,
                "analysis": {
                    "m2_yoy": m2_yoy,
                    "monetary_policy": policy,
                    "m1_m2_scissor": round(scissor, 2),
                    "liquidity": liquidity,
                    "note": "M1-M2剪刀差为正表示资金活化，为负表示资金定期化"
                },
                "meta": {
                    "data_source": "tushare_pro",
                    "count": len(data),
                    "unit": "亿元",
                    "fields": {
                        "m0": "流通中现金",
                        "m1": "狭义货币（M0+活期存款）",
                        "m2": "广义货币（M1+定期存款等）",
                        "yoy": "同比增速(%)"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ get_money_supply error: {e}")
            return build_error_response(f"获取货币供应量异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"宏观数据"})
    async def get_interest_rates(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        【利率数据】获取SHIBOR和LPR利率

        📌 适用场景:
        - "现在的利率水平是多少"
        - "LPR是多少"
        - "银行间市场流动性"

        📌 指标解读:
        - SHIBOR: 银行间同业拆借利率，反映银行间流动性
        - LPR: 贷款市场报价利率，直接影响贷款利率
          - 1年期LPR: 影响企业贷款和消费贷
          - 5年期LPR: 影响房贷利率

        Args:
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            limit: 返回条数

        Returns:
            {
              "lpr": {"1y": 3.10, "5y": 3.60},
              "shibor": {"on": 1.454, "1w": 1.966, ...}
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            result = {}

            # 获取LPR
            try:
                lpr_df = await cache.cached_call(
                    api.pro.shibor_lpr,
                    cache_type="daily",
                    limit=10
                )
                if lpr_df is not None and not lpr_df.empty:
                    lpr_data = []
                    for _, row in lpr_df.iterrows():
                        lpr_data.append({
                            "date": row.get('date'),
                            "lpr_1y": float(row.get('1y', 0)),
                            "lpr_5y": float(row.get('5y', 0))
                        })
                    result["lpr"] = lpr_data
                    result["lpr_latest"] = lpr_data[0] if lpr_data else None
            except Exception as e:
                logger.warning(f"获取LPR失败: {e}")

            # 获取SHIBOR
            kwargs = {"limit": limit}
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date

            try:
                shibor_df = await cache.cached_call(
                    api.pro.shibor,
                    cache_type="daily",
                    **kwargs
                )
                if shibor_df is not None and not shibor_df.empty:
                    shibor_data = []
                    for _, row in shibor_df.head(10).iterrows():
                        shibor_data.append({
                            "date": row.get('date'),
                            "overnight": float(row.get('on', 0)),
                            "1w": float(row.get('1w', 0)),
                            "2w": float(row.get('2w', 0)),
                            "1m": float(row.get('1m', 0)),
                            "3m": float(row.get('3m', 0)),
                            "6m": float(row.get('6m', 0)),
                            "1y": float(row.get('1y', 0))
                        })
                    result["shibor"] = shibor_data
                    result["shibor_latest"] = shibor_data[0] if shibor_data else None
            except Exception as e:
                logger.warning(f"获取SHIBOR失败: {e}")

            if not result:
                return build_error_response("未获取到利率数据", ErrorCode.NO_DATA)

            return {
                "success": True,
                "data": result,
                "meta": {
                    "data_source": "tushare_pro",
                    "fields": {
                        "lpr_1y": "1年期LPR，影响短期贷款",
                        "lpr_5y": "5年期LPR，影响房贷",
                        "shibor_on": "隔夜拆借利率",
                        "shibor_1w": "1周拆借利率"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ get_interest_rates error: {e}")
            return build_error_response(f"获取利率数据异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)

    @mcp.tool(tags={"宏观数据"})
    async def get_ppi_data(
        start_m: Optional[str] = None,
        end_m: Optional[str] = None,
        limit: int = 12
    ) -> Dict[str, Any]:
        """
        【PPI数据】获取工业品出厂价格指数

        PPI反映工业品价格变化，是CPI的先行指标。

        📌 适用场景:
        - "上游工业品价格走势"
        - "PPI和CPI的剪刀差"
        - "判断企业利润空间"

        Args:
            start_m: 开始月份，如 "202301"
            end_m: 结束月份，如 "202412"
            limit: 返回条数，默认12条

        Returns:
            {
              "data": [
                {
                  "month": "202412",
                  "ppi_yoy": -2.3,         # 同比(%)
                  "ppi_mom": -0.1,         # 环比(%)
                  "production_yoy": -2.6,  # 生产资料同比
                  "consumer_yoy": -1.4     # 生活资料同比
                }
              ]
            }
        """
        try:
            if not api.is_available():
                return build_error_response("Tushare Pro 不可用", ErrorCode.PRO_REQUIRED)

            kwargs = {"limit": limit}
            if start_m:
                kwargs["start_m"] = start_m
            if end_m:
                kwargs["end_m"] = end_m

            df = await cache.cached_call(
                api.pro.cn_ppi,
                cache_type="financial",
                **kwargs
            )

            if df is None or df.empty:
                return build_error_response("未找到PPI数据", ErrorCode.NO_DATA)

            data = []
            for _, row in df.iterrows():
                data.append({
                    "month": row.get('month'),
                    "ppi_yoy": float(row.get('ppi_yoy', 0)),
                    "ppi_mom": float(row.get('ppi_mom', 0)),
                    "ppi_accu": float(row.get('ppi_accu', 0)),
                    "production_yoy": float(row.get('ppi_mp_yoy', 0)),  # 生产资料
                    "consumer_yoy": float(row.get('ppi_cg_yoy', 0))     # 生活资料
                })

            return {
                "success": True,
                "data": data,
                "analysis": {
                    "latest_yoy": data[0]['ppi_yoy'] if data else None,
                    "interpretation": "工业品价格下跌，企业面临降价压力" if data and data[0]['ppi_yoy'] < 0 else "工业品价格上涨"
                },
                "meta": {
                    "data_source": "tushare_pro",
                    "count": len(data),
                    "fields": {
                        "ppi_yoy": "工业品出厂价格同比(%)",
                        "production_yoy": "生产资料价格同比",
                        "consumer_yoy": "生活资料价格同比"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ get_ppi_data error: {e}")
            return build_error_response(f"获取PPI数据异常: {str(e)}", ErrorCode.UPSTREAM_ERROR)
