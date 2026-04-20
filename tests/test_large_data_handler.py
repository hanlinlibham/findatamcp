"""测试 utils.large_data_handler

覆盖阈值分支、预览行取头/尾、等距采样、_build_summary 统计、以及
handle_large_data / merge_large_data_payload 的合约。
"""

from __future__ import annotations

import pandas as pd
import pytest

from findatamcp.utils import large_data_handler as ldh


def _rows(n: int, with_date: bool = True):
    rows = []
    for i in range(n):
        row = {"close": 10.0 + i, "vol": 100 + i}
        if with_date:
            row["trade_date"] = f"2024{(i // 30) + 1:02d}{(i % 30) + 1:02d}"
        rows.append(row)
    return rows


# ---------- build_preview_rows ----------

def test_preview_head_within_limit_returns_all():
    rows = _rows(3)
    assert ldh.build_preview_rows(rows, limit=10) == rows


def test_preview_head_limits():
    rows = _rows(10)
    assert ldh.build_preview_rows(rows, limit=3) == rows[:3]


def test_preview_tail_limits():
    rows = _rows(10)
    assert ldh.build_preview_rows(rows, limit=3, mode="tail") == rows[-3:]


def test_preview_zero_limit_returns_empty():
    assert ldh.build_preview_rows(_rows(5), limit=0) == []


def test_preview_empty_input():
    assert ldh.build_preview_rows([], limit=5) == []


# ---------- sample_rows ----------

def test_sample_returns_all_when_below_cap():
    rows = _rows(50)
    assert ldh.sample_rows(rows, max_points=120) == rows


def test_sample_preserves_first_and_last():
    rows = _rows(1000)
    sampled = ldh.sample_rows(rows, max_points=120)
    assert 1 < len(sampled) <= 120
    assert sampled[0] == rows[0]
    assert sampled[-1] == rows[-1]


def test_sample_with_max_points_two_keeps_endpoints():
    rows = _rows(10)
    sampled = ldh.sample_rows(rows, max_points=2)
    assert sampled[0] == rows[0]
    assert sampled[-1] == rows[-1]


# ---------- _build_summary ----------

def test_summary_detects_date_range():
    rows = _rows(5)
    s = ldh._build_summary(rows)
    assert "date_range" in s
    assert s["date_range"].startswith("2024")


def test_summary_numeric_stats():
    rows = [{"close": 1.0}, {"close": 2.0}, {"close": 3.0}]
    s = ldh._build_summary(rows)
    assert s["close"]["latest"] == 3.0
    assert s["close"]["min"] == 1.0
    assert s["close"]["max"] == 3.0
    assert s["close"]["mean"] == pytest.approx(2.0)


def test_summary_skips_identifier_columns():
    rows = [{"ts_code": "600519.SH", "close": 1.0},
            {"ts_code": "600519.SH", "close": 2.0}]
    s = ldh._build_summary(rows)
    assert "ts_code" not in s
    assert "close" in s


def test_summary_empty_rows_returns_empty():
    assert ldh._build_summary([]) == {}


# ---------- handle_large_data ----------

def test_handle_large_data_inline_branch():
    rows = _rows(10)
    result = ldh.handle_large_data(rows, "tool_x", {"k": "v"})
    assert result["total_rows"] == 10
    assert result["data"] == rows
    assert "schema" in result
    assert "is_truncated" not in result


def test_handle_large_data_threshold_boundary():
    """刚好 200 行仍走 inline 分支。"""
    rows = _rows(ldh.THRESHOLD)
    result = ldh.handle_large_data(rows, "tool_x", {})
    assert "data" in result
    assert "is_truncated" not in result


def test_handle_large_data_truncated_branch(tmp_path, monkeypatch):
    # 让文件写入落到临时目录,避免污染
    monkeypatch.setattr(
        ldh.data_file_store, "_DataFileStore__unused", None, raising=False
    )

    rows = _rows(ldh.THRESHOLD + 50)
    result = ldh.handle_large_data(rows, "tool_x", {"k": "v"}, preview_rows=3)

    assert result["is_truncated"] is True
    assert result["total_rows"] == len(rows)
    assert len(result["preview"]) == 3
    assert result["preview"] == rows[:3]
    assert result["data_id"]
    assert result["resource_uri"].startswith("data://table/")
    assert result["download_urls"]["jsonl"].endswith(".jsonl")
    assert "schema" in result


def test_handle_large_data_preview_tail():
    rows = _rows(ldh.THRESHOLD + 10)
    result = ldh.handle_large_data(
        rows, "tool_x", {}, preview_rows=2, preview_mode="tail"
    )
    assert result["preview"] == rows[-2:]


# ---------- prepare_large_data_view ----------

def test_prepare_large_data_view_small():
    rows = _rows(5)
    large, inline, ui = ldh.prepare_large_data_view(rows, "tool_x", {})
    assert inline == rows
    assert ui == rows
    assert "is_truncated" not in large


def test_prepare_large_data_view_large_samples_ui():
    rows = _rows(ldh.THRESHOLD + 500)
    large, inline, ui = ldh.prepare_large_data_view(
        rows, "tool_x", {}, preview_rows=5, sample_points=50
    )
    assert large["is_truncated"] is True
    assert len(inline) == 5
    assert len(ui) <= 50


# ---------- merge_large_data_payload ----------

def test_merge_truncated_updates_result():
    result = {"success": True}
    payload = {"is_truncated": True, "preview": [], "data_id": "abc"}
    merged = ldh.merge_large_data_payload(result, payload)
    assert merged["is_truncated"] is True
    assert merged["data_id"] == "abc"
    assert merged["success"] is True


def test_merge_small_data_only_passes_schema():
    result = {"success": True}
    payload = {"data": [1, 2], "total_rows": 2, "schema": {"x": {"type": "number"}}}
    merged = ldh.merge_large_data_payload(result, payload)
    # data 不应被合并
    assert "data" not in merged
    assert merged["schema"] == {"x": {"type": "number"}}


# ---------- build_data_resource_uri ----------

def test_build_uri():
    assert ldh.build_data_resource_uri("abc123") == "data://table/abc123"
