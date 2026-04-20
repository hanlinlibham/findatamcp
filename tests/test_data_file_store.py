"""测试 cache.data_file_store

覆盖:schema 推断、JSONL 规范化(NaN→null、id 列强制字符串)、文件生命周期与过期清理。
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    """每个用例一个独立 DataFileStore(绕过单例)。"""
    from findatamcp.cache import data_file_store as dfs_mod

    monkeypatch.setattr(dfs_mod, "DATA_DIR", tmp_path)

    instance = dfs_mod.DataFileStore.__new__(dfs_mod.DataFileStore)
    instance._initialized = False
    instance.__init__()
    return instance


# ---------- schema 推断 ----------

def test_infer_schema_by_column_name():
    from findatamcp.cache.data_file_store import infer_schema
    rows = [{"trade_date": "20240102", "ts_code": "600519.SH", "close": 1.0}]
    schema = infer_schema(rows, ["trade_date", "ts_code", "close"])
    assert schema["trade_date"]["type"] == "date"
    assert schema["ts_code"]["type"] == "string"
    assert schema["close"]["type"] == "number"


def test_infer_schema_bool_and_allnone():
    from findatamcp.cache.data_file_store import infer_schema
    rows = [{"flag": True, "empty": None}, {"flag": False, "empty": None}]
    schema = infer_schema(rows, ["flag", "empty"])
    assert schema["flag"]["type"] == "bool"
    # 全空列保守判为 string
    assert schema["empty"]["type"] == "string"


# ---------- store / get ----------

def test_store_creates_jsonl_and_json(fresh_store):
    rows = [
        {"trade_date": "20240102", "ts_code": "600519.SH", "close": 10.5},
        {"trade_date": "20240103", "ts_code": "600519.SH", "close": 11.0},
    ]
    meta = fresh_store.store(rows, "get_hist", {"ts_code": "600519.SH"})

    assert meta.total_rows == 2
    assert meta.columns == ["trade_date", "ts_code", "close"]
    assert Path(meta.jsonl_path).exists()
    assert Path(meta.json_path).exists()

    # JSONL 每行一条,日期/代码列必须是字符串
    lines = Path(meta.jsonl_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["trade_date"] == "20240102"
    assert first["ts_code"] == "600519.SH"
    assert first["close"] == 10.5


def test_store_nan_becomes_null_in_jsonl(fresh_store):
    rows = [{"trade_date": "20240102", "close": math.nan}]
    meta = fresh_store.store(rows, "t", {})

    line = Path(meta.jsonl_path).read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["close"] is None


def test_store_forces_str_for_code_columns(fresh_store):
    rows = [{"ts_code": 600519, "symbol": 600519, "close": 1.0}]
    meta = fresh_store.store(rows, "t", {})
    payload = json.loads(Path(meta.jsonl_path).read_text().strip())
    assert payload["ts_code"] == "600519"
    assert payload["symbol"] == "600519"
    # 非 id/date 列保持原类型
    assert payload["close"] == 1.0


def test_get_returns_meta_for_unexpired(fresh_store):
    meta = fresh_store.store([{"x": 1}], "t", {})
    got = fresh_store.get(meta.data_id)
    assert got is meta


def test_get_returns_none_for_unknown(fresh_store):
    assert fresh_store.get("does_not_exist") is None


def test_get_expired_removes_files(fresh_store):
    meta = fresh_store.store([{"x": 1}], "t", {})
    # 人为改过期时间到过去
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    fresh_store._index[meta.data_id].expires_at = past

    assert fresh_store.get(meta.data_id) is None
    # 文件应被清理
    assert not Path(meta.jsonl_path).exists()
    assert not Path(meta.json_path).exists()


def test_cleanup_expired_batch(fresh_store):
    m1 = fresh_store.store([{"x": 1}], "t", {})
    m2 = fresh_store.store([{"x": 2}], "t", {})
    # 把 m1 设为已过期
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    fresh_store._index[m1.data_id].expires_at = past

    fresh_store.cleanup_expired()

    assert m1.data_id not in fresh_store._index
    assert m2.data_id in fresh_store._index
    assert not Path(m1.jsonl_path).exists()
    assert Path(m2.jsonl_path).exists()


def test_get_download_urls_structure(fresh_store):
    meta = fresh_store.store([{"x": 1}], "t", {})
    urls = fresh_store.get_download_urls(meta.data_id)
    assert urls["jsonl"].endswith(f"/data/{meta.data_id}.jsonl")
    assert urls["json"].endswith(f"/data/{meta.data_id}.json")
