"""Quick test for index support via MCP client"""
import asyncio
import json
from fastmcp import Client

async def main():
    url = "http://localhost:8006/mcp"

    async with Client(url) as client:
        print("=" * 60)

        # Test 1: Stock regression — 600519.SH (贵州茅台)
        print("\n[Test 1] get_latest_daily_close(600519.SH) — stock regression")
        r = await client.call_tool("get_latest_daily_close", {"ts_code": "600519.SH"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        print(f"  success={data.get('success')}, asset_type={data.get('asset_type')}, price={data.get('data',{}).get('price')}")

        # Test 2: Shanghai Composite Index — 000001.SH
        print("\n[Test 2] get_latest_daily_close(000001.SH) — Shanghai index")
        r = await client.call_tool("get_latest_daily_close", {"ts_code": "000001.SH"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        print(f"  success={data.get('success')}, asset_type={data.get('asset_type')}, price={data.get('data',{}).get('price')}")

        # Test 3: Shenzhen Component Index — 399001.SZ (30 days)
        print("\n[Test 3] get_historical_data(399001.SZ, days=5) — Shenzhen index")
        r = await client.call_tool("get_historical_data", {"ts_code": "399001.SZ", "days": 30})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        dd = data.get('daily_data', {})
        print(f"  success={data.get('success')}, asset_type={data.get('asset_type')}, count={dd.get('data_count')}, latest_price={dd.get('price_statistics',{}).get('latest_price')}")

        # Test 4: Shenwan Industry Index — 801010.SI
        print("\n[Test 4] get_historical_data(801010.SI, days=5) — Shenwan index (sw_daily)")
        r = await client.call_tool("get_historical_data", {"ts_code": "801010.SI", "days": 30})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        dd = data.get('daily_data', {})
        print(f"  success={data.get('success')}, asset_type={data.get('asset_type')}, count={dd.get('data_count')}, latest_price={dd.get('price_statistics',{}).get('latest_price')}")

        # Test 5: Bare code — 000001 should still be stock (Ping An Bank)
        print("\n[Test 5] get_latest_daily_close(000001) — bare code = Ping An Bank (stock)")
        r = await client.call_tool("get_latest_daily_close", {"ts_code": "000001"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        print(f"  success={data.get('success')}, asset_type={data.get('asset_type')}, ts_code={data.get('ts_code')}, price={data.get('data',{}).get('price')}")

        # Test 6: Search for 沪深300
        print("\n[Test 6] search_stocks('沪深300') — should return index results")
        r = await client.call_tool("search_stocks", {"keyword": "沪深300"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        indices = data.get('indices', [])
        print(f"  success={data.get('success')}, stock_count={len(data.get('stocks',[]))}, index_count={len(indices)}")
        for idx in indices[:3]:
            print(f"    - {idx['ts_code']} {idx['name']}")

        # Test 7: New tool — get_index_weight
        print("\n[Test 7] get_index_weight(000300.SH) — CSI 300 constituents")
        r = await client.call_tool("get_index_weight", {"index_code": "000300.SH"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        constituents = data.get('constituents', [])
        print(f"  success={data.get('success')}, count={data.get('count')}")
        for c in constituents[:5]:
            print(f"    - {c.get('con_code')} weight={c.get('weight')}")

        # Test 8: New tool — get_index_valuation
        print("\n[Test 8] get_index_valuation(000001.SH) — Shanghai index valuation")
        r = await client.call_tool("get_index_valuation", {"ts_code": "000001.SH"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        vals = data.get('data', [])
        print(f"  success={data.get('success')}, count={data.get('count')}")
        if vals:
            latest = vals[-1]
            print(f"    latest: date={latest.get('trade_date')}, pe={latest.get('pe')}, pb={latest.get('pb')}, total_mv={latest.get('total_mv')}")

        # Test 9: New tool — get_industry_overview (classify)
        print("\n[Test 9] get_industry_overview(action='classify', level='L1') — Shenwan L1 industries")
        r = await client.call_tool("get_industry_overview", {"action": "classify", "level": "L1", "src": "SW2021"})
        data = json.loads(r.content[0].text) if hasattr(r.content[0], 'text') else r.content[0]
        items = data.get('data', [])
        print(f"  success={data.get('success')}, count={data.get('count')}")
        for item in items[:5]:
            print(f"    - {item.get('index_code', 'N/A')} {item.get('industry_name', 'N/A')}")

        print("\n" + "=" * 60)
        print("All tests completed!")

asyncio.run(main())
