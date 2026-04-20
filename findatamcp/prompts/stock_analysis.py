"""股票分析提示模板

提供股票分析相关的提示模板：
- analyze_stock: 股票分析提示模板
- compare_stocks: 对比分析两只股票
- analyze_sector: 行业分析提示模板
- research_fund: 基金研究提示模板
"""

from fastmcp import FastMCP


def register_stock_prompts(mcp: FastMCP):
    """注册股票分析提示模板"""

    @mcp.prompt()
    async def analyze_stock(stock_name: str, analysis_type: str = "comprehensive"):
        """
        股票分析提示模板

        Args:
            stock_name: 股票名称或代码
            analysis_type: 分析类型（comprehensive=综合, technical=技术, fundamental=基本面）
        """
        if analysis_type == "comprehensive":
            return f"""请对{stock_name}进行全面的投资分析：
1. 基本面分析（财务、业务、行业地位）
2. 技术面分析（价格趋势、技术指标）
3. 估值分析（PE、PB、合理价格）
4. 风险评估
5. 投资建议"""
        elif analysis_type == "technical":
            return f"""请对{stock_name}进行技术分析：
1. 价格走势和趋势
2. 技术指标（均线、MACD、RSI、KDJ）
3. 支撑位和压力位
4. 成交量分析
5. 技术面投资建议"""
        elif analysis_type == "fundamental":
            return f"""请对{stock_name}进行基本面分析：
1. 公司业务和竞争优势
2. 财务状况分析（利润、资产、现金流）
3. 行业地位和市场份额
4. 管理层和公司治理
5. 成长前景和投资价值"""
        else:
            return f"""请对{stock_name}进行{analysis_type}分析。"""

    @mcp.prompt()
    async def compare_stocks(stock1: str, stock2: str):
        """对比分析两只股票的提示模板"""
        return f"""请对比分析{stock1}和{stock2}：
1. 基本面对比（财务、业务）
2. 市场表现对比（股价、成交）
3. 估值对比
4. 优劣势分析
5. 投资建议（哪只更值得投资）"""

    @mcp.prompt()
    async def analyze_sector(sector: str):
        """行业分析提示模板"""
        return f"""请对{sector}行业进行深度分析：
1. 行业概况和发展趋势
2. 竞争格局和龙头公司
3. 投资机会
4. 风险因素
5. 投资建议"""

    @mcp.prompt()
    async def research_fund(fund_name: str):
        """基金研究提示模板"""
        return f"""请对{fund_name}进行全面研究：
1. 基金基本信息和策略
2. 业绩表现和收益率
3. 投资组合和持仓
4. 风险评估
5. 投资建议"""