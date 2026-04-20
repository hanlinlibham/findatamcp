"""
统一响应格式构建器 (P0-3)

提供标准化的响应格式，包含 meta 信息用于：
- 数据来源追踪
- 日期口径说明
- 数据覆盖范围
- API 状态标识
"""

from typing import Any, Dict, Optional
from datetime import datetime


def build_response(
    success: bool,
    data: Any = None,
    meta: Optional[Dict] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    统一响应格式构建器

    Args:
        success: 是否成功
        data: 返回数据
        meta: 元数据信息
        error: 错误信息（失败时）
        error_code: 错误码（失败时）

    Returns:
        标准化响应格式:
        {
            "success": bool,
            "data": {...},
            "meta": {
                "data_source": "tushare_pro",
                "trade_date": "20260126",
                "date_range": "20260101-20260126",
                "date_adjusted": false,
                "date_adjust_message": "",
                "coverage": 4500,
                "expected_coverage": 5000,
                "api_status": "pro"
            },
            "error": null,
            "error_code": null,
            "timestamp": "2026-01-26T10:00:00"
        }
    """
    response = {
        "success": success,
        "data": data,
        "meta": meta or {},
        "error": error,
        "error_code": error_code,
        "timestamp": datetime.now().isoformat()
    }

    # 清理空值
    if not error:
        del response["error"]
    if not error_code:
        del response["error_code"]

    return response


def build_meta(
    data_source: str = "tushare_pro",
    trade_date: Optional[str] = None,
    date_range: Optional[str] = None,
    date_adjusted: bool = False,
    date_adjust_message: Optional[str] = None,
    coverage: Optional[int] = None,
    expected_coverage: Optional[int] = None,
    api_status: str = "pro",
    **kwargs
) -> Dict[str, Any]:
    """
    构建 meta 信息

    Args:
        data_source: 数据来源 (tushare_pro/tushare_free)
        trade_date: 交易日期 (YYYYMMDD)
        date_range: 日期范围 (YYYYMMDD-YYYYMMDD)
        date_adjusted: 是否进行了日期调整
        date_adjust_message: 日期调整说明
        coverage: 实际数据条数
        expected_coverage: 预期数据条数
        api_status: API 状态 (pro/free)
        **kwargs: 其他自定义字段

    Returns:
        meta 字典
    """
    meta = {
        "data_source": data_source,
        "api_status": api_status
    }

    if trade_date:
        meta["trade_date"] = trade_date

    if date_range:
        meta["date_range"] = date_range

    if date_adjusted:
        meta["date_adjusted"] = date_adjusted
        if date_adjust_message:
            meta["date_adjust_message"] = date_adjust_message

    if coverage is not None:
        meta["coverage"] = coverage

    if expected_coverage is not None:
        meta["expected_coverage"] = expected_coverage

    # 添加自定义字段
    meta.update(kwargs)

    return meta


def build_success_response(
    data: Any,
    trade_date: Optional[str] = None,
    date_range: Optional[str] = None,
    date_adjusted: bool = False,
    date_adjust_message: Optional[str] = None,
    coverage: Optional[int] = None,
    api_status: str = "pro",
    **extra_meta
) -> Dict[str, Any]:
    """
    快速构建成功响应

    Args:
        data: 返回数据
        trade_date: 交易日期
        date_range: 日期范围
        date_adjusted: 是否日期调整
        date_adjust_message: 日期调整说明
        coverage: 数据覆盖量
        api_status: API 状态
        **extra_meta: 额外 meta 字段

    Returns:
        标准化成功响应
    """
    meta = build_meta(
        trade_date=trade_date,
        date_range=date_range,
        date_adjusted=date_adjusted,
        date_adjust_message=date_adjust_message,
        coverage=coverage,
        api_status=api_status,
        **extra_meta
    )

    return build_response(success=True, data=data, meta=meta)


def build_error_response(
    error: str,
    error_code: Optional[str] = None,
    data: Any = None
) -> Dict[str, Any]:
    """
    快速构建错误响应

    Args:
        error: 错误信息
        error_code: 错误码
        data: 附加数据（可选）

    Returns:
        标准化错误响应
    """
    return build_response(
        success=False,
        data=data,
        error=error,
        error_code=error_code
    )
