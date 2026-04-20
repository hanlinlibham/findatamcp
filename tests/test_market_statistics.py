"""
Tushare MCP 工具优化测试

测试 P0/P1/P2 优化后的工具功能
"""

import asyncio
import sys
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.cache import cache
from src.utils.tushare_api import TushareAPI


async def test_market_summary():
    """测试用例 1: 市场均值统计"""
    print("\n" + "=" * 60)
    print("测试用例 1: get_market_summary - 全市场统计")
    print("=" * 60)

    from src.tools.market_statistics import register_market_statistics_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_market_statistics_tools(mcp, api)

    # 获取注册的工具
    tools = mcp._tool_manager._tools
    get_market_summary = tools.get("get_market_summary")

    if not get_market_summary:
        print("❌ get_market_summary 工具未注册")
        return False

    # 调用工具
    result = await get_market_summary.fn()

    if result.get("success"):
        data = result.get("data", {})
        meta = result.get("meta", {})

        print(f"✅ 调用成功")
        print(f"   交易日期: {data.get('trade_date')}")
        print(f"   股票数量: {data.get('total_stocks')}")
        print(f"   涨跌幅统计:")
        pct_stats = data.get("pct_chg_stats", {})
        print(f"     - 均值: {pct_stats.get('mean', 'N/A'):.4f}%")
        print(f"     - 中位数: {pct_stats.get('median', 'N/A'):.4f}%")
        print(f"     - 最大: {pct_stats.get('max', 'N/A'):.2f}%")
        print(f"     - 最小: {pct_stats.get('min', 'N/A'):.2f}%")
        print(f"   涨跌家数:")
        ad = data.get("advance_decline", {})
        print(f"     - 上涨: {ad.get('advance', 'N/A')} ({ad.get('advance_ratio', 'N/A')}%)")
        print(f"     - 下跌: {ad.get('decline', 'N/A')} ({ad.get('decline_ratio', 'N/A')}%)")
        print(f"   Meta 信息:")
        print(f"     - 数据源: {meta.get('data_source', 'N/A')}")
        print(f"     - 日期调整: {meta.get('date_adjusted', False)}")
        return True
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def test_market_extremes():
    """测试用例 2: 涨跌幅极值"""
    print("\n" + "=" * 60)
    print("测试用例 2: get_market_extremes - 涨跌幅极值")
    print("=" * 60)

    from src.tools.market_statistics import register_market_statistics_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_market_statistics_tools(mcp, api)

    tools = mcp._tool_manager._tools
    get_market_extremes = tools.get("get_market_extremes")

    if not get_market_extremes:
        print("❌ get_market_extremes 工具未注册")
        return False

    result = await get_market_extremes.fn(top_n=5)

    if result.get("success"):
        data = result.get("data", {})

        print(f"✅ 调用成功")
        print(f"   交易日期: {data.get('trade_date')}")
        print(f"   涨幅 Top 5:")
        for i, stock in enumerate(data.get("top_gainers", [])[:5], 1):
            print(f"     {i}. {stock.get('name')} ({stock.get('ts_code')}): {stock.get('pct_chg')}%")
        print(f"   跌幅 Top 5:")
        for i, stock in enumerate(data.get("top_losers", [])[:5], 1):
            print(f"     {i}. {stock.get('name')} ({stock.get('ts_code')}): {stock.get('pct_chg')}%")
        return True
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def test_batch_pct_chg():
    """测试用例 3: 批量涨跌幅（行业均值）"""
    print("\n" + "=" * 60)
    print("测试用例 3: get_batch_pct_chg - 批量涨跌幅")
    print("=" * 60)

    from src.tools.market_statistics import register_market_statistics_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_market_statistics_tools(mcp, api)

    tools = mcp._tool_manager._tools
    get_batch_pct_chg = tools.get("get_batch_pct_chg")

    if not get_batch_pct_chg:
        print("❌ get_batch_pct_chg 工具未注册")
        return False

    # 测试白酒龙头股
    stock_codes = ["600519.SH", "000858.SZ", "000568.SZ"]
    result = await get_batch_pct_chg.fn(
        stock_codes=stock_codes,
        start_date="20260101",
        end_date="20260126"
    )

    if result.get("success"):
        data = result.get("data", {})
        stats = data.get("statistics", {})

        print(f"✅ 调用成功")
        print(f"   日期范围: {data.get('start_date')} - {data.get('end_date')}")
        print(f"   股票数量: {data.get('stock_count')}")
        print(f"   各股涨跌幅:")
        for item in data.get("results", []):
            if "error" not in item:
                print(f"     - {item.get('name')}: {item.get('pct_chg')}%")
            else:
                print(f"     - {item.get('ts_code')}: {item.get('error')}")
        print(f"   行业统计:")
        print(f"     - 均值: {stats.get('mean', 'N/A')}%")
        print(f"     - 中位数: {stats.get('median', 'N/A')}%")
        return True
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def test_historical_data_slim():
    """测试用例 4: 历史数据瘦身"""
    print("\n" + "=" * 60)
    print("测试用例 4: get_historical_data - 返回体瘦身")
    print("=" * 60)

    from src.tools.market_data import register_market_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_market_tools(mcp, api)

    tools = mcp._tool_manager._tools
    get_historical_data = tools.get("get_historical_data")

    if not get_historical_data:
        print("❌ get_historical_data 工具未注册")
        return False

    # 测试默认不返回 items
    result = await get_historical_data.fn(stock_code="000001", days=60)

    if result.get("success"):
        daily_data = result.get("daily_data", {})
        has_items = "items" in daily_data

        print(f"✅ 调用成功")
        print(f"   股票: {result.get('ts_code')}")
        print(f"   数据条数: {daily_data.get('data_count')}")
        print(f"   包含 items: {has_items} (期望: False)")
        print(f"   价格统计:")
        stats = daily_data.get("price_statistics", {})
        print(f"     - 最高价: {stats.get('max_price')}")
        print(f"     - 最低价: {stats.get('min_price')}")
        print(f"     - 平均价: {stats.get('avg_price')}")

        if not has_items:
            print("✅ 返回体瘦身验证通过")
            return True
        else:
            print("❌ 返回体瘦身验证失败 - items 不应该存在")
            return False
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def test_latest_daily_close():
    """测试用例 5: 语义纠偏"""
    print("\n" + "=" * 60)
    print("测试用例 5: get_latest_daily_close - 语义纠偏")
    print("=" * 60)

    from src.tools.market_data import register_market_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_market_tools(mcp, api)

    tools = mcp._tool_manager._tools

    # 检查新函数
    get_latest_daily_close = tools.get("get_latest_daily_close")
    # 检查旧函数别名
    get_realtime_price = tools.get("get_realtime_price")

    if not get_latest_daily_close:
        print("❌ get_latest_daily_close 工具未注册")
        return False

    if not get_realtime_price:
        print("⚠️ get_realtime_price 别名未注册（向后兼容）")
    else:
        print("✅ get_realtime_price 别名已注册（向后兼容）")

    result = await get_latest_daily_close.fn(stock_code="600036")

    if result.get("success"):
        data = result.get("data", {})
        meta = result.get("meta", {})

        print(f"✅ 调用成功")
        print(f"   股票: {result.get('ts_code')}")
        print(f"   收盘价: {data.get('price')}")
        print(f"   涨跌幅: {data.get('pct_chg')}%")
        print(f"   交易日期: {data.get('trade_date')}")
        print(f"   Meta 信息:")
        print(f"     - data_type: {meta.get('data_type')} (期望: daily_close)")
        print(f"     - note: {meta.get('note')}")
        return True
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def test_tool_manifest():
    """测试用例 6: 工具清单"""
    print("\n" + "=" * 60)
    print("测试用例 6: get_tool_manifest - 工具能力清单")
    print("=" * 60)

    from src.tools.meta import register_meta_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_meta_tools(mcp, api)

    tools = mcp._tool_manager._tools
    get_tool_manifest = tools.get("get_tool_manifest")

    if not get_tool_manifest:
        print("❌ get_tool_manifest 工具未注册")
        return False

    result = await get_tool_manifest.fn()

    if result.get("success"):
        print(f"✅ 调用成功")
        print(f"   工具总数: {result.get('total_tools')}")
        print(f"   分类: {result.get('categories')}")
        print(f"   各分类工具数:")
        for cat, tools_list in result.get("tools_by_category", {}).items():
            print(f"     - {cat}: {len(tools_list)} 个")
        return True
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def test_date_tolerance():
    """测试用例 7: 日期容错"""
    print("\n" + "=" * 60)
    print("测试用例 7: 日期容错功能")
    print("=" * 60)

    from src.utils.data_processing import (
        get_latest_trading_day,
        adjust_date_to_trading_day
    )

    api = TushareAPI(config.TUSHARE_TOKEN)

    # 测试获取最近交易日
    latest = await get_latest_trading_day(cache, api)
    print(f"✅ 最近交易日: {latest}")

    # 测试日期调整（假设今天可能非交易日）
    today = "20260126"
    adjusted, msg = await adjust_date_to_trading_day(cache, api, today)
    print(f"✅ 日期调整: {today} -> {adjusted}")
    if msg:
        print(f"   消息: {msg}")

    return True


async def test_sector_next_actions():
    """测试用例 8: 行业工具 next_actions"""
    print("\n" + "=" * 60)
    print("测试用例 8: get_sector_top_stocks - next_actions 提示")
    print("=" * 60)

    from src.tools.market_flow import register_market_flow_tools
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    api = TushareAPI(config.TUSHARE_TOKEN)
    register_market_flow_tools(mcp, api)

    tools = mcp._tool_manager._tools
    get_sector_top_stocks = tools.get("get_sector_top_stocks")

    if not get_sector_top_stocks:
        print("❌ get_sector_top_stocks 工具未注册")
        return False

    result = await get_sector_top_stocks.fn(sector_name="银行", limit=5)

    if result.get("success"):
        next_actions = result.get("next_actions", {})

        print(f"✅ 调用成功")
        print(f"   行业: {result.get('sector_name')}")
        print(f"   龙头股数量: {result.get('count')}")
        print(f"   next_actions 提示:")
        for action_name, action_info in next_actions.items():
            print(f"     - {action_name}:")
            print(f"         tool: {action_info.get('tool')}")
            print(f"         description: {action_info.get('description')}")

        if next_actions:
            print("✅ next_actions 验证通过")
            return True
        else:
            print("❌ next_actions 缺失")
            return False
    else:
        print(f"❌ 调用失败: {result.get('error')}")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 Tushare MCP 工具优化测试")
    print("=" * 60)

    results = []

    # 测试 1: 市场统计
    try:
        results.append(("get_market_summary", await test_market_summary()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("get_market_summary", False))

    # 测试 2: 涨跌幅极值
    try:
        results.append(("get_market_extremes", await test_market_extremes()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("get_market_extremes", False))

    # 测试 3: 批量涨跌幅
    try:
        results.append(("get_batch_pct_chg", await test_batch_pct_chg()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("get_batch_pct_chg", False))

    # 测试 4: 历史数据瘦身
    try:
        results.append(("get_historical_data 瘦身", await test_historical_data_slim()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("get_historical_data 瘦身", False))

    # 测试 5: 语义纠偏
    try:
        results.append(("get_latest_daily_close", await test_latest_daily_close()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("get_latest_daily_close", False))

    # 测试 6: 工具清单
    try:
        results.append(("get_tool_manifest", await test_tool_manifest()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("get_tool_manifest", False))

    # 测试 7: 日期容错
    try:
        results.append(("日期容错", await test_date_tolerance()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("日期容错", False))

    # 测试 8: 行业工具 next_actions
    try:
        results.append(("next_actions 提示", await test_sector_next_actions()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("next_actions 提示", False))

    # 汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print("-" * 60)
    print(f"  总计: {len(results)} 个测试, {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
