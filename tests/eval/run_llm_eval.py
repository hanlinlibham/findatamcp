#!/usr/bin/env python3
"""LLM 路由评测 harness（全量 LLM 链路评测的最小可执行实现）。

测两件事，直击本次改造的价值点：
1. 路由首选命中率 —— 给 LLM 当前工具目录 + 自然语言任务，看它选的"第一个工具"
   是否落在期望集合。改造后(工具改名澄清、描述更清晰)应不低于基线。
2. 报错自纠命中率 —— 给 LLM 一个带 hint 的错误返回，看它能否据 hint 选对恢复工具
   (如 symbol_not_found → resolve_symbol)。直接衡量 error+hint 的价值。

用法:
    export ANTHROPIC_API_KEY=...
    python tests/eval/run_llm_eval.py --label after            # 当前分支
    git stash && git checkout main && python ... --label before # 基线(对比 A/B)

无 ANTHROPIC_API_KEY 时直接跳过(退出码 0)，便于 CI 安全引用。
scorecard 写到 tests/eval/scorecard_<label>.json。

注意: 真正的 A/B 需在不同 git checkout 各跑一次(目录/工具名随代码变化)，
本脚本只评测"当前 checkout 暴露的工具集"。
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import yaml
except ImportError:
    print("需要 pyyaml: pip install pyyaml --break-system-packages")
    sys.exit(0)

from tests._harness import tool_catalog  # noqa: E402

TRACES_FILE = Path(__file__).with_name("golden_traces.yaml")
DEFAULT_MODEL = "claude-sonnet-4-6"

ROUTING_PROMPT = """你是一个金融数据 Agent，可用工具如下(名称: 说明):

{catalog}

用户任务：{task}

只回答你**第一步**应该调用的**单个**工具名(从上面列表里选)，用 JSON 输出：
{{"tool": "<tool_name>"}}"""

RECOVERY_PROMPT = """你是一个金融数据 Agent，可用工具如下(名称: 说明):

{catalog}

你刚刚的一次工具调用返回了错误：
{error}

阅读其中的 hint，回答你**下一步**应调用哪个**单个**工具来修复，用 JSON 输出：
{{"tool": "<tool_name>"}}"""


def _ask_tool(client, model, prompt):
    msg = client.messages.create(
        model=model, max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    # 提取 JSON
    import re
    m = re.search(r'\{[^{}]*"tool"[^{}]*\}', text)
    if m:
        try:
            return json.loads(m.group(0)).get("tool", "").strip()
        except Exception:
            pass
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="after", help="scorecard 标签(如 before/after)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  未设置 ANTHROPIC_API_KEY，跳过 LLM 评测(退出码 0)。")
        return

    try:
        import anthropic
    except ImportError:
        print("需要 anthropic SDK: pip install anthropic --break-system-packages")
        return

    client = anthropic.Anthropic()
    catalog_dict = tool_catalog()
    catalog = "\n".join(f"- {n}: {d}" for n, d in sorted(catalog_dict.items()))
    traces = yaml.safe_load(TRACES_FILE.read_text())["traces"]

    results = []
    for tr in traces:
        if tr["kind"] == "recovery":
            prompt = RECOVERY_PROMPT.format(
                catalog=catalog, error=json.dumps(tr["error_payload"], ensure_ascii=False))
        else:
            prompt = ROUTING_PROMPT.format(catalog=catalog, task=tr["task"])
        picked = _ask_tool(client, args.model, prompt)
        hit = picked in tr["expected_first"]
        results.append({"id": tr["id"], "kind": tr["kind"], "task": tr["task"],
                        "picked": picked, "expected": tr["expected_first"], "hit": hit})
        print(f"[{'✓' if hit else '✗'}] {tr['id']:24s} picked={picked!r} expected={tr['expected_first']}")

    routing = [r for r in results if r["kind"] == "routing"]
    recovery = [r for r in results if r["kind"] == "recovery"]
    scorecard = {
        "label": args.label,
        "model": args.model,
        "tool_count": len(catalog_dict),
        "routing_hit_rate": round(sum(r["hit"] for r in routing) / max(len(routing), 1), 3),
        "recovery_hit_rate": round(sum(r["hit"] for r in recovery) / max(len(recovery), 1), 3),
        "overall_hit_rate": round(sum(r["hit"] for r in results) / max(len(results), 1), 3),
        "results": results,
    }
    out = Path(__file__).with_name(f"scorecard_{args.label}.json")
    out.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2))
    print(f"\n路由命中率 {scorecard['routing_hit_rate']} | 自纠命中率 "
          f"{scorecard['recovery_hit_rate']} | 总体 {scorecard['overall_hit_rate']}")
    print(f"scorecard → {out}")


if __name__ == "__main__":
    main()
