#!/usr/bin/env python3
"""
Tushare MCP Server - HTTP模式
基于fastmcp实现的HTTP MCP服务器，提供tushare数据查询和金融实体搜索功能

特点：
- ✅ 完全独立，无外部代码依赖
- ✅ 集成Tushare Pro API数据查询
- ✅ 集成本地金融实体数据库（全部A股+基金）
- ✅ 支持MCP Tools和Resources
- ✅ HTTP SSE传输，可被任何MCP客户端调用

运行方式：
    python tushare_server.py --port 8006
    
环境变量：
    TUSHARE_TOKEN - Tushare Pro API Token（必需）
    BACKEND_API_URL - 后端API地址（默认 http://localhost:8089）
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
import argparse

# ✅ 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    # 加载当前目录下的 .env 文件
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger_early = logging.getLogger("tushare_server")
        # logger_early.info(f"✅ 已加载环境变量文件: {env_path}")
except ImportError:
    # 如果没有安装 python-dotenv，从系统环境变量读取
    pass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("tushare_server")

try:
    from fastmcp import FastMCP
    import uvicorn
    import httpx
except ImportError:
    print("❌ Required packages not installed. Please run:", file=sys.stderr)
    print("   pip install fastmcp uvicorn httpx", file=sys.stderr)
    sys.exit(1)

# 导入tushare和相关依赖
try:
    import tushare as ts
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
except ImportError as e:
    print(f"❌ Failed to import required packages: {e}", file=sys.stderr)
    print(f"   Please run: pip install tushare pandas numpy", file=sys.stderr)
    sys.exit(1)

# ==================== 性能优化：异步包装器与缓存 ====================

# 简单的内存缓存（生产环境建议使用 Redis）
_memory_cache: Dict[str, Dict[str, Any]] = {}
_cache_ttl = {
    "realtime": 60,      # 实时数据缓存1分钟
    "daily": 3600,       # 日线数据缓存1小时
    "financial": 86400,  # 财务数据缓存24小时
    "basic": 86400       # 基础信息缓存24小时
}


async def cached_tushare_call(func: Callable, cache_type: str = "daily", *args, **kwargs) -> Any:
    """
    异步执行 Tushare 调用并缓存结果
    
    关键优化：使用 asyncio.to_thread 避免阻塞事件循环
    
    Args:
        func: Tushare API 函数（同步）
        cache_type: 缓存类型（realtime/daily/financial/basic）
        *args, **kwargs: 传递给 func 的参数
    """
    # 生成缓存键（处理 partial 对象和普通函数）
    try:
        func_name = func.__name__
    except AttributeError:
        # 处理 functools.partial 对象或其他没有 __name__ 的可调用对象
        func_name = getattr(func, 'func', func).__name__ if hasattr(getattr(func, 'func', None), '__name__') else str(func)
    
    cache_key = f"{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
    
    # 检查缓存
    if cache_key in _memory_cache:
        entry = _memory_cache[cache_key]
        age = (datetime.now() - entry['time']).total_seconds()
        ttl = _cache_ttl.get(cache_type, 3600)
        
        if age < ttl:
            logger.debug(f"Cache hit: {cache_key[:50]}... (age: {age:.1f}s)")
            return entry['data']
    
    # 关键优化：在线程池中执行同步的 Tushare API
    # 避免阻塞 asyncio 事件循环
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        
        # 写入缓存
        _memory_cache[cache_key] = {
            'data': result,
            'time': datetime.now()
        }
        
        logger.debug(f"Cache miss: {cache_key[:50]}... (cached for {_cache_ttl.get(cache_type, 3600)}s)")
        return result
        
    except Exception as e:
        logger.error(f"Tushare API call failed: {e}")
        raise

# 后端API地址（实际端口：8004）
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8004")

# 导入完整版TushareDataCollector
try:
    from tushare_collector_full import TushareDataCollector
    print("✅ Imported full TushareDataCollector", file=sys.stderr)
except ImportError as e:
    print(f"❌ Failed to import TushareDataCollector: {e}", file=sys.stderr)
    print("   Using fallback minimal version", file=sys.stderr)
    
    # Fallback: 最小版本
    class TushareDataCollector:
        def __init__(self, token: Optional[str] = None):
            self.token = token or os.getenv('TUSHARE_TOKEN')
            self.pro = None
            if self.token:
                try:
                    ts.set_token(self.token)
                    self.pro = ts.pro_api(self.token)
                except Exception as e:
                    print(f"❌ Tushare init failed: {e}", file=sys.stderr)
        
        def _normalize_stock_code(self, code: str) -> str:
            if '.' in code:
                return code
            return f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        
        async def collect_comprehensive_data(self, stock_code: str) -> Dict[str, Any]:
            return {"error": "TushareDataCollector not fully loaded"}

# 创建MCP服务器实例
mcp = FastMCP("tushare-data", dependencies=["tushare", "pandas", "numpy", "httpx"])

# ==================== MCP Resources ====================
# 提供金融实体数据作为可读取的资源

@mcp.resource("entity://stats")
async def get_entity_stats_resource() -> str:
    """
    金融实体统计信息（作为Resource）
    
    提供股票、基金的数量统计等信息
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BACKEND_API_URL}/api/entities/stats")
            
            if response.status_code == 200:
                stats = response.json()
                return json.dumps({
                    "uri": "entity://stats",
                    "mimeType": "application/json",
                    "description": "金融实体统计信息",
                    "data": stats
                }, ensure_ascii=False, indent=2)
            else:
                return json.dumps({"error": "无法获取统计信息"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("entity://search/{query}")
async def search_entity_resource(query: str) -> str:
    """
    搜索金融实体（动态Resource）
    
    示例：
    - entity://search/贵州茅台 → 查询贵州茅台的代码
    - entity://search/平安银行 → 查询平安银行的代码  
    - entity://search/payh → 拼音搜索
    
    LLM可以通过读取这个Resource来查找股票代码
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
                
                result_lines = [f"搜索'{query}'的结果：\n"]
                for entity in entities:
                    result_lines.append(f"- {entity['name']} ({entity['code']})")
                    result_lines.append(f"  类型：{'股票' if entity['entity_type']=='stock' else '基金'}")
                    if entity.get('pinyin_initials'):
                        result_lines.append(f"  拼音：{entity['pinyin_initials']}")
                    result_lines.append("")
                
                return "\n".join(result_lines)
            else:
                return f"查询失败: HTTP {response.status_code}"
    except Exception as e:
        return f"查询异常: {str(e)}"


@mcp.resource("entity://code/{name}")
async def get_code_by_name_resource(name: str) -> str:
    """
    根据名称查询代码（动态Resource）
    
    示例：
    - entity://code/贵州茅台 → 600519.SH
    - entity://code/平安银行 → 000001.SZ
    
    这是一个便捷的Resource，LLM可以快速查询"贵州茅台的代码是多少"
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
                return f"查询失败: HTTP {response.status_code}"
    except Exception as e:
        return f"查询异常: {str(e)}"


@mcp.resource("entity://markets")
async def get_markets_info_resource() -> str:
    """
    市场信息（作为Resource）
    
    提供可用的市场列表和说明
    """
    markets_info = {
        "uri": "entity://markets",
        "mimeType": "application/json",
        "description": "中国证券市场信息",
        "markets": [
            {
                "code": "SH",
                "name": "上海证券交易所",
                "description": "主板、科创板",
                "stock_prefix": "6"
            },
            {
                "code": "SZ",
                "name": "深圳证券交易所",
                "description": "主板、中小板、创业板",
                "stock_prefix": "0, 2, 3"
            },
            {
                "code": "BJ",
                "name": "北京证券交易所",
                "description": "北交所",
                "stock_prefix": "4, 8"
            },
            {
                "code": "OF",
                "name": "场外基金",
                "description": "开放式基金"
            }
        ]
    }
    return json.dumps(markets_info, ensure_ascii=False, indent=2)


# ==================== MCP Prompts ====================
# 提供可重用的提示模板

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
5. 短期操作建议"""
    elif analysis_type == "fundamental":
        return f"""请对{stock_name}进行基本面分析：
1. 公司业务和竞争力
2. 财务数据分析
3. 行业分析和地位
4. 成长性评估
5. 估值评估"""
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

# 全局tushare数据收集器实例
_collector: Optional[TushareDataCollector] = None


def get_collector() -> TushareDataCollector:
    """获取全局tushare数据收集器实例"""
    global _collector
    if _collector is None:
        _collector = TushareDataCollector()
    return _collector


@mcp.tool()
async def get_stock_data(ts_code: str, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取股票的综合数据（实时行情、历史数据、财务指标）

    Args:
        ts_code: Tushare股票代码，例如 '600519.SH', '000001.SZ'
                也支持 '600519', '000001'（自动补全后缀）
        stock_code: (废弃) 旧参数名，请使用 ts_code

    Returns:
        包含股票综合数据的字典，包括：
        - realtime_data: 实时行情数据
        - daily_data: 历史数据统计
        - financial_data: 核心财务指标
        - basic_info: 股票基本信息

    Examples:
        >>> result = await get_stock_data("000001.SZ")
        >>> print(result["data"]["realtime_data"]["price"])
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code

        collector = get_collector()
        data = await collector.collect_comprehensive_data(ts_code)

        if data and not data.get("error"):
            return {
                "success": True,
                "ts_code": ts_code,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        else:
            error_msg = data.get("error", "数据收集失败") if data else "数据收集返回空结果"
            return {
                "success": False,
                "error": error_msg,
                "ts_code": ts_code
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取股票数据异常: {str(e)}",
            "ts_code": ts_code if 'ts_code' in locals() else None
        }


@mcp.tool()
async def get_realtime_price(ts_code: str, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取股票实时行情数据（已优化：非阻塞调用）

    Args:
        ts_code: Tushare股票代码，例如 '600519.SH', '000001.SZ'
                也支持 '600519', '000001'（自动补全后缀）
        stock_code: (废弃) 旧参数名，请使用 ts_code

    Returns:
        实时行情数据，包括：
        - price: 当前价格
        - change: 涨跌额
        - changepercent: 涨跌幅
        - volume: 成交量
        - amount: 成交额

    Examples:
        >>> result = await get_realtime_price("600036.SH")
        >>> print(f"招商银行当前价格: {result['realtime_data']['price']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code

        collector = get_collector()

        # 标准化股票代码
        code = ts_code.strip()
        if '.' not in code:
            ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        else:
            ts_code = code
        
        # 获取最新一日数据作为实时数据（使用异步包装器）
        if collector.pro:
            df = await cached_tushare_call(
                collector.pro.daily,
                cache_type="realtime",
                ts_code=ts_code,
                limit=1
            )
            if not df.empty:
                latest = df.iloc[0].to_dict()
                realtime_data = {
                    "price": latest.get('close'),
                    "changepercent": latest.get('pct_chg'),
                    "open": latest.get('open'),
                    "high": latest.get('high'),
                    "low": latest.get('low'),
                    "pre_close": latest.get('pre_close'),
                    "volume": latest.get('vol'),
                    "amount": latest.get('amount'),
                    "trade_date": latest.get('trade_date')
                }
            else:
                realtime_data = {"error": "无最新数据"}
        else:
            realtime_data = {"error": "Tushare Pro not available"}
        
        if realtime_data and not realtime_data.get("error"):
            return {
                "success": True,
                "ts_code": ts_code,
                "realtime_data": realtime_data,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": realtime_data.get("error", "无法获取实时数据"),
                "ts_code": ts_code
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取实时行情异常: {str(e)}",
            "ts_code": ts_code
        }


@mcp.tool()
async def get_historical_data(ts_code: str, days: int = 60, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取股票历史行情数据和统计指标
    
    Args:
        stock_code: 股票代码
        days: 获取的天数，默认60天（可选：30, 60, 90, 250）
        
    Returns:
        历史数据统计，包括：
        - price_statistics: 价格统计（最高价、最低价、波动率等）
        - trend_statistics: 趋势统计（近期涨跌幅）
        - data_count: 数据条数
        
    Examples:
        >>> result = await get_historical_data("000001", days=90)
        >>> stats = result["daily_data"]["price_statistics"]
        >>> print(f"90天最高价: {stats['max_price']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code

        collector = get_collector()

        # 标准化股票代码
        code = ts_code.strip()
        if '.' not in code:
            ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

        # 获取历史数据（使用异步包装器）
        if collector.pro:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            df = await cached_tushare_call(
                collector.pro.daily,
                cache_type="daily",
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if not df.empty:
                df = df.sort_values('trade_date')
                
                # 计算统计指标
                daily_data = {
                    "data_count": len(df),
                    "start_date": start_date,
                    "end_date": end_date,
                    "price_statistics": {
                        "max_price": float(df['high'].max()),
                        "min_price": float(df['low'].min()),
                        "avg_price": float(df['close'].mean()),
                        "price_volatility": float(df['pct_chg'].std()) if len(df) > 1 else 0,
                        "max_single_day_gain": float(df['pct_chg'].max()),
                        "max_single_day_loss": float(df['pct_chg'].min())
                    },
                    "trend_statistics": {
                        "total_change": float(((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100) if len(df) > 0 else 0
                    }
                }
            else:
                daily_data = {"error": "无历史数据"}
        else:
            daily_data = {"error": "Tushare Pro not available"}
        
        if daily_data and not daily_data.get("error"):
            return {
                "success": True,
                "ts_code": ts_code,
                "daily_data": daily_data,
                "days": days,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": daily_data.get("error", "无法获取历史数据"),
                "ts_code": ts_code
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取历史数据异常: {str(e)}",
            "ts_code": ts_code
        }


@mcp.tool()
async def get_financial_indicators(ts_code: str, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取股票核心财务指标

    Args:
        ts_code: Tushare股票代码，例如 '600519.SH', '000001.SZ'
                也支持 '600519', '000001'（自动补全后缀）
        stock_code: (废弃) 旧参数名，请使用 ts_code

    Returns:
        财务指标数据，包括：
        - income_core: 核心利润表数据（营收、净利润）
        - balance_core: 核心资产负债表数据（总资产、净资产）

    Examples:
        >>> result = await get_financial_indicators("600036.SH")
        >>> income = result["financial_data"]["income_core"]
        >>> print(f"营业收入: {income['total_revenue']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code

        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        financial_data = await collector._get_simplified_financial_data(ts_code)
        
        if financial_data and not financial_data.get("error"):
            return {
                "success": True,
                "ts_code": ts_code,
                "financial_data": financial_data,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": financial_data.get("error", "无法获取财务数据"),
                "ts_code": ts_code
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取财务指标异常: {str(e)}",
            "ts_code": ts_code
        }


@mcp.tool()
async def get_basic_info(ts_code: str, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取股票基本信息

    Args:
        ts_code: Tushare股票代码，例如 '600519.SH', '000001.SZ'
                也支持 '600519', '000001'（自动补全后缀）
        stock_code: (废弃) 旧参数名，请使用 ts_code

    Returns:
        股票基本信息，包括：
        - name: 股票名称
        - industry: 所属行业
        - area: 地域
        - market: 市场类型
        - list_date: 上市日期

    Examples:
        >>> result = await get_basic_info("000001.SZ")
        >>> info = result["basic_info"]
        >>> print(f"{info['name']} - {info['industry']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code

        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        basic_info = await collector._get_basic_info(ts_code)
        
        if basic_info and not basic_info.get("error"):
            return {
                "success": True,
                "ts_code": ts_code,
                "basic_info": basic_info,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": basic_info.get("error", "无法获取基本信息"),
                "ts_code": ts_code
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取基本信息异常: {str(e)}",
            "ts_code": ts_code
        }


@mcp.tool()
async def search_financial_entity(
    keyword: str,
    entity_type: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    搜索金融实体（股票、基金）- 使用本地数据库
    
    支持多种搜索方式：
    - 拼音首字母：payh -> 平安银行
    - 股票代码：000001 -> 平安银行
    - 名称搜索：平安 -> 平安银行、平安保险等
    
    Args:
        keyword: 搜索关键词（支持拼音首字母、代码、名称）
        entity_type: 实体类型（stock=股票, fund=基金），可选
        market: 市场筛选（SH=上海, SZ=深圳, BJ=北京, OF=场外），可选
        limit: 返回数量，默认10，最大100
        
    Returns:
        包含实体列表的字典，每个实体包含：
        - code: 实体代码（如 000001.SZ）
        - name: 实体名称（如 平安银行）
        - entity_type: 实体类型（stock/fund）
        - market: 市场代码
        - pinyin_initials: 拼音首字母
        
    Examples:
        >>> # 按名称搜索
        >>> result = await search_financial_entity("平安")
        >>> # 按拼音首字母搜索
        >>> result = await search_financial_entity("payh")
        >>> # 只搜索股票
        >>> result = await search_financial_entity("银行", entity_type="stock")
        >>> # 只搜索沪市股票
        >>> result = await search_financial_entity("科技", entity_type="stock", market="SH")
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            params = {
                "q": keyword,
                "limit": min(limit, 100)  # 限制最大值
            }
            if entity_type:
                params["entity_type"] = entity_type
            if market:
                params["market"] = market
            
            response = await client.get(
                f"{BACKEND_API_URL}/api/entities/search",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "total": data.get("total", 0),
                    "entities": data.get("entities", []),
                    "query": keyword,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": f"API返回错误: {response.status_code}",
                    "keyword": keyword
                }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "请求超时，后端服务可能未启动",
            "keyword": keyword
        }
    except httpx.ConnectError:
        return {
            "success": False,
            "error": f"无法连接到后端服务: {BACKEND_API_URL}",
            "keyword": keyword
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"搜索异常: {str(e)}",
            "keyword": keyword
        }


@mcp.tool()
async def get_entity_by_code(code: str) -> Dict[str, Any]:
    """
    根据代码精确查询金融实体
    
    Args:
        code: 实体代码（支持带后缀如 000001.SZ 或不带后缀如 000001）
        
    Returns:
        实体详细信息，包含：
        - code: 完整代码
        - name: 实体名称
        - entity_type: 类型（stock/fund）
        - market: 市场
        - pinyin_full: 完整拼音
        - pinyin_initials: 拼音首字母
        
    Examples:
        >>> result = await get_entity_by_code("000001.SZ")
        >>> print(result["entity"]["name"])  # 平安银行
        >>> result = await get_entity_by_code("000001")  # 自动添加后缀
    """
    try:
        # 标准化代码格式
        search_code = code
        if '.' not in code:
            # 自动添加市场后缀
            if code.startswith('6'):
                search_code = f"{code}.SH"
            elif code.startswith('8') or code.startswith('4'):
                search_code = f"{code}.BJ"
            else:
                search_code = f"{code}.SZ"
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{BACKEND_API_URL}/api/entities/by-code/{search_code}"
            )
            
            if response.status_code == 200:
                entity = response.json()
                return {
                    "success": True,
                    "entity": entity,
                    "timestamp": datetime.now().isoformat()
                }
            elif response.status_code == 404:
                return {
                    "success": False,
                    "error": f"未找到代码为 {search_code} 的实体",
                    "code": code
                }
            else:
                return {
                    "success": False,
                    "error": f"查询失败: {response.status_code}",
                    "code": code
                }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "请求超时，后端服务可能未启动",
            "code": code
        }
    except httpx.ConnectError:
        return {
            "success": False,
            "error": f"无法连接到后端服务: {BACKEND_API_URL}",
            "code": code
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"查询异常: {str(e)}",
            "code": code
        }


@mcp.tool()
async def search_stocks(keyword: str, limit: int = 10) -> Dict[str, Any]:
    """
    搜索股票（根据名称或代码）
    
    Args:
        keyword: 搜索关键词（股票名称或代码）
        limit: 返回结果数量限制，默认10
        
    Returns:
        匹配的股票列表
        
    Examples:
        >>> result = await search_stocks("银行", limit=5)
        >>> for stock in result["stocks"]:
        ...     print(f"{stock['name']} ({stock['symbol']})")
    """
    try:
        collector = get_collector()
        
        # 如果有pro接口，使用stock_basic进行搜索
        if collector.pro:
            # 按名称或代码搜索
            df = collector.pro.stock_basic(
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market'
            )
            
            if not df.empty:
                # 过滤包含关键词的股票
                keyword_lower = keyword.lower()
                matched = df[
                    df['name'].str.contains(keyword, case=False, na=False) |
                    df['symbol'].str.contains(keyword, case=False, na=False) |
                    df['ts_code'].str.contains(keyword, case=False, na=False)
                ]
                
                results = matched.head(limit).to_dict('records')
                
                return {
                    "success": True,
                    "keyword": keyword,
                    "count": len(results),
                    "stocks": results,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "未找到匹配的股票",
                    "keyword": keyword
                }
        else:
            return {
                "success": False,
                "error": "需要Tushare Pro权限",
                "keyword": keyword
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"搜索股票异常: {str(e)}",
            "keyword": keyword
        }


@mcp.tool()
async def calculate_metrics(stock_codes: List[str], start_date: str, end_date: str, metric: str = "close") -> Dict[str, Any]:
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
    try:
        collector = get_collector()
        if not collector.pro:
             return {"success": False, "error": "Tushare Pro not available"}
        
        # 优化：一次性获取所有股票数据
        ts_codes_str = ",".join([collector._normalize_stock_code(c) for c in stock_codes])
        
        df_all = collector.pro.daily(ts_code=ts_codes_str, start_date=start_date, end_date=end_date)
        
        if df_all.empty:
             return {"success": False, "error": "未获取到数据"}

        # 透视表：行=日期，列=股票代码，值=metric
        pivot_df = df_all.pivot(index='trade_date', columns='ts_code', values=metric)
        
        # 按日期排序（Tushare返回可能是倒序）
        pivot_df = pivot_df.sort_index()
        
        if pivot_df.empty:
             return {"success": False, "error": "数据透视后为空"}

        # 计算相关系数矩阵
        corr_matrix = pivot_df.corr()
        
        # 转换为 Markdown 表格
        markdown_table = corr_matrix.to_markdown()
        
        return {
            "success": True,
            "type": "text", 
            "content": f"## 股价相关性矩阵 ({metric}, {start_date}-{end_date})\n\n{markdown_table}",
            "correlation_matrix": corr_matrix.to_dict(),
            "stock_count": len(pivot_df.columns),
            "date_range": f"{pivot_df.index[0]} - {pivot_df.index[-1]}"
        }

    except Exception as e:
        return {"success": False, "error": f"计算指标异常: {str(e)}"}


# ==================== 财务数据工具 ====================

@mcp.tool()
async def get_income_statement(ts_code: str, period: str = "20231231", report_type: str = "1", stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取利润表数据
    
    Args:
        stock_code: 股票代码，例如 '000001'、'600036'
        period: 报告期，格式 YYYYMMDD，例如 '20231231'（年报）、'20230930'（三季报）
        report_type: 报告类型，1-合并报表（默认），2-单季合并，3-调整单季合并，4-调整合并报表
        
    Returns:
        利润表数据，包括：
        - total_revenue: 营业总收入
        - revenue: 营业收入
        - operate_profit: 营业利润
        - total_profit: 利润总额
        - n_income: 净利润
        - n_income_attr_p: 归属于母公司所有者的净利润
        
    Examples:
        >>> result = await get_income_statement("600036", "20231231")
        >>> print(f"营业收入: {result['data']['revenue']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        df = await cached_tushare_call(
            collector.pro.income,
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
            "ts_code": ts_code
        }


@mcp.tool()
async def get_balance_sheet(ts_code: str, period: str = "20231231", report_type: str = "1", stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取资产负债表数据
    
    Args:
        stock_code: 股票代码
        period: 报告期，格式 YYYYMMDD
        report_type: 报告类型，1-合并报表（默认），2-单季合并，3-调整单季合并，4-调整合并报表
        
    Returns:
        资产负债表数据，包括：
        - total_assets: 资产总计
        - total_liab: 负债合计
        - total_hldr_eqy_exc_min_int: 股东权益合计（不含少数股东权益）
        - total_cur_assets: 流动资产合计
        - total_cur_liab: 流动负债合计
        
    Examples:
        >>> result = await get_balance_sheet("000001", "20231231")
        >>> print(f"总资产: {result['data']['total_assets']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        df = await cached_tushare_call(
            collector.pro.balancesheet,
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
            "ts_code": ts_code
        }


@mcp.tool()
async def get_cashflow_statement(ts_code: str, period: str = "20231231", report_type: str = "1", stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取现金流量表数据
    
    Args:
        stock_code: 股票代码
        period: 报告期，格式 YYYYMMDD
        report_type: 报告类型，1-合并报表（默认），2-单季合并，3-调整单季合并，4-调整合并报表
        
    Returns:
        现金流量表数据，包括：
        - n_cashflow_act: 经营活动产生的现金流量净额
        - n_cashflow_inv_act: 投资活动产生的现金流量净额
        - n_cash_flows_fnc_act: 筹资活动产生的现金流量净额
        - c_cash_equ_end_period: 期末现金及现金等价物余额
        
    Examples:
        >>> result = await get_cashflow_statement("600519", "20231231")
        >>> print(f"经营现金流: {result['data']['n_cashflow_act']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        df = await cached_tushare_call(
            collector.pro.cashflow,
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
            "ts_code": ts_code
        }


@mcp.tool()
async def get_financial_indicator(ts_code: str, period: str = "20231231", stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取财务指标数据（综合指标）
    
    Args:
        stock_code: 股票代码
        period: 报告期，格式 YYYYMMDD
        
    Returns:
        财务指标数据，包括：
        - roe: 净资产收益率（ROE）
        - roa: 总资产报酬率（ROA）
        - grossprofit_margin: 销售毛利率
        - netprofit_margin: 销售净利率
        - debt_to_assets: 资产负债率
        - current_ratio: 流动比率
        - quick_ratio: 速动比率
        - eps: 每股收益（EPS）
        - bps: 每股净资产（BPS）
        
    Examples:
        >>> result = await get_financial_indicator("000858", "20231231")
        >>> print(f"ROE: {result['data']['roe']}%")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        df = collector.pro.fina_indicator(ts_code=ts_code, period=period)
        
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
            "ts_code": ts_code
        }


@mcp.tool()
async def get_forecast(ts_code: str, year: Optional[str] = None, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取业绩预告数据
    
    Args:
        stock_code: 股票代码
        year: 年份，例如 '2024'，不传则获取最新
        
    Returns:
        业绩预告数据，包括：
        - type: 预告类型（预增/预减/扭亏/首亏等）
        - p_change_min: 预告净利润变动幅度下限（%）
        - p_change_max: 预告净利润变动幅度上限（%）
        - net_profit_min: 预告净利润下限（万元）
        - net_profit_max: 预告净利润上限（万元）
        - summary: 业绩预告摘要
        
    Examples:
        >>> result = await get_forecast("000001", "2024")
        >>> for item in result['data']:
        ...     print(f"{item['end_date']}: {item['type']}, 变动 {item['p_change_min']}%~{item['p_change_max']}%")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        # 如果没有指定年份，获取最近一年的数据
        if not year:
            current_year = datetime.now().year
            year = str(current_year)
        
        df = collector.pro.forecast(ts_code=ts_code, end_date=f"{year}1231")
        
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
            "ts_code": ts_code
        }


@mcp.tool()
async def get_express(ts_code: str, period: Optional[str] = None, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取业绩快报数据
    
    Args:
        stock_code: 股票代码
        period: 报告期，格式 YYYYMMDD，例如 '20231231'，不传则获取最新
        
    Returns:
        业绩快报数据，包括：
        - revenue: 营业收入（元）
        - operate_profit: 营业利润（元）
        - total_profit: 利润总额（元）
        - n_income: 净利润（元）
        - total_assets: 总资产（元）
        - total_hldr_eqy_exc_min_int: 股东权益合计（元）
        - roe: 净资产收益率（%）
        - eps: 每股收益（元）
        - bps: 每股净资产（元）
        
    Examples:
        >>> result = await get_express("600036", "20231231")
        >>> print(f"快报净利润: {result['data']['n_income']}")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        if period:
            df = collector.pro.express(ts_code=ts_code, period=period)
        else:
            df = collector.pro.express(ts_code=ts_code)
        
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
            "ts_code": ts_code
        }


# ==================== 市场数据工具 ====================

@mcp.tool()
async def get_moneyflow(ts_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None, stock_code: Optional[str] = None) -> Dict[str, Any]:
    """
    获取个股资金流向数据
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期，格式 YYYYMMDD，不传则默认最近20个交易日
        end_date: 结束日期，格式 YYYYMMDD，不传则默认今天
        
    Returns:
        资金流向数据，包括：
        - buy_sm_vol: 小单买入量（手）
        - buy_sm_amount: 小单买入金额（万元）
        - sell_sm_vol: 小单卖出量（手）
        - sell_sm_amount: 小单卖出金额（万元）
        - buy_md_vol: 中单买入量（手）
        - buy_md_amount: 中单买入金额（万元）
        - sell_md_vol: 中单卖出量（手）
        - sell_md_amount: 中单卖出金额（万元）
        - buy_lg_vol: 大单买入量（手）
        - buy_lg_amount: 大单买入金额（万元）
        - sell_lg_vol: 大单卖出量（手）
        - sell_lg_amount: 大单卖出金额（万元）
        - buy_elg_vol: 特大单买入量（手）
        - buy_elg_amount: 特大单买入金额（万元）
        - sell_elg_vol: 特大单卖出量（手）
        - sell_elg_amount: 特大单卖出金额（万元）
        - net_mf_vol: 净流入量（手）
        - net_mf_amount: 净流入额（万元）
        
    Examples:
        >>> result = await get_moneyflow("000001", "20240101", "20240131")
        >>> for item in result['data']:
        ...     print(f"{item['trade_date']}: 净流入 {item['net_mf_amount']} 万元")
    """
    try:
        # 兼容旧参数名
        if stock_code and not ts_code:
            ts_code = stock_code
        collector = get_collector()
        ts_code = collector._normalize_stock_code(ts_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        # 默认获取最近20个交易日
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
        
        df = collector.pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df.empty:
            return {"success": False, "error": "未找到资金流向数据", "ts_code": ts_code}
        
        # 按日期排序
        df = df.sort_values('trade_date')
        data = df.to_dict('records')
        
        return {
            "success": True,
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
            "count": len(data),
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取资金流向数据异常: {str(e)}",
            "ts_code": ts_code
        }


# ==================== 高级分析工具（增长与趋势）====================

@mcp.tool()
async def get_financial_metrics(
    stock_code: str,
    metrics: List[str],
    period: str = "3y",
    calc_type: str = "raw"
) -> Dict[str, Any]:
    """
    获取财务指标与增长分析（聚合工具）
    
    这是一个强大的聚合工具，不仅返回原始财务数据，还能直接计算增长率、复合增速等衍生指标。
    
    Args:
        stock_code: 股票代码
        metrics: 指标列表，支持：
            - revenue: 营业收入
            - net_profit: 净利润
            - gross_profit: 毛利润
            - operate_profit: 营业利润
            - total_assets: 总资产
            - roe: 净资产收益率
            - eps: 每股收益
        period: 时间范围，支持：
            - 1y: 最近1年（4个季度）
            - 3y: 最近3年（12个季度）
            - 5y: 最近5年（20个季度）
        calc_type: 计算类型，支持：
            - raw: 原始值
            - yoy: 同比增长率（Year-over-Year）
            - qoq: 环比增长率（Quarter-over-Quarter）
            - cagr: 复合年均增长率（Compound Annual Growth Rate）
            - ttm: 滚动12个月累计（Trailing Twelve Months）
            
    Returns:
        Markdown 格式的表格 + JSON 数据
        
    Examples:
        >>> # 查看茅台近3年营收和净利润的复合增速
        >>> result = await get_financial_metrics(
        ...     "600519", 
        ...     ["revenue", "net_profit"], 
        ...     period="3y", 
        ...     calc_type="cagr"
        ... )
    """
    try:
        collector = get_collector()
        ts_code = collector._normalize_stock_code(stock_code)
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        # 解析时间范围
        years_map = {"1y": 1, "3y": 3, "5y": 5}
        years = years_map.get(period, 3)
        
        # 获取财务指标数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=years*365+90)).strftime('%Y%m%d')
        
        df = collector.pro.fina_indicator(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            return {"success": False, "error": "未找到财务数据", "ts_code": ts_code}
        
        # 按报告期排序
        df = df.sort_values('end_date')
        
        # 指标映射
        metric_map = {
            "revenue": "revenue",
            "net_profit": "n_income",
            "gross_profit": "grossprofit",
            "operate_profit": "operate_profit",
            "total_assets": "total_assets",
            "roe": "roe",
            "eps": "eps"
        }
        
        results = {}
        
        for metric in metrics:
            col_name = metric_map.get(metric)
            if not col_name or col_name not in df.columns:
                results[metric] = {"error": f"指标 {metric} 不可用"}
                continue
            
            series = df[col_name].dropna()
            
            if calc_type == "raw":
                results[metric] = {
                    "type": "raw",
                    "data": series.tolist(),
                    "periods": df['end_date'].tolist()
                }
            
            elif calc_type == "yoy":
                # 同比增长率（需要4个季度前的数据）
                yoy = series.pct_change(periods=4) * 100
                results[metric] = {
                    "type": "yoy",
                    "data": yoy.tolist(),
                    "periods": df['end_date'].tolist(),
                    "unit": "%"
                }
            
            elif calc_type == "qoq":
                # 环比增长率
                qoq = series.pct_change() * 100
                results[metric] = {
                    "type": "qoq",
                    "data": qoq.tolist(),
                    "periods": df['end_date'].tolist(),
                    "unit": "%"
                }
            
            elif calc_type == "cagr":
                # 复合年均增长率
                if len(series) >= 2:
                    start_val = series.iloc[0]
                    end_val = series.iloc[-1]
                    n_years = len(series) / 4  # 假设季度数据
                    
                    if start_val > 0:
                        cagr = (pow(end_val / start_val, 1 / n_years) - 1) * 100
                    else:
                        cagr = None
                    
                    results[metric] = {
                        "type": "cagr",
                        "value": round(cagr, 2) if cagr else None,
                        "start_value": float(start_val),
                        "end_value": float(end_val),
                        "years": round(n_years, 1),
                        "unit": "%"
                    }
                else:
                    results[metric] = {"error": "数据不足，无法计算CAGR"}
            
            elif calc_type == "ttm":
                # 滚动12个月（4个季度）累计
                ttm = series.rolling(window=4).sum()
                results[metric] = {
                    "type": "ttm",
                    "data": ttm.tolist(),
                    "periods": df['end_date'].tolist()
                }
        
        # 生成 Markdown 表格
        if calc_type == "cagr":
            markdown_lines = ["| 指标 | 起始值 | 结束值 | 年数 | 复合增速(CAGR) |", "| :--- | :--- | :--- | :--- | :--- |"]
            for metric, data in results.items():
                if "error" not in data:
                    markdown_lines.append(
                        f"| {metric} | {data['start_value']:.2f} | {data['end_value']:.2f} | "
                        f"{data['years']:.1f} | {data['value']:.2f}% |"
                    )
        else:
            markdown_lines = [f"## {stock_code} 财务指标 ({calc_type})", ""]
            markdown_lines.append("数据已返回，请查看 JSON 格式的详细数据。")
        
        markdown_table = "\n".join(markdown_lines)
        
        return {
            "success": True,
            "ts_code": ts_code,
            "metrics": metrics,
            "period": period,
            "calc_type": calc_type,
            "results": results,
            "markdown": markdown_table,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"财务指标分析异常: {str(e)}",
            "ts_code": ts_code
        }


@mcp.tool()
async def analyze_price_correlation(
    stock_codes: List[str],
    start_date: str,
    end_date: str,
    analysis_type: str = "correlation"
) -> Dict[str, Any]:
    """
    量化分析工具（相关性、贝塔、业绩对比）
    
    专门处理多只股票的时间序列计算，自动处理数据对齐和缺失值。
    
    Args:
        stock_codes: 股票代码列表，至少2个，例如 ["600519.SH", "000858.SZ"]
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
        analysis_type: 分析类型，支持：
            - correlation: 相关性分析（Pearson相关系数）
            - beta: 贝塔系数（相对于沪深300）
            - performance_compare: 涨跌幅对比
            - volatility: 波动率分析
            - max_drawdown: 最大回撤分析
            
    Returns:
        Markdown 格式的表格 + JSON 数据
        
    Examples:
        >>> # 分析茅台和五粮液的股价相关性
        >>> result = await analyze_price_correlation(
        ...     ["600519.SH", "000858.SZ"],
        ...     "20230101",
        ...     "20231231",
        ...     "correlation"
        ... )
    """
    try:
        collector = get_collector()
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        if len(stock_codes) < 2:
            return {"success": False, "error": "至少需要2个股票代码"}
        
        # 标准化股票代码
        ts_codes = [collector._normalize_stock_code(code) for code in stock_codes]
        
        # 获取所有股票的日线数据
        ts_codes_str = ",".join(ts_codes)
        df_all = collector.pro.daily(
            ts_code=ts_codes_str,
            start_date=start_date,
            end_date=end_date
        )
        
        if df_all.empty:
            return {"success": False, "error": "未获取到价格数据"}
        
        # 透视表：行=日期，列=股票代码，值=收盘价
        pivot_df = df_all.pivot(index='trade_date', columns='ts_code', values='close')
        pivot_df = pivot_df.sort_index()
        
        # 数据对齐：前向填充缺失值（处理停牌）
        pivot_df = pivot_df.fillna(method='ffill')
        
        # 计算收益率
        returns_df = pivot_df.pct_change().dropna()
        
        results = {}
        markdown_lines = []
        
        if analysis_type == "correlation":
            # 相关性矩阵
            corr_matrix = returns_df.corr()
            
            # 转换为 Markdown 表格
            markdown_lines.append(f"## 股价相关性矩阵 ({start_date}-{end_date})")
            markdown_lines.append("")
            
            # 表头
            header = "| 股票 | " + " | ".join([code.split('.')[0] for code in corr_matrix.columns]) + " |"
            separator = "| :--- | " + " | ".join([":---:" for _ in corr_matrix.columns]) + " |"
            markdown_lines.append(header)
            markdown_lines.append(separator)
            
            # 数据行
            for idx, row in corr_matrix.iterrows():
                row_data = [f"{val:.4f}" for val in row]
                markdown_lines.append(f"| {idx.split('.')[0]} | " + " | ".join(row_data) + " |")
            
            results = {
                "correlation_matrix": corr_matrix.to_dict(),
                "interpretation": "相关系数接近1表示高度正相关，接近-1表示高度负相关，接近0表示无相关性"
            }
        
        elif analysis_type == "beta":
            # 获取沪深300指数数据作为基准
            index_df = collector.pro.index_daily(
                ts_code='000300.SH',
                start_date=start_date,
                end_date=end_date
            )
            
            if index_df.empty:
                return {"success": False, "error": "无法获取沪深300数据"}
            
            index_df = index_df.set_index('trade_date').sort_index()
            market_returns = index_df['close'].pct_change().dropna()
            
            # 对齐日期
            aligned_returns = returns_df.join(market_returns.rename('market'), how='inner')
            
            # 计算每只股票的 Beta
            betas = {}
            for code in ts_codes:
                if code in aligned_returns.columns:
                    cov = aligned_returns[code].cov(aligned_returns['market'])
                    var = aligned_returns['market'].var()
                    beta = cov / var if var != 0 else None
                    betas[code] = round(beta, 4) if beta else None
            
            markdown_lines.append(f"## 贝塔系数分析 (相对于沪深300)")
            markdown_lines.append("")
            markdown_lines.append("| 股票代码 | Beta系数 | 解读 |")
            markdown_lines.append("| :--- | :---: | :--- |")
            
            for code, beta in betas.items():
                if beta:
                    interpretation = "高弹性" if beta > 1.2 else ("低弹性" if beta < 0.8 else "中等弹性")
                    markdown_lines.append(f"| {code} | {beta:.4f} | {interpretation} |")
            
            results = {"betas": betas}
        
        elif analysis_type == "performance_compare":
            # 涨跌幅对比
            total_returns = (pivot_df.iloc[-1] / pivot_df.iloc[0] - 1) * 100
            
            markdown_lines.append(f"## 涨跌幅对比 ({start_date}-{end_date})")
            markdown_lines.append("")
            markdown_lines.append("| 股票代码 | 期初价格 | 期末价格 | 涨跌幅 | 排名 |")
            markdown_lines.append("| :--- | :---: | :---: | :---: | :---: |")
            
            sorted_returns = total_returns.sort_values(ascending=False)
            for rank, (code, ret) in enumerate(sorted_returns.items(), 1):
                start_price = pivot_df[code].iloc[0]
                end_price = pivot_df[code].iloc[-1]
                markdown_lines.append(
                    f"| {code} | {start_price:.2f} | {end_price:.2f} | "
                    f"{ret:+.2f}% | {rank} |"
                )
            
            results = {"total_returns": total_returns.to_dict()}
        
        elif analysis_type == "volatility":
            # 波动率分析（年化）
            volatilities = returns_df.std() * np.sqrt(252) * 100
            
            markdown_lines.append(f"## 波动率分析 (年化)")
            markdown_lines.append("")
            markdown_lines.append("| 股票代码 | 年化波动率 | 风险等级 |")
            markdown_lines.append("| :--- | :---: | :--- |")
            
            for code, vol in volatilities.items():
                risk_level = "高风险" if vol > 40 else ("中风险" if vol > 25 else "低风险")
                markdown_lines.append(f"| {code} | {vol:.2f}% | {risk_level} |")
            
            results = {"volatilities": volatilities.to_dict()}
        
        elif analysis_type == "max_drawdown":
            # 最大回撤
            max_drawdowns = {}
            
            for code in pivot_df.columns:
                cummax = pivot_df[code].cummax()
                drawdown = (pivot_df[code] / cummax - 1) * 100
                max_dd = drawdown.min()
                max_drawdowns[code] = round(max_dd, 2)
            
            markdown_lines.append(f"## 最大回撤分析")
            markdown_lines.append("")
            markdown_lines.append("| 股票代码 | 最大回撤 | 风险评级 |")
            markdown_lines.append("| :--- | :---: | :--- |")
            
            for code, dd in sorted(max_drawdowns.items(), key=lambda x: x[1]):
                risk = "高风险" if dd < -30 else ("中风险" if dd < -20 else "低风险")
                markdown_lines.append(f"| {code} | {dd:.2f}% | {risk} |")
            
            results = {"max_drawdowns": max_drawdowns}
        
        markdown_table = "\n".join(markdown_lines)
        
        # 构建时间序列数据用于前端图表展示
        # 格式: { "600519.SH": [{"date": "20241201", "close": 1500.0}, ...], ... }
        time_series = {}
        for code in pivot_df.columns:
            series_data = []
            for date_str, price in pivot_df[code].items():
                if pd.notna(price):
                    series_data.append({
                        "date": str(date_str),
                        "close": round(float(price), 2)
                    })
            time_series[code] = series_data
        
        return {
            "success": True,
            "stock_codes": stock_codes,
            "ts_codes": ts_codes,
            "start_date": start_date,
            "end_date": end_date,
            "analysis_type": analysis_type,
            "results": results,
            "markdown": markdown_table,
            "data_points": len(pivot_df),
            "timestamp": datetime.now().isoformat(),
            # 新增：时间序列数据，用于前端绘制股价对比图
            "time_series": time_series
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"量化分析异常: {str(e)}",
            "stock_codes": stock_codes
        }


@mcp.tool()
async def analyze_stock_performance(
    stock_codes: List[str],
    start_date: str,
    end_date: str,
    analysis_type: str = "comprehensive"
) -> Dict[str, Any]:
    """
    深度量化分析引擎（企业级）
    
    集成技术指标、风险调整收益、相关性分析的全能工具。
    
    Args:
        stock_codes: 股票代码列表，例如 ["600519.SH", "000858.SZ"]
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
        analysis_type: 分析类型，支持：
            - correlation: 相关性矩阵
            - technical: 技术指标（RSI/MACD/均线）
            - risk: 风险调整收益（Sharpe/MaxDrawdown/Sortino）
            - comprehensive: 综合报告（包含以上所有）⭐推荐
            
    Returns:
        Markdown 格式的综合报告 + JSON 数据
        
    Examples:
        >>> # 综合分析白酒三巨头
        >>> result = await analyze_stock_performance(
        ...     ["600519.SH", "000858.SZ", "000568.SZ"],
        ...     "20230101",
        ...     "20231231",
        ...     "comprehensive"
        ... )
    """
    try:
        collector = get_collector()
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro Required"}
        
        # 标准化代码
        ts_codes = [collector._normalize_stock_code(c) for c in stock_codes]
        ts_codes_str = ",".join(ts_codes)
        
        # 异步非阻塞调用（关键优化）
        df_all = await cached_tushare_call(
            collector.pro.daily,
            cache_type="daily",
            ts_code=ts_codes_str,
            start_date=start_date,
            end_date=end_date
        )
        
        if df_all.empty:
            return {"success": False, "error": "未获取到数据"}
        
        # 数据预处理
        df_all = df_all.sort_values('trade_date')
        pivot_close = df_all.pivot(index='trade_date', columns='ts_code', values='close')
        
        # 数据对齐：前向填充 + 有效性检查
        pivot_close = pivot_close.fillna(method='ffill')
        
        # 检查有效数据长度
        valid_data_ratio = pivot_close.notna().sum() / len(pivot_close)
        if (valid_data_ratio < 0.7).any():
            logger.warning(f"部分股票数据不足70%: {valid_data_ratio[valid_data_ratio < 0.7].to_dict()}")
        
        results = {}
        markdown_parts = [f"# 📊 量化分析报告", f"**分析区间**: {start_date} - {end_date}", ""]
        
        # === 1. 相关性分析 ===
        if analysis_type in ["correlation", "comprehensive"] and len(ts_codes) > 1:
            returns = pivot_close.pct_change().dropna()
            corr_matrix = returns.corr()
            
            markdown_parts.append("## 🔗 股价相关性矩阵")
            markdown_parts.append("")
            
            # 格式化表格
            header = "| 股票 | " + " | ".join([c.split('.')[0] for c in corr_matrix.columns]) + " |"
            separator = "| :--- | " + " | ".join([":---:" for _ in corr_matrix.columns]) + " |"
            markdown_parts.append(header)
            markdown_parts.append(separator)
            
            for idx, row in corr_matrix.iterrows():
                row_data = [f"{val:.3f}" for val in row]
                markdown_parts.append(f"| {idx.split('.')[0]} | " + " | ".join(row_data) + " |")
            
            markdown_parts.append("")
            results["correlation"] = corr_matrix.to_dict()
        
        # === 2. 风险调整收益（Sharpe & Sortino & Drawdown）===
        if analysis_type in ["risk", "comprehensive"]:
            returns = pivot_close.pct_change().dropna()
            
            # 年化收益
            total_ret = (pivot_close.iloc[-1] / pivot_close.iloc[0] - 1)
            trading_days = len(pivot_close)
            ann_ret = (1 + total_ret) ** (252 / trading_days) - 1
            
            # 年化波动率
            volatility = returns.std() * np.sqrt(252)
            
            # 夏普比率（假设无风险利率 2.5%）
            risk_free = 0.025
            sharpe = (ann_ret - risk_free) / volatility
            
            # Sortino 比率（只考虑下行波动）
            downside_returns = returns[returns < 0]
            downside_std = downside_returns.std() * np.sqrt(252)
            sortino = (ann_ret - risk_free) / downside_std
            
            # 最大回撤
            cummax = pivot_close.cummax()
            drawdown = (pivot_close / cummax - 1)
            max_dd = drawdown.min()
            
            # 卡玛比率（Calmar Ratio）= 年化收益 / 最大回撤
            calmar = ann_ret / abs(max_dd)
            
            markdown_parts.append("## 🛡️ 风险调整收益指标")
            markdown_parts.append("")
            markdown_parts.append("| 股票 | 年化收益 | 波动率 | 夏普比率 | Sortino | 最大回撤 | Calmar | 评级 |")
            markdown_parts.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
            
            risk_data = []
            for code in ts_codes:
                if code in sharpe.index:
                    # 综合评级
                    score = 0
                    if sharpe[code] > 1.0: score += 2
                    elif sharpe[code] > 0.5: score += 1
                    if max_dd[code] > -0.2: score += 2
                    elif max_dd[code] > -0.3: score += 1
                    if volatility[code] < 0.3: score += 1
                    
                    rating = "优秀" if score >= 5 else ("良好" if score >= 3 else "一般")
                    
                    markdown_parts.append(
                        f"| {code.split('.')[0]} | {ann_ret[code]:+.1%} | {volatility[code]:.1%} | "
                        f"{sharpe[code]:.2f} | {sortino[code]:.2f} | {max_dd[code]:.1%} | "
                        f"{calmar[code]:.2f} | {rating} |"
                    )
                    
                    risk_data.append({
                        "code": code,
                        "annual_return": float(ann_ret[code]),
                        "volatility": float(volatility[code]),
                        "sharpe": float(sharpe[code]),
                        "sortino": float(sortino[code]),
                        "max_drawdown": float(max_dd[code]),
                        "calmar": float(calmar[code]),
                        "rating": rating
                    })
            
            markdown_parts.append("")
            markdown_parts.append("**指标说明**:")
            markdown_parts.append("- 夏普比率 > 1.0: 优秀；0.5-1.0: 良好；< 0.5: 一般")
            markdown_parts.append("- Sortino 比率: 只考虑下行风险，越高越好")
            markdown_parts.append("- Calmar 比率: 收益/回撤，越高越好")
            markdown_parts.append("")
            
            results["risk_metrics"] = risk_data
        
        # === 3. 技术指标（RSI & MACD & 均线）===
        if analysis_type in ["technical", "comprehensive"]:
            tech_data = []
            markdown_parts.append("## 📈 核心技术指标（最新）")
            markdown_parts.append("")
            markdown_parts.append("| 股票 | 收盘价 | MA20 | MA60 | RSI(14) | MACD | 趋势信号 |")
            markdown_parts.append("| :--- | :---: | :---: | :---: | :---: | :--- | :--- |")
            
            for code in ts_codes:
                if code not in pivot_close.columns:
                    continue
                
                series = pivot_close[code].dropna()
                if len(series) < 60:
                    continue
                
                # 均线
                ma20 = series.rolling(window=20).mean()
                ma60 = series.rolling(window=60).mean()
                
                # RSI 计算
                delta = series.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                
                # MACD 计算
                ema12 = series.ewm(span=12, adjust=False).mean()
                ema26 = series.ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                macd_hist = macd_line - signal_line
                
                # 最新值
                curr_price = series.iloc[-1]
                curr_ma20 = ma20.iloc[-1]
                curr_ma60 = ma60.iloc[-1]
                curr_rsi = rsi.iloc[-1]
                curr_macd = macd_hist.iloc[-1]
                
                # 趋势判断
                signals = []
                if curr_price > curr_ma20 > curr_ma60:
                    signals.append("多头排列")
                elif curr_price < curr_ma20 < curr_ma60:
                    signals.append("空头排列")
                
                if curr_rsi > 70:
                    signals.append("超买")
                elif curr_rsi < 30:
                    signals.append("超卖")
                
                if curr_macd > 0:
                    macd_signal = "金叉" if macd_hist.iloc[-2] < 0 else "多头"
                else:
                    macd_signal = "死叉" if macd_hist.iloc[-2] > 0 else "空头"
                
                trend = " | ".join(signals) if signals else "震荡"
                
                markdown_parts.append(
                    f"| {code.split('.')[0]} | {curr_price:.2f} | {curr_ma20:.2f} | {curr_ma60:.2f} | "
                    f"{curr_rsi:.1f} | {macd_signal} | {trend} |"
                )
                
                tech_data.append({
                    "code": code,
                    "price": float(curr_price),
                    "ma20": float(curr_ma20),
                    "ma60": float(curr_ma60),
                    "rsi_14": float(curr_rsi),
                    "macd_signal": macd_signal,
                    "trend": trend
                })
            
            markdown_parts.append("")
            results["technical"] = tech_data
        
        markdown_table = "\n".join(markdown_parts)
        
        return {
            "success": True,
            "stock_codes": stock_codes,
            "ts_codes": ts_codes,
            "start_date": start_date,
            "end_date": end_date,
            "analysis_type": analysis_type,
            "data_points": len(pivot_close),
            "results": results,
            "markdown": markdown_table,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        import traceback
        logger.error(f"深度量化分析异常: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": f"分析异常: {str(e)}",
            "stock_codes": stock_codes,
            "trace": traceback.format_exc()
        }



@mcp.tool()
async def get_sector_top_stocks(
    sector_name: str,
    limit: int = 10,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取某行业/板块的龙头股列表（按市值排序）
    
    解决"白酒行业"、"银行板块"等语义泛化问题。
    优先使用申万行业分类（更精准），fallback到通用行业分类。
    
    优化点：
    1. 优先使用申万行业指数获取成分股（更精准）
    2. 使用asyncio.gather并发查询市值（提速10倍+）
    3. 分批执行避免触发API频控限制
    
    Args:
        sector_name: 行业名称，如 "白酒", "银行", "半导体", "新能源"
        limit: 返回数量，默认 10（建议 5-20）
        date: 指定日期（YYYYMMDD），已废弃，自动使用最新数据
        
    Returns:
        股票代码列表和名称，可直接传给 analyze_stock_performance 工具
        
    Examples:
        >>> # 获取白酒行业前10大龙头股
        >>> result = await get_sector_top_stocks("白酒", limit=10)
        >>> codes = result['codes']  # ['600519.SH', '000858.SZ', ...]
        >>> 
        >>> # 然后将 codes 传给量化分析工具
        >>> perf = await analyze_stock_performance(codes, "20230101", "20231231", "comprehensive")
    """
    try:
        collector = get_collector()
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro Required"}
        
        logger.info(f"查询行业 '{sector_name}' 的龙头股（申万分类+并发查询）")
        
        # ===== 第1步：获取行业股票列表 =====
        target_codes = []
        sector_stocks = None
        data_source = None
        
        # 方案A: 优先尝试申万行业指数（最精准）
        try:
            df_sw_index = await cached_tushare_call(
                collector.pro.index_basic,
                cache_type="basic",
                market='SW',
                fields='ts_code,name'
            )
            
            if not df_sw_index.empty:
                # 模糊匹配行业名称
                matched = df_sw_index[df_sw_index['name'].str.contains(sector_name, case=False, na=False)]
                
                if not matched.empty:
                    # 优先选择二级行业（包含"Ⅱ"），更精准
                    level2 = matched[matched['name'].str.contains('Ⅱ', na=False)]
                    index_code = level2['ts_code'].iloc[0] if not level2.empty else matched['ts_code'].iloc[0]
                    index_name = level2['name'].iloc[0] if not level2.empty else matched['name'].iloc[0]
                    
                    logger.info(f"✓ 找到申万指数: {index_name} ({index_code})")
                    
                    # 获取成分股
                    df_members = await cached_tushare_call(
                        collector.pro.index_member,
                        cache_type="basic",
                        index_code=index_code
                    )
                    
                    if not df_members.empty:
                        target_codes = df_members['con_code'].tolist()
                        data_source = f"申万指数-{index_name}"
                        logger.info(f"✓ 从申万指数获取 {len(target_codes)} 只成分股")
                        
                        # 获取股票名称等基本信息
                        df_basic = await cached_tushare_call(
                            collector.pro.stock_basic,
                            cache_type="basic",
                            exchange='',
                            list_status='L',
                            fields='ts_code,symbol,name,industry,market'
                        )
                        sector_stocks = df_basic[df_basic['ts_code'].isin(target_codes)]
        
        except Exception as e:
            logger.warning(f"申万分类查询失败: {e}，fallback到通用分类")
        
        # 方案B: Fallback到 stock_basic 的 industry 字段
        if not target_codes:
            df_basic = await cached_tushare_call(
                collector.pro.stock_basic,
                cache_type="basic",
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,industry,market'
            )
            
            if df_basic.empty:
                return {"success": False, "error": "无法获取股票基础数据"}
            
            # 模糊匹配行业名称
            sector_mask = df_basic['industry'].str.contains(sector_name, case=False, na=False)
            sector_stocks = df_basic[sector_mask]
            
            if sector_stocks.empty:
                # 在名称中搜索
                name_mask = df_basic['name'].str.contains(sector_name, case=False, na=False)
                sector_stocks = df_basic[name_mask]
                
                if sector_stocks.empty:
                    return {
                        "success": False,
                        "error": f"未找到包含 '{sector_name}' 的板块。建议：\n"
                                f"1. 尝试更通用名称（如'酒'而不是'高端白酒'）\n"
                                f"2. 标准行业名称：白酒、银行、半导体、新能源"
                    }
            
            target_codes = sector_stocks['ts_code'].tolist()
            data_source = "通用行业分类"
            logger.info(f"从通用分类找到 {len(target_codes)} 只股票")
        
        # ===== 第2步：批量获取市值数据（优化版：按日期查询）=====
        # 限制数量避免过多API调用
        if len(target_codes) > 100:
            target_codes = target_codes[:100]
            logger.warning(f"股票数量过多，限制为前100只")
        
        logger.info(f"🚀 开始批量获取 {len(target_codes)} 只股票的市值数据（优化方案：1次API调用）...")
        
        # 🔧 关键优化1：获取最新交易日期
        try:
            # 使用交易日历获取最近7天的交易日
            df_cal = await cached_tushare_call(
                collector.pro.trade_cal,
                cache_type="basic",
                exchange='SSE',
                start_date=(datetime.now() - timedelta(days=7)).strftime('%Y%m%d'),
                end_date=datetime.now().strftime('%Y%m%d')
            )
            
            # 筛选已交易的最近日期
            df_traded = df_cal[df_cal['is_open'] == 1]
            if not df_traded.empty:
                latest_trade_date = df_traded['cal_date'].iloc[-1]
            else:
                # 兜底：使用今天
                latest_trade_date = datetime.now().strftime('%Y%m%d')
            
            logger.info(f"✓ 最新交易日期: {latest_trade_date}")
            
        except Exception as e:
            logger.warning(f"获取交易日历失败: {e}，使用当前日期")
            latest_trade_date = datetime.now().strftime('%Y%m%d')
        
        # 🚀 核心优化：一次性获取某天所有股票的市值数据（而不是逐只查询）
        df_mv = None
        query_dates = []
        
        # 🔧 智能回退机制：尝试最近3个日期
        for days_back in range(0, 4):
            check_date = (datetime.strptime(latest_trade_date, '%Y%m%d') 
                         - timedelta(days=days_back)).strftime('%Y%m%d')
            query_dates.append(check_date)
            
            try:
                logger.info(f"尝试查询 {check_date} 的市值数据...")
                
                # ✨ 关键：按日期查询所有股票（1次API调用）
                df_mv_all = await cached_tushare_call(
                    collector.pro.daily_basic,
                    cache_type="daily",  # 缓存1小时
                    trade_date=check_date,
                    fields='ts_code,trade_date,total_mv,circ_mv,pe_ttm,pb'
                )
                
                if df_mv_all is not None and not df_mv_all.empty:
                    # 筛选目标股票（本地操作，不消耗API）
                    df_mv = df_mv_all[df_mv_all['ts_code'].isin(target_codes)].copy()
                    
                    if not df_mv.empty:
                        logger.info(f"✓ 使用 {check_date} 的数据，成功获取 {len(df_mv)} 只股票")
                        break
                    else:
                        logger.warning(f"{check_date} 数据中无目标股票")
                else:
                    logger.warning(f"{check_date} 无市值数据")
                    
            except Exception as e:
                logger.warning(f"查询 {check_date} 失败: {e}")
                continue
        
        # 🔧 增强的错误处理
        if df_mv is None or df_mv.empty:
            failed_count = len(target_codes)
            return {
                "success": False,
                "error": f"无法获取任何股票的市值数据",
                "sector": sector_name,
                "total_stocks": len(target_codes),
                "failed_count": failed_count,
                "query_dates_tried": query_dates,
                "suggestion": "可能原因：\n"
                            "1. 市场未开盘（周末/节假日）\n"
                            "2. 股票代码不正确\n"
                            "3. Tushare API 权限不足\n"
                            "建议：检查交易日历或稍后重试"
            }
        
        # 🔧 部分成功处理
        success_count = len(df_mv)
        failed_count = len(target_codes) - success_count
        
        if failed_count > 0:
            failed_codes = list(set(target_codes) - set(df_mv['ts_code'].tolist()))
            logger.warning(
                f"⚠️  部分股票无市值数据: {failed_count}/{len(target_codes)} 只失败\n"
                f"失败代码: {', '.join(failed_codes[:5])}{'...' if failed_count > 5 else ''}"
            )
        
        logger.info(f"✅ 批量查询完成: {success_count}/{len(target_codes)} 只股票有数据（仅1次API调用）")
        
        # ===== 第3步：合并排序 =====
        merged = pd.merge(sector_stocks, df_mv, on='ts_code', how='inner')
        merged = merged[merged['total_mv'].notna()]
        top_stocks = merged.sort_values('total_mv', ascending=False).head(limit)
        
        # ===== 第4步：格式化输出 =====
        result_list = []
        for _, row in top_stocks.iterrows():
            mv_yi = row['total_mv'] / 10000  # 万元 -> 亿元
            result_list.append({
                "ts_code": row['ts_code'],
                "name": row['name'],
                "industry": row.get('industry', data_source),
                "market": row['market'],
                "market_cap_billion": round(mv_yi, 2),
                "pe_ttm": round(row['pe_ttm'], 2) if pd.notna(row['pe_ttm']) else None,
                "pb": round(row['pb'], 2) if pd.notna(row['pb']) else None
            })
        
        codes_only = [item['ts_code'] for item in result_list]
        
        # 生成摘要
        if result_list:
            leader = result_list[0]
            summary = (
                f"✅ 已找到【{sector_name}】板块市值最大的前 {len(result_list)} 只股票。\n"
                f"龙头：{leader['name']} ({leader['ts_code']})，市值 {leader['market_cap_billion']} 亿元。\n"
                f"数据来源：{data_source}\n"
                f"可将 codes 列表直接传给 analyze_stock_performance 进行深度分析。"
            )
        else:
            summary = f"未找到 '{sector_name}' 板块的股票"
        
        # 生成Markdown表格
        markdown_lines = [f"## 📊 {sector_name}板块龙头股（按市值排序）", ""]
        markdown_lines.append(f"**数据来源**: {data_source}")
        markdown_lines.append("")
        markdown_lines.append("| 排名 | 股票代码 | 名称 | 市值(亿) | PE(TTM) | PB | 市场 |")
        markdown_lines.append("| :---: | :--- | :--- | :---: | :---: | :---: | :--- |")
        
        for rank, item in enumerate(result_list, 1):
            pe_str = f"{item['pe_ttm']:.1f}" if item['pe_ttm'] else "-"
            pb_str = f"{item['pb']:.2f}" if item['pb'] else "-"
            markdown_lines.append(
                f"| {rank} | {item['ts_code']} | {item['name']} | "
                f"{item['market_cap_billion']:.0f} | {pe_str} | {pb_str} | {item['market']} |"
            )
        
        markdown_table = "\n".join(markdown_lines)
        
        # 获取实际日期
        actual_dates = df_mv['trade_date'].unique()
        date_info = f"{actual_dates[-1]}" if len(actual_dates) == 1 else f"{actual_dates.min()}-{actual_dates.max()}"
        
        return {
            "success": True,
            "sector": sector_name,
            "data_source": data_source,
            "trade_date": date_info,
            "count": len(result_list),
            "total_candidates": len(target_codes),
            "success_rate": f"{len(df_mv)}/{len(target_codes)}",
            "top_stocks": result_list,
            "codes": codes_only,
            "summary": summary,
            "markdown": markdown_table,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        import traceback
        logger.error(f"板块查询异常: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": f"板块查询异常: {str(e)}",
            "sector": sector_name
        }



@mcp.tool()
async def get_top_list(trade_date: str, market_type: str = "SH") -> Dict[str, Any]:
    """
    获取龙虎榜数据
    
    Args:
        trade_date: 交易日期，格式 YYYYMMDD
        market_type: 市场类型，SH-上海，SZ-深圳，BJ-北京
        
    Returns:
        龙虎榜数据，包括：
        - ts_code: 股票代码
        - name: 股票名称
        - close: 收盘价
        - pct_chg: 涨跌幅
        - turnover_rate: 换手率
        - amount: 总成交额
        - l_sell: 龙虎榜卖出额
        - l_buy: 龙虎榜买入额
        - l_amount: 龙虎榜成交额
        - net_amount: 龙虎榜净买入
        - net_rate: 龙虎榜净买额占比
        - reason: 上榜原因
        
    Examples:
        >>> result = await get_top_list("20240115", "SH")
        >>> for item in result['data']:
        ...     print(f"{item['name']}: {item['reason']}, 净买入 {item['net_amount']} 万元")
    """
    try:
        collector = get_collector()
        
        if not collector.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        
        df = collector.pro.top_list(trade_date=trade_date)
        
        if df.empty:
            return {"success": False, "error": "未找到龙虎榜数据", "trade_date": trade_date}
        
        # 筛选市场
        if market_type:
            df = df[df['ts_code'].str.endswith(f'.{market_type}')]
        
        data = df.to_dict('records')
        
        return {
            "success": True,
            "trade_date": trade_date,
            "market_type": market_type,
            "count": len(data),
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取龙虎榜数据异常: {str(e)}",
            "trade_date": trade_date
        }


def main():
    """主函数：启动HTTP MCP服务器"""
    parser = argparse.ArgumentParser(description="Tushare MCP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8006, help="Port to bind to (default: 8006)")
    args = parser.parse_args()
    
    try:
        # 预初始化collector，检查tushare连接
        collector = get_collector()
        
        # 打印启动信息
        print("=" * 80)
        print("🚀 Tushare MCP Server Starting...")
        print(f"📊 API Status: {'Pro' if collector.pro else 'Free'}")
        print(f"🌐 HTTP Server: http://{args.host}:{args.port}")
        print(f"🔧 Tools Available: 21 (Production-Ready 企业级分析引擎 + 语义泛化)")
        print("")
        print("📈 基础行情数据:")
        print("   1. get_stock_data - 获取股票综合数据")
        print("   2. get_realtime_price - 获取实时行情")
        print("   3. get_historical_data - 获取历史数据")
        print("   4. get_basic_info - 获取基本信息")
        print("")
        print("💰 财务数据（三大报表+指标）:")
        print("   5. get_income_statement - 获取利润表 ⭐NEW")
        print("   6. get_balance_sheet - 获取资产负债表 ⭐NEW")
        print("   7. get_cashflow_statement - 获取现金流量表 ⭐NEW")
        print("   8. get_financial_indicator - 获取财务指标（ROE/ROA/毛利率等）⭐NEW")
        print("   9. get_financial_indicators - 获取核心财务指标（旧版兼容）")
        print("")
        print("📊 业绩数据:")
        print("   10. get_forecast - 获取业绩预告 ⭐NEW")
        print("   11. get_express - 获取业绩快报 ⭐NEW")
        print("")
        print("💸 市场数据:")
        print("   12. get_moneyflow - 获取个股资金流向 ⭐NEW")
        print("   13. get_top_list - 获取龙虎榜数据 ⭐NEW")
        print("")
        print("🔍 搜索与查询:")
        print("   14. search_stocks - 搜索股票（Tushare）")
        print("   15. search_financial_entity - 搜索金融实体（本地数据库）")
        print("   16. get_entity_by_code - 精确查询实体（本地数据库）")
        print("")
        print("📐 高级分析工具（企业级 Production-Ready）:")
        print("   17. get_financial_metrics - 财务指标聚合分析（支持CAGR/YoY/QoQ/TTM）⭐")
        print("   18. analyze_price_correlation - 量化分析引擎（相关性/Beta/波动率/回撤）⭐")
        print("   19. analyze_stock_performance - 深度量化分析（Sharpe/Sortino/RSI/MACD）⭐⭐")
        print("   20. get_sector_top_stocks - 行业龙头股查询（语义泛化）⭐⭐NEW")
        print("   21. calculate_metrics - 计算股票相关性矩阵（旧版兼容）")
        print("")
        print("🚀 性能优化:")
        print("   ✅ 异步非阻塞调用（避免事件循环阻塞）")
        print("   ✅ 智能缓存机制（实时数据1分钟，财务数据24小时）")
        print("   ✅ 数据对齐与清洗（自动处理停牌和缺失值）")
        print("=" * 80)
        print(f"✅ Server ready at http://{args.host}:{args.port}")
        print("")
        
        # 启动HTTP MCP服务器 - 使用 streamable-http 传输提高稳定性
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
        
    except KeyboardInterrupt:
        print("\n⚠️ Server interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

