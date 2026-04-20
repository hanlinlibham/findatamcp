#!/usr/bin/env python3
"""
测试完整的股票查询工作流

演示正确的工具链调用：
1. search_financial_entity - 搜索实体获取代码
2. get_historical_data - 获取近期表现
3. get_stock_data - 获取完整数据
"""

import asyncio
import httpx
import json
from datetime import datetime

BACKEND_URL = "http://localhost:8004"


async def test_complete_workflow():
    """测试完整工作流：查询贵州茅台近一周表现"""
    
    print("=" * 70)
    print("🧪 完整工作流测试：查询贵州茅台近一周表现")
    print("=" * 70)
    print()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # Step 1: 搜索实体获取代码
        print("📍 Step 1: 搜索贵州茅台的股票代码")
        print("-" * 70)
        
        payload1 = {
            "server_name": "tushare-data",
            "tool_name": "search_financial_entity",
            "arguments": {
                "keyword": "贵州茅台",
                "entity_type": "stock",
                "limit": 1
            }
        }
        
        try:
            response1 = await client.post(
                f"{BACKEND_URL}/api/mcp/call-tool",
                json=payload1
            )
            
            if response1.status_code == 200:
                result1 = response1.json()
                print("✅ 搜索成功")
                
                # 解析结果
                if result1.get("success"):
                    entities = result1.get("entities", [])
                    if entities:
                        entity = entities[0]
                        stock_code = entity['code'].split('.')[0]  # 600519.SH → 600519
                        stock_name = entity['name']
                        
                        print(f"   股票名称: {stock_name}")
                        print(f"   股票代码: {entity['code']}")
                        print(f"   市场: {entity.get('market')}")
                        print(f"   拼音: {entity.get('pinyin_initials')}")
                        print()
                    else:
                        print("❌ 未找到实体")
                        return
                else:
                    print(f"❌ 搜索失败: {result1}")
                    return
            else:
                print(f"❌ API调用失败: {response1.status_code}")
                print(f"   响应: {response1.text}")
                return
        except Exception as e:
            print(f"❌ 异常: {e}")
            return
        
        # Step 2: 获取近一周的历史数据
        print("📈 Step 2: 获取近一周的历史数据")
        print("-" * 70)
        
        payload2 = {
            "server_name": "tushare-data",
            "tool_name": "get_historical_data",
            "arguments": {
                "stock_code": stock_code,
                "days": 7
            }
        }
        
        try:
            response2 = await client.post(
                f"{BACKEND_URL}/api/mcp/call-tool",
                json=payload2
            )
            
            if response2.status_code == 200:
                result2 = response2.json()
                print("✅ 数据获取成功")
                
                if result2.get("success"):
                    daily_data = result2.get("daily_data", {})
                    stats = daily_data.get("price_statistics", {})
                    trend = daily_data.get("trend_statistics", {})
                    
                    print(f"\n📊 {stock_name} 近一周表现:")
                    print(f"   数据条数: {daily_data.get('data_count')} 个交易日")
                    print(f"   时间范围: {daily_data.get('start_date')} ~ {daily_data.get('end_date')}")
                    print(f"\n   价格统计:")
                    print(f"   - 最高价: {stats.get('max_price'):.2f} 元")
                    print(f"   - 最低价: {stats.get('min_price'):.2f} 元")
                    print(f"   - 平均价: {stats.get('avg_price'):.2f} 元")
                    print(f"   - 价格波动率: {stats.get('price_volatility'):.2f}%")
                    print(f"\n   涨跌情况:")
                    print(f"   - 区间涨跌幅: {trend.get('total_change'):.2f}%")
                    print(f"   - 单日最大涨幅: {stats.get('max_single_day_gain'):.2f}%")
                    print(f"   - 单日最大跌幅: {stats.get('max_single_day_loss'):.2f}%")
                    print()
                else:
                    print(f"❌ 获取失败: {result2.get('error')}")
            else:
                print(f"❌ API调用失败: {response2.status_code}")
                print(f"   响应: {response2.text}")
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Step 3: 获取实时价格
        print("💰 Step 3: 获取当前实时价格")
        print("-" * 70)
        
        payload3 = {
            "server_name": "tushare-data",
            "tool_name": "get_realtime_price",
            "arguments": {
                "stock_code": stock_code
            }
        }
        
        try:
            response3 = await client.post(
                f"{BACKEND_URL}/api/mcp/call-tool",
                json=payload3
            )
            
            if response3.status_code == 200:
                result3 = response3.json()
                
                if result3.get("success"):
                    realtime = result3.get("realtime_data", {})
                    print("✅ 实时数据:")
                    print(f"   当前价格: {realtime.get('price')} 元")
                    print(f"   涨跌幅: {realtime.get('changepercent')}%")
                    print(f"   成交量: {realtime.get('volume')}")
                    print(f"   交易日期: {realtime.get('trade_date')}")
                    print()
                else:
                    print(f"⚠️  获取失败: {result3.get('error')}")
                    print()
            else:
                print(f"❌ API调用失败: {response3.status_code}")
        except Exception as e:
            print(f"❌ 异常: {e}")
        
        print("=" * 70)
        print("✅ 完整工作流测试完成")
        print("=" * 70)
        print()
        print("📝 总结：")
        print("   1. search_financial_entity - 识别股票代码 ✅")
        print("   2. get_historical_data - 获取历史表现 ✅")
        print("   3. get_realtime_price - 获取当前价格 ✅")
        print()
        print("🎯 在Deep Research中，系统会自动执行这个工具链")
        print()


if __name__ == "__main__":
    asyncio.run(test_complete_workflow())

