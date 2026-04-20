#!/usr/bin/env python3
"""
测试 Tushare MCP 工具

直接测试本地服务器的各个工具
"""

import asyncio
import httpx
import json
from datetime import datetime


# 配置
MCP_SERVER_URL = "http://127.0.0.1:8006"
BACKEND_API_URL = "http://localhost:8004"  # 后端实际端口


async def call_mcp_tool(tool_name: str, arguments: dict):
    """调用MCP工具"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1,
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response = await client.post(
            f"{MCP_SERVER_URL}/mcp",
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get("result", {})
        else:
            return {"error": f"HTTP {response.status_code}: {response.text}"}


async def test_list_tools():
    """测试：列出所有工具"""
    print("=" * 60)
    print("📋 测试：列出所有工具")
    print("=" * 60)
    print()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            }
            
            response = await client.post(f"{MCP_SERVER_URL}/mcp", json=payload)
            
            if response.status_code == 200:
                result = response.json()
                tools = result.get("result", {}).get("tools", [])
                
                print(f"✅ 发现 {len(tools)} 个工具:\n")
                for i, tool in enumerate(tools, 1):
                    print(f"{i}. {tool.get('name')}")
                    print(f"   描述: {tool.get('description', 'N/A')}")
                    schema = tool.get('inputSchema', {})
                    if schema:
                        props = schema.get('properties', {})
                        required = schema.get('required', [])
                        print(f"   参数: {', '.join(props.keys())}")
                        if required:
                            print(f"   必需: {', '.join(required)}")
                    print()
                
                return True
            else:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"   {response.text}")
                return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_get_basic_info():
    """测试：获取基本信息"""
    print("=" * 60)
    print("📊 测试：获取股票基本信息 (000001 平安银行)")
    print("=" * 60)
    print()
    
    try:
        result = await call_mcp_tool("get_basic_info", {"stock_code": "000001"})
        
        if result.get("success"):
            info = result.get("basic_info", {})
            print("✅ 获取成功:\n")
            print(f"   股票代码: {result.get('stock_code')}")
            print(f"   Tushare代码: {result.get('ts_code')}")
            print(f"   股票名称: {info.get('name', 'N/A')}")
            print(f"   所属行业: {info.get('industry', 'N/A')}")
            print(f"   地域: {info.get('area', 'N/A')}")
            print(f"   市场: {info.get('market', 'N/A')}")
            print(f"   上市日期: {info.get('list_date', 'N/A')}")
            print()
            return True
        else:
            print(f"❌ 调用失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_get_realtime_price():
    """测试：获取实时行情"""
    print("=" * 60)
    print("💰 测试：获取实时行情 (600036 招商银行)")
    print("=" * 60)
    print()
    
    try:
        result = await call_mcp_tool("get_realtime_price", {"stock_code": "600036"})
        
        if result.get("success"):
            data = result.get("realtime_data", {})
            print("✅ 获取成功:\n")
            print(f"   股票代码: {result.get('stock_code')}")
            print(f"   当前价格: {data.get('price', 'N/A')}")
            print(f"   涨跌幅: {data.get('changepercent', 'N/A')}%")
            print(f"   开盘价: {data.get('open', 'N/A')}")
            print(f"   最高价: {data.get('high', 'N/A')}")
            print(f"   最低价: {data.get('low', 'N/A')}")
            print(f"   成交量: {data.get('volume', 'N/A')}")
            print(f"   成交额: {data.get('amount', 'N/A')}")
            print(f"   数据日期: {data.get('trade_date', 'N/A')}")
            print(f"   数据新鲜度: {data.get('data_freshness', 'N/A')}")
            print()
            return True
        else:
            print(f"❌ 调用失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_get_stock_data():
    """测试：获取综合数据"""
    print("=" * 60)
    print("📈 测试：获取股票综合数据 (000001 平安银行)")
    print("=" * 60)
    print()
    
    try:
        result = await call_mcp_tool("get_stock_data", {"stock_code": "000001"})
        
        if result.get("success"):
            data = result.get("data", {})
            print("✅ 获取成功:\n")
            
            # 实时数据
            realtime = data.get("realtime_data", {})
            print("📊 实时行情:")
            print(f"   当前价格: {realtime.get('price', 'N/A')}")
            print(f"   涨跌幅: {realtime.get('changepercent', 'N/A')}%")
            print()
            
            # 历史数据统计
            daily = data.get("daily_data", {})
            if daily:
                stats = daily.get("price_statistics", {})
                trend = daily.get("trend_statistics", {})
                print("📈 历史数据:")
                print(f"   数据条数: {daily.get('data_count', 'N/A')}")
                if stats:
                    print(f"   最高价: {stats.get('max_price_250d', 'N/A'):.2f}")
                    print(f"   最低价: {stats.get('min_price_250d', 'N/A'):.2f}")
                    print(f"   波动率: {stats.get('price_volatility_250d', 'N/A'):.2f}%")
                if trend:
                    print(f"   近30日涨跌: {trend.get('recent_30d_change', 'N/A'):.2f}%")
                print()
            
            # 财务数据
            financial = data.get("financial_data", {})
            if financial and not financial.get("error"):
                income = financial.get("income_core", {})
                if income:
                    print("💰 财务指标:")
                    print(f"   营业收入: {income.get('total_revenue', 'N/A')}")
                    print(f"   净利润: {income.get('net_income', 'N/A')}")
                    print(f"   报告期: {income.get('end_date', 'N/A')}")
                    print()
            
            print(f"⏰ 采集时间: {data.get('collection_time', 'N/A')}")
            print(f"📡 数据源: {data.get('data_source', 'N/A')}")
            print()
            return True
        else:
            print(f"❌ 调用失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_search_stocks():
    """测试：搜索股票"""
    print("=" * 60)
    print("🔍 测试：搜索股票 (关键词: 银行)")
    print("=" * 60)
    print()
    
    try:
        result = await call_mcp_tool("search_stocks", {"keyword": "银行", "limit": 5})
        
        if result.get("success"):
            stocks = result.get("stocks", [])
            print(f"✅ 找到 {len(stocks)} 只股票:\n")
            
            for i, stock in enumerate(stocks, 1):
                print(f"{i}. {stock.get('name')} ({stock.get('symbol')})")
                print(f"   代码: {stock.get('ts_code')}")
                print(f"   行业: {stock.get('industry', 'N/A')}")
                print(f"   地域: {stock.get('area', 'N/A')}")
                print()
            
            return True
        else:
            print(f"❌ 调用失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n")
    print("🧪 Tushare MCP 工具测试套件")
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 服务器: {MCP_SERVER_URL}")
    print("\n")
    
    # 检查服务器连接
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{MCP_SERVER_URL}/health")
            if response.status_code != 200:
                print(f"❌ 无法连接到 Tushare MCP 服务器: {MCP_SERVER_URL}")
                print(f"   请先启动服务: cd /home/abmind_v01/mcp && bash start.sh")
                return
    except Exception as e:
        print(f"❌ 无法连接到 Tushare MCP 服务器: {e}")
        print(f"   请先启动服务: cd /home/abmind_v01/mcp && bash start.sh")
        return
    
    tests = [
        ("列出工具", test_list_tools),
        ("获取基本信息", test_get_basic_info),
        ("获取实时行情", test_get_realtime_price),
        ("获取综合数据", test_get_stock_data),
        ("搜索股票", test_search_stocks),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ 测试 '{name}' 异常: {e}")
            results.append((name, False))
        
        # 测试间隔
        await asyncio.sleep(1)
    
    # 打印总结
    print("=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print()
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {status} - {name}")
    
    print()
    print(f"📈 通过率: {passed}/{total} ({passed*100//total}%)")
    print()
    
    if passed == total:
        print("🎉 所有测试通过！Tushare MCP 服务器运行正常。")
    else:
        print("⚠️ 部分测试失败，请检查日志。")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

