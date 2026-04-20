"""Quick test for HK/US stock support via MCP client"""
import asyncio
import json
from fastmcp import Client

PASS = 0
FAIL = 0

def check(name, data, condition, detail=""):
    global PASS, FAIL
    ok = condition(data) if callable(condition) else condition
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return ok


async def main():
    url = "http://localhost:8006/mcp"

    async with Client(url) as client:
        print("=" * 70)
        print("HK / US Stock Support Test Suite")
        print("=" * 70)

        # ===== Test 1: A 股回归 =====
        print("\n[Test 1] A 股回归 — get_latest_daily_close(600519.SH)")
        r = await client.call_tool("get_latest_daily_close", {"ts_code": "600519.SH"})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        check("asset_type=stock", data, lambda d: d.get("asset_type") == "stock")
        check("has price", data, lambda d: d.get("data", {}).get("price") is not None,
              f"price={data.get('data',{}).get('price')}")

        # ===== Test 2: 港股日线 =====
        print("\n[Test 2] 港股日线 — get_latest_daily_close(00700.HK) 腾讯")
        r = await client.call_tool("get_latest_daily_close", {"ts_code": "00700.HK"})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        check("asset_type=hk", data, lambda d: d.get("asset_type") == "hk")
        check("has price", data, lambda d: d.get("data", {}).get("price") is not None,
              f"price={data.get('data',{}).get('price')}")

        # ===== Test 3: 美股日线 =====
        print("\n[Test 3] 美股日线 — get_latest_daily_close(AAPL) 苹果")
        r = await client.call_tool("get_latest_daily_close", {"ts_code": "AAPL"})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        check("asset_type=us", data, lambda d: d.get("asset_type") == "us")
        check("has price", data, lambda d: d.get("data", {}).get("price") is not None,
              f"price={data.get('data',{}).get('price')}")

        # ===== Test 4: 港股历史 =====
        print("\n[Test 4] 港股历史 — get_historical_data(00700.HK, days=30)")
        r = await client.call_tool("get_historical_data", {"ts_code": "00700.HK", "days": 30})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        check("asset_type=hk", data, lambda d: d.get("asset_type") == "hk")
        dd = data.get("daily_data", {})
        check("has data_count", data, lambda d: dd.get("data_count", 0) > 0,
              f"count={dd.get('data_count')}")

        # ===== Test 5: 美股历史 =====
        print("\n[Test 5] 美股历史 — get_historical_data(AAPL, days=30)")
        r = await client.call_tool("get_historical_data", {"ts_code": "AAPL", "days": 30})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        check("asset_type=us", data, lambda d: d.get("asset_type") == "us")
        dd = data.get("daily_data", {})
        check("has data_count", data, lambda d: dd.get("data_count", 0) > 0,
              f"count={dd.get('data_count')}")

        # ===== Test 6: 搜索港股 =====
        print("\n[Test 6] 搜索港股 — search_stocks('腾讯')")
        r = await client.call_tool("search_stocks", {"keyword": "腾讯"})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        hk = data.get("hk_stocks", [])
        check("has hk_stocks", data, lambda d: len(hk) > 0, f"count={len(hk)}")
        if hk:
            top = ', '.join(s['ts_code'] + ' ' + s['name'] for s in hk[:3])
            print(f"    top results: {top}")

        # ===== Test 7: 搜索美股 =====
        print("\n[Test 7] 搜索美股 — search_stocks('Apple')")
        r = await client.call_tool("search_stocks", {"keyword": "Apple"})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        us = data.get("us_stocks", [])
        check("has us_stocks", data, lambda d: len(us) > 0, f"count={len(us)}")
        if us:
            top = ', '.join(str(s['ts_code']) + ' ' + str(s.get('name', s.get('enname', ''))) for s in us[:3])
            print(f"    top results: {top}")

        # ===== Test 8: 财务拦截（美股） =====
        print("\n[Test 8] 财务拦截 — get_income_statement(AAPL)")
        r = await client.call_tool("get_income_statement", {"ts_code": "AAPL"})
        data = json.loads(r.content[0].text)
        check("success=False", data, lambda d: d.get("success") == False)
        check("error mentions A股", data, lambda d: "仅支持A股" in d.get("error", ""),
              f"error={data.get('error','')[:60]}")

        # ===== Test 9: 资金流拦截（港股） =====
        print("\n[Test 9] 资金流拦截 — get_moneyflow(00700.HK)")
        r = await client.call_tool("get_moneyflow", {"ts_code": "00700.HK"})
        data = json.loads(r.content[0].text)
        check("success=False", data, lambda d: d.get("success") == False)
        check("error mentions A股", data, lambda d: "仅支持A股" in d.get("error", ""),
              f"error={data.get('error','')[:60]}")

        # ===== Test 10: get_basic_info 港股 =====
        print("\n[Test 10] 基本信息 — get_basic_info(00700.HK)")
        r = await client.call_tool("get_basic_info", {"ts_code": "00700.HK"})
        data = json.loads(r.content[0].text)
        check("success=True", data, lambda d: d.get("success") == True)
        bi = data.get("basic_info", {})
        check("has name", data, lambda d: bi.get("name") is not None,
              f"name={bi.get('name')}")

        # ===== Summary =====
        print("\n" + "=" * 70)
        total = PASS + FAIL
        print(f"Results: {PASS}/{total} passed, {FAIL} failed")
        if FAIL == 0:
            print("All tests passed!")
        else:
            print(f"WARNING: {FAIL} test(s) failed!")
        print("=" * 70)


asyncio.run(main())
