"""大数据分流处理

当工具返回行数 > THRESHOLD 时，自动存为独立数据资源，
并仅内联预览数据、摘要和资源 URI。
小数据也会带上列 schema（contract 一致）。
"""

import logging
from math import ceil
from typing import Dict, List, Any, Optional, Callable, Literal

from ..cache.data_file_store import data_file_store, infer_schema

logger = logging.getLogger(__name__)

THRESHOLD = 200  # 行数阈值
DATA_RESOURCE_SCHEME = "data://table"


def build_data_resource_uri(data_id: str) -> str:
    """构造大数据资源 URI。"""
    return f"{DATA_RESOURCE_SCHEME}/{data_id}"


def build_preview_rows(
    rows: List[Dict[str, Any]],
    limit: int,
    mode: Literal["head", "tail"] = "head",
) -> List[Dict[str, Any]]:
    """获取内联预览行。"""
    if limit <= 0 or not rows:
        return []
    if len(rows) <= limit:
        return rows
    if mode == "tail":
        return rows[-limit:]
    return rows[:limit]


def sample_rows(rows: List[Dict[str, Any]], max_points: int = 120) -> List[Dict[str, Any]]:
    """对长序列做等距抽样，供 UI 展示使用。"""
    if max_points <= 0 or len(rows) <= max_points:
        return rows
    step = (len(rows) - 1) / (max_points - 1)
    sampled: List[Dict[str, Any]] = []
    last_idx = -1
    for i in range(max_points):
        idx = min(len(rows) - 1, ceil(i * step))
        if idx != last_idx:
            sampled.append(rows[idx])
            last_idx = idx
    if sampled[-1] != rows[-1]:
        sampled[-1] = rows[-1]
    return sampled


def _build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """自动生成数值列统计 + 日期范围"""
    summary: Dict[str, Any] = {}

    if not rows:
        return summary

    keys = rows[0].keys()

    date_cols = [k for k in keys if "date" in k.lower()]
    for col in date_cols:
        vals = [r[col] for r in rows if r.get(col)]
        if vals:
            summary["date_range"] = f"{min(vals)} ~ {max(vals)}"
            break

    for col in keys:
        if col in date_cols or col in ("ts_code", "index_code", "con_code", "con_name", "trade_date"):
            continue
        nums = []
        for r in rows:
            v = r.get(col)
            if v is not None:
                try:
                    nums.append(float(v))
                except (ValueError, TypeError):
                    break
        if len(nums) > len(rows) * 0.5:
            summary[col] = {
                "latest": round(nums[-1], 4),
                "min": round(min(nums), 4),
                "max": round(max(nums), 4),
                "mean": round(sum(nums) / len(nums), 4),
            }

    return summary


def prepare_large_data_view(
    rows: List[Dict[str, Any]],
    tool_name: str,
    query_params: Dict[str, Any],
    *,
    preview_rows: int = 5,
    preview_mode: Literal["head", "tail"] = "head",
    sample_points: int = 120,
    summary_builder: Optional[Callable] = None,
) -> tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回大数据 payload、内联数据和 UI 展示数据。"""
    large = handle_large_data(
        rows,
        tool_name,
        query_params,
        summary_builder=summary_builder,
        preview_rows=preview_rows,
        preview_mode=preview_mode,
    )
    if "is_truncated" in large:
        inline_rows = large.get("preview", [])
        ui_rows = sample_rows(rows, max_points=sample_points)
    else:
        inline_rows = large.get("data", rows)
        ui_rows = rows
    return large, inline_rows, ui_rows


def merge_large_data_payload(result: Dict[str, Any], large_payload: Dict[str, Any]) -> Dict[str, Any]:
    """将大数据 payload 合并进工具返回。"""
    if "is_truncated" in large_payload:
        result.update(large_payload)
    elif "schema" in large_payload:
        # 小数据也透传 schema，便于下游统一构造 ColDef
        result.setdefault("schema", large_payload["schema"])
    return result


def handle_large_data(
    rows: List[Dict[str, Any]],
    tool_name: str,
    query_params: Dict[str, Any],
    summary_builder: Optional[Callable] = None,
    preview_rows: int = 5,
    preview_mode: Literal["head", "tail"] = "head",
) -> Dict[str, Any]:
    """大数据分流：小数据 inline，大数据存文件返回摘要。

    无论哪条分支，返回 dict 都带 `schema` 字段（{col: {"type": date|string|number|bool}}），
    供下游（artifact renderer 等）构造列类型。
    """
    total = len(rows)
    columns = list(rows[0].keys()) if rows else []
    schema = infer_schema(rows, columns)

    if total <= THRESHOLD:
        return {"data": rows, "total_rows": total, "schema": schema}

    meta = data_file_store.store(rows, tool_name, query_params)
    urls = data_file_store.get_download_urls(meta.data_id)
    resource_uri = build_data_resource_uri(meta.data_id)
    preview = build_preview_rows(rows, preview_rows, mode=preview_mode)

    if summary_builder:
        summary = summary_builder(rows)
    else:
        summary = _build_summary(rows)

    return {
        "total_rows": total,
        "is_truncated": True,
        "message": f"数据量较大({total}行)，仅内联预览数据；完整数据请读取资源 {resource_uri}。",
        "data_id": meta.data_id,
        "resource_uri": resource_uri,
        "download_urls": urls,
        "preview": preview,
        "summary": summary,
        "schema": meta.schema,
        "expires_in": "24小时",
    }
