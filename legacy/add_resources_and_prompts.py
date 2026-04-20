# 在当前tushare_server.py的基础上添加Resources和Prompts的代码片段

resources_code = '''
@mcp.resource("entity://search/{query}")
async def search_entity_resource(query: str) -> str:
    """
    搜索金融实体（作为Resource，支持动态查询）
    
    示例：
    - entity://search/贵州茅台 → 查询贵州茅台的代码
    - entity://search/平安银行 → 查询平安银行的代码
    - entity://search/payh → 拼音搜索
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{BACKEND_API_URL}/api/entities/search",
                params={"q": query, "limit": 10}
            )
            
            if response.status_code == 200:
                data = response.json()
                entities = data.get("entities", [])
                
                result_lines = [f"搜索'{query}'的结果：\\n"]
                for entity in entities:
                    result_lines.append(f"- {entity['name']} ({entity['code']})")
                    result_lines.append(f"  类型：{'股票' if entity['entity_type']=='stock' else '基金'}")
                    if entity.get('pinyin_initials'):
                        result_lines.append(f"  拼音：{entity['pinyin_initials']}")
                    result_lines.append("")
                
                return "\\n".join(result_lines)
            else:
                return f"查询失败: HTTP {response.status_code}"
    except Exception as e:
        return f"查询异常: {str(e)}"

@mcp.resource("entity://code/{name}")
async def get_code_by_name_resource(name: str) -> str:
    """
    根据名称查询代码（作为Resource）
    
    示例：
    - entity://code/贵州茅台 → 600519.SH
    - entity://code/平安银行 → 000001.SZ
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{BACKEND_API_URL}/api/entities/search",
                params={"q": name, "limit": 1}
            )
            
            if response.status_code == 200:
                data = response.json()
                entities = data.get("entities", [])
                
                if entities:
                    entity = entities[0]
                    return f"{entity['name']}的代码是：{entity['code']}"
                else:
                    return f"未找到'{name}'的信息"
            else:
                return f"查询失败"
    except Exception as e:
        return f"查询异常: {str(e)}"
'''

prompts_code = '''
@mcp.prompt()
async def analyze_stock(stock_name: str, analysis_type: str = "comprehensive"):
    """
    股票分析提示模板
    
    Args:
        stock_name: 股票名称或代码
        analysis_type: 分析类型（comprehensive=综合, technical=技术, fundamental=基本面）
    """
    if analysis_type == "comprehensive":
        return f"""请对{stock_name}进行全面的投资分析，包括：
1. 基本面分析（财务、业务、行业地位）
2. 技术面分析（价格趋势、技术指标）
3. 估值分析（PE、PB、合理价格）
4. 风险评估
5. 投资建议"""
    elif analysis_type == "technical":
        return f"""请对{stock_name}进行技术分析，包括：
1. 价格走势和趋势
2. 技术指标（均线、MACD、RSI、KDJ）
3. 支撑位和压力位
4. 成交量分析
5. 短期操作建议"""
    else:
        return f"请分析{stock_name}的投资价值"

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
2. 竞争格局
3. 投资机会和龙头股票
4. 风险因素
5. 投资建议"""
'''

print("Resources和Prompts代码已准备好")
print("\\n请在tushare_server.py的合适位置添加以上代码")
