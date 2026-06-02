"""golden traces 一致性（进 CI，无需 API）：确保用例引用的工具都真实存在。

防止改名/删除工具后 golden_traces.yaml 悄悄失配。
"""

from pathlib import Path

import pytest

from tests._harness import tool_names

yaml = pytest.importorskip("yaml")

TRACES = Path(__file__).parent / "eval" / "golden_traces.yaml"


@pytest.fixture(scope="module")
def traces():
    return yaml.safe_load(TRACES.read_text())["traces"]


def test_traces_well_formed(traces):
    assert len(traces) >= 8
    for t in traces:
        assert t.get("id") and t.get("task")
        assert t.get("kind") in ("routing", "recovery")
        assert t.get("expected_first"), f"{t['id']} 缺 expected_first"


def test_expected_tools_are_registered(traces):
    names = tool_names()
    bad = [(t["id"], e)
           for t in traces
           for e in t.get("expected_first", []) + t.get("expected_next", [])
           if e not in names]
    assert not bad, f"golden traces 引用了未注册工具: {bad}"
