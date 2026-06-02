"""返回信封契约 + 向后兼容静态断言（纯静态，进 CI）。

保证统一信封字段齐全、错误信封带 hint，且不悄悄删字段。
"""

from findatamcp.utils.response import (
    build_response, build_success_response, build_error_response, build_meta,
)
from findatamcp.utils.errors import ErrorCode


def test_success_envelope_shape():
    r = build_success_response(data={"x": 1}, trade_date="20260601")
    assert r["success"] is True
    assert "data" in r and "meta" in r and "timestamp" in r
    assert r["meta"]["data_source"] == "tushare_pro"
    # 成功返回不应带 error/error_code
    assert "error" not in r and "error_code" not in r


def test_error_envelope_has_code_and_hint():
    r = build_error_response(error_code=ErrorCode.SYMBOL_NOT_FOUND)
    assert r["success"] is False
    assert r["error_code"] == "symbol_not_found"
    assert r["error"]  # 自动取 message
    assert "resolve_symbol" in r["hint"]  # 可路由默认 hint


def test_error_enum_whitelist_echo():
    r = build_error_response(
        error="metric 非法", error_code=ErrorCode.INVALID_ENUM,
        valid_values=["pct_chg", "amount", "turnover_rate"])
    assert r["valid_values"] == ["pct_chg", "amount", "turnover_rate"]


def test_error_without_hint_when_no_default():
    # UNAUTHORIZED 无默认 hint，且未显式传 → 不应出现空 hint 字段
    r = build_error_response(error_code=ErrorCode.UNAUTHORIZED)
    assert r.get("hint") is None or "hint" not in r


def test_meta_passes_through_source_table():
    m = build_meta(source_table="wind_wande.x", methodology_version="v1.0")
    assert m["source_table"] == "wind_wande.x"
    assert m["methodology_version"] == "v1.0"


def test_backward_compat_envelope_keys():
    """快照核心信封键集合，防止后续误删导致调用方破裂。"""
    r = build_response(success=True, data=[], meta={"data_source": "x", "api_status": "pro"})
    assert {"success", "data", "meta", "timestamp"} <= set(r.keys())


def test_all_error_codes_have_messages():
    codes = [v for k, v in vars(ErrorCode).items()
             if isinstance(v, str) and not k.startswith("_") and k.isupper()]
    for c in codes:
        assert ErrorCode.get_message(c) != "未知错误", f"{c} 缺 message"
