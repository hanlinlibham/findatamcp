"""行业板块工具

提供行业板块分析相关的MCP工具，包括：
- analyze_sector: 行业板块分析（占位符）
"""

from typing import Dict, Any
from datetime import datetime
from fastmcp import FastMCP

from ..utils.tushare_api import TushareAPI


def register_sector_tools(mcp: FastMCP, api: TushareAPI):
    """注册行业板块工具"""

    @mcp.tool(tags={"行业板块"})
    async def analyze_sector(sector: str) -> Dict[str, Any]:
        """
        【行业深度】对指定行业/板块做综合分析：龙头股、估值水平、近期涨跌、资金流向

        Args:
            sector: 行业板块名称

        Returns:
            行业分析结果

        Examples:
            >>> result = await analyze_sector("白酒")
            >>> print(result["analysis"])
        """
        try:
            # 路由占位：本工具不直接产出分析，按 sector 类型给出非循环的下一步。
            # 注意 不要无脑指回 get_sector_top_stocks(sector) —— 主题/概念名(如 创新药)在板块库里查不到，会形成死循环。
            return {
                "success": True,
                "sector": sector,
                "analysis": None,
                "note": "analyze_sector 为路由占位，不直接产出分析，请按 routing 选择路径。",
                "routing": {
                    "标准行业(如 白酒/银行/半导体/新能源)": [
                        f"get_sector_top_stocks(sector_name='{sector}') 取龙头",
                        "再 get_batch_pct_chg(成分) 看涨跌 + get_stock_valuation(成分) 看估值",
                    ],
                    "主题/概念(如 创新药/AI/机器人/低空经济)": [
                        f"search_stocks(keyword='{sector}') 找对应指数代码(.CSI/.SZ)",
                        "get_index_weight(index_code) 取成分 → get_batch_pct_chg + get_stock_valuation 聚合",
                        "指数层 PE/PB：get_index_valuation 仅覆盖宽基/申万(.SI)，主题指数无直接估值，需成分聚合",
                    ],
                },
                "timestamp": str(datetime.now())
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"行业分析异常: {str(e)}",
                "sector": sector
            }
