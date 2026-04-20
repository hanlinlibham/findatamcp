"""测试 entity_store

覆盖加载、拼音首字母索引、代码查询、搜索过滤。不依赖真 Tushare。
"""

from __future__ import annotations

import pytest

from findatamcp.entity_store import EntityStore, _pinyin_full, _pinyin_initials


# ---------- 纯函数拼音 ----------

def test_pinyin_initials_known_mapping():
    assert _pinyin_initials("平安银行") == "payh"
    assert _pinyin_initials("贵州茅台") == "gzmt"


def test_pinyin_full_known_mapping():
    assert _pinyin_full("平安银行") == "pinganyinhang"


def test_pinyin_non_chinese_passthrough():
    # 英文 / 数字不应抛异常
    assert _pinyin_initials("ETF50") != ""


# ---------- EntityStore.load ----------

@pytest.mark.asyncio
async def test_load_populates_stocks_and_funds(
    mock_tushare_api,
    sample_stock_basic_df,
    sample_fund_basic_df,
):
    store = EntityStore()
    n = await store.load(mock_tushare_api)
    assert n == len(sample_stock_basic_df) + len(sample_fund_basic_df)

    stats = await store.get_stats()
    assert stats["loaded"] is True
    assert stats["stocks"] == len(sample_stock_basic_df)
    assert stats["funds"] == len(sample_fund_basic_df)
    assert stats["total"] == n


@pytest.mark.asyncio
async def test_load_handles_empty_stock_df(mock_tushare_api):
    import pandas as pd
    mock_tushare_api.pro.stock_basic.return_value = pd.DataFrame()
    mock_tushare_api.pro.fund_basic.return_value = pd.DataFrame()

    store = EntityStore()
    n = await store.load(mock_tushare_api)
    assert n == 0
    assert (await store.get_stats())["loaded"] is True


@pytest.mark.asyncio
async def test_load_survives_stock_api_exception(mock_tushare_api, sample_fund_basic_df):
    mock_tushare_api.pro.stock_basic.side_effect = RuntimeError("api down")

    store = EntityStore()
    n = await store.load(mock_tushare_api)
    # 股票加载失败,但基金应照常加载
    assert n == len(sample_fund_basic_df)


# ---------- 搜索 ----------

@pytest.fixture
async def loaded_store(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)
    return store


@pytest.mark.asyncio
async def test_search_by_ts_code_exact(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    results = await store.search_entities("600519.SH")
    assert results
    assert results[0]["code"] == "600519.SH"


@pytest.mark.asyncio
async def test_search_by_bare_symbol(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    results = await store.search_entities("600519")
    assert any(r["code"] == "600519.SH" for r in results)


@pytest.mark.asyncio
async def test_search_by_pinyin_initials(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    results = await store.search_entities("gzmt")
    assert any(r["name"] == "贵州茅台" for r in results)


@pytest.mark.asyncio
async def test_search_by_chinese_substring(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    results = await store.search_entities("茅台")
    assert any(r["name"] == "贵州茅台" for r in results)


@pytest.mark.asyncio
async def test_search_filters_by_entity_type(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    stocks = await store.search_entities("30", entity_type="stock", limit=20)
    funds = await store.search_entities("30", entity_type="fund", limit=20)

    assert all(r["entity_type"] == "stock" for r in stocks)
    assert all(r["entity_type"] == "fund" for r in funds)


@pytest.mark.asyncio
async def test_search_respects_limit(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    # 用空关键词拿不到结果,换一个宽泛的代码前缀
    results = await store.search_entities("6", limit=1)
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_search_returns_empty_when_not_loaded():
    store = EntityStore()
    assert await store.search_entities("xxx") == []


# ---------- get_entity_by_code ----------

@pytest.mark.asyncio
async def test_get_entity_by_ts_code(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    e = await store.get_entity_by_code("600519.SH")
    assert e is not None
    assert e["name"] == "贵州茅台"


@pytest.mark.asyncio
async def test_get_entity_by_bare_symbol(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    e = await store.get_entity_by_code("600519")
    assert e is not None
    assert e["code"] == "600519.SH"


@pytest.mark.asyncio
async def test_get_entity_case_insensitive_suffix(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)

    e = await store.get_entity_by_code("600519.sh")
    assert e is not None
    assert e["code"] == "600519.SH"


@pytest.mark.asyncio
async def test_get_entity_unknown_returns_none(mock_tushare_api):
    store = EntityStore()
    await store.load(mock_tushare_api)
    assert await store.get_entity_by_code("999999.ZZ") is None
