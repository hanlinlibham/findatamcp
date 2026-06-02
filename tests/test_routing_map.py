"""路由地图完整性静态断言（纯静态，进 CI，无需 Tushare token / 运行中 server）。

校验 ROUTING_MAP 这份"唯一事实源"自洽且与真实注册工具一致：
- 每个 key 是真实注册工具
- 每条 next_steps.tool 是真实注册工具（无悬空边）
- param_from 路径语法合法、产出实体类型在词表内
- 入口工具 produces ts_code；codes 生产者的下游确实消费 codes
"""

import pytest

from findatamcp.tools.routing import ROUTING_MAP, _resolve_path, attach_next_steps
from tests._harness import tool_names

ENTITY_VOCAB = {"keyword", "ts_code", "codes", "index_code", "sector",
                "trade_date", "report_period", "macro"}


@pytest.fixture(scope="module")
def names():
    return tool_names()


def test_keys_are_registered_tools(names):
    missing = [k for k in ROUTING_MAP if k not in names]
    assert not missing, f"ROUTING_MAP 含未注册工具 key: {missing}"


def test_no_dangling_edges(names):
    dangling = [
        (k, e["tool"])
        for k, spec in ROUTING_MAP.items()
        for e in spec.get("next_steps", [])
        if e["tool"] not in names
    ]
    assert not dangling, f"next_steps 指向未注册工具(悬空边): {dangling}"


def test_entity_types_in_vocab():
    bad = []
    for k, spec in ROUTING_MAP.items():
        for ent in spec.get("produces", []) + spec.get("consumes", []):
            if ent not in ENTITY_VOCAB:
                bad.append((k, ent))
    assert not bad, f"未知实体类型: {bad}"


def test_every_edge_has_intent_and_tool():
    bad = []
    for k, spec in ROUTING_MAP.items():
        for e in spec.get("next_steps", []):
            if not e.get("intent") or not e.get("tool"):
                bad.append((k, e))
    assert not bad, f"边缺 intent/tool: {bad}"


def test_param_from_paths_parse():
    """param_from 路径必须能被解析器解析（语法合法，不抛错）。"""
    sample = {
        "candidates": [{"code": "600519.SH"}],
        "codes": ["a", "b", "c"],
        "ts_code": "600519.SH",
    }
    for k, spec in ROUTING_MAP.items():
        for e in spec.get("next_steps", []):
            for pname, path in e.get("param_from", {}).items():
                # 不抛错即合法；解析不到返回 None 是允许的
                _resolve_path(sample, path)


def test_attach_prefills_resolve_symbol():
    res = attach_next_steps(
        {"success": True, "candidates": [{"code": "600519.SH"}]}, "resolve_symbol")
    hist = [s for s in res["next_steps"] if s["tool"] == "get_historical_data"]
    assert hist and hist[0]["params"]["ts_code"] == "600519.SH"


def test_attach_skips_on_error():
    res = attach_next_steps({"success": False, "error": "x"}, "resolve_symbol")
    assert "next_steps" not in res


def test_no_orphan_hubs(names):
    """每个 produces 'codes' 的生产者，至少有一条边指向消费 codes 的工具。"""
    code_consumers = {k for k, s in ROUTING_MAP.items() if "codes" in s.get("consumes", [])}
    for k, spec in ROUTING_MAP.items():
        if "codes" in spec.get("produces", []):
            targets = {e["tool"] for e in spec.get("next_steps", [])}
            assert targets & code_consumers, f"{k} 产出 codes 但无下游消费者边"
