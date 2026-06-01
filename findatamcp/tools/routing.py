"""
工具路由地图（self-describing routing graph）

面向 LLM 消费者：把"工具之间靠实体类型(ts_code / codes / sector / index_code ...)
连接"的隐式知识，沉淀成一份**唯一声明式事实源** ROUTING_MAP，再三处复用：

1. 运行时注入 —— attach_next_steps(result, tool_name)：按 param_from 从本次返回里
   预填下游工具的实参（如把 candidates[0].code 填进 get_historical_data 的 ts_code），
   挂到返回的 `next_steps` 字段。纯增量，向后兼容。
2. 全局视图 —— get_routing_map()：让 LLM 一次看清"从某工具能往哪走"，
   无需常驻全部工具描述。
3. 评测驱动 —— 静态测试断言图的完整性（无悬空边、无孤儿工具）。

实体类型词表：
  keyword(自然语言名) / ts_code(个股/基金/指数代码) / codes(ts_code 列表) /
  index_code / sector(行业名) / trade_date / report_period / macro(宏观,终点)
"""

import re
from typing import Any, Dict, List, Optional

# ── param_from 路径解析 ───────────────────────────────────────────────
# 支持： name | name[i] | name[a:b] | name[]  (后者把剩余路径在 list 上逐元素 pluck)
_TOKEN = re.compile(r'^([A-Za-z_][\w]*)(?:\[([^\]]*)\])?$')


def _resolve_path(obj: Any, path: str) -> Any:
    """从 result 里按 path 取值，失败返回 None（防御式，绝不抛错）。"""
    try:
        cur = obj
        tokens = path.split('.')
        for i, tok in enumerate(tokens):
            m = _TOKEN.match(tok)
            if not m:
                return None
            name, idx = m.group(1), m.group(2)
            cur = cur[name] if isinstance(cur, dict) else getattr(cur, name)
            if idx is None:
                continue
            if idx == '':  # name[].field —— 在 list 上逐元素取剩余路径
                if not isinstance(cur, list):
                    return None
                rest = '.'.join(tokens[i + 1:])
                if rest:
                    return [_resolve_path(el, rest) for el in cur]
                return cur
            if ':' in idx:  # 切片 name[a:b]
                a, _, b = idx.partition(':')
                cur = cur[(int(a) if a.strip() else None):(int(b) if b.strip() else None)]
            else:  # 下标 name[i]
                cur = cur[int(idx)]
        return cur
    except Exception:
        return None


# ── 路由地图（唯一事实源）────────────────────────────────────────────
# 每个工具： produces(产出的可路由实体) / consumes(需要的实体) /
#            next_steps[{intent, tool, param_from?, note?}]
# param_from: {下游参数名: 本次 result 的取值路径}
ROUTING_MAP: Dict[str, Dict[str, Any]] = {
    # ── 入口漏斗：keyword → ts_code ──
    "resolve_symbol": {
        "produces": ["ts_code"],
        "consumes": ["keyword"],
        "role": "entry",
        "next_steps": [
            {"intent": "看历史走势/K线", "tool": "get_historical_data",
             "param_from": {"ts_code": "candidates[0].code"}},
            {"intent": "看最新收盘价", "tool": "get_latest_daily_close",
             "param_from": {"ts_code": "candidates[0].code"}},
            {"intent": "看综合快照", "tool": "get_stock_data",
             "param_from": {"ts_code": "candidates[0].code"}},
            {"intent": "看财务比率(ROE/毛利率等)", "tool": "get_financial_ratios",
             "param_from": {"ts_code": "candidates[0].code"}},
        ],
    },
    "search_financial_entity": {
        "produces": ["ts_code"], "consumes": ["keyword"], "role": "entry",
        "next_steps": [
            {"intent": "看个股综合数据", "tool": "get_stock_data"},
            {"intent": "看基本信息", "tool": "get_basic_info"},
            {"intent": "看基金概览", "tool": "get_fund_data"},
        ],
    },
    "search_stocks": {
        "produces": ["ts_code"], "consumes": ["keyword"], "role": "entry",
        "next_steps": [
            {"intent": "看历史走势", "tool": "get_historical_data"},
            {"intent": "看综合快照", "tool": "get_stock_data"},
        ],
    },
    "get_entity_by_code": {
        "produces": ["ts_code"], "consumes": ["ts_code"], "role": "entry",
        "next_steps": [
            {"intent": "看综合快照", "tool": "get_stock_data"},
            {"intent": "看基本信息", "tool": "get_basic_info"},
        ],
    },

    # ── codes[] 生产者 → 多股工具 ──
    "get_sector_top_stocks": {
        "produces": ["codes"], "consumes": ["sector"],
        "next_steps": [
            {"intent": "批量算区间涨跌幅", "tool": "get_batch_pct_chg",
             "param_from": {"stock_codes": "codes[:10]"}},
            {"intent": "相关性/Beta 分析", "tool": "compute_correlation",
             "param_from": {"stock_codes": "codes[:10]"}},
            {"intent": "看某只龙头最新价", "tool": "get_latest_daily_close"},
        ],
    },
    "get_index_weight": {
        "produces": ["codes"], "consumes": ["index_code"],
        "next_steps": [
            {"intent": "批量算成分股涨跌", "tool": "get_batch_pct_chg",
             "note": "用 constituents[].con_code 作为 stock_codes（建议取前若干只）"},
            {"intent": "成分股相关性", "tool": "compute_correlation",
             "note": "用 constituents[].con_code 作为 stock_codes"},
            {"intent": "看指数估值水平", "tool": "get_index_valuation"},
        ],
    },
    "get_industry_overview": {
        "produces": ["codes", "sector"], "consumes": ["sector"],
        "next_steps": [
            {"intent": "查该行业龙头股", "tool": "get_sector_top_stocks"},
            {"intent": "批量算成分涨跌", "tool": "get_batch_pct_chg",
             "note": "用成分股 code 列表作为 stock_codes"},
        ],
    },

    # ── 市场扫描（无入参）→ 产出 ts_code 列表 ──
    "get_market_summary": {
        "produces": [], "consumes": [],
        "next_steps": [
            {"intent": "看涨跌幅排行", "tool": "get_market_extremes"},
            {"intent": "看龙虎榜异动", "tool": "get_top_list"},
        ],
    },
    "get_market_extremes": {
        "produces": ["ts_code"], "consumes": [],
        "next_steps": [
            {"intent": "看榜上个股最新价", "tool": "get_latest_daily_close",
             "note": "用 top_gainers[].ts_code / top_losers[].ts_code"},
            {"intent": "看榜上个股走势", "tool": "get_historical_data",
             "note": "用 top_gainers[].ts_code"},
        ],
    },
    "get_top_list": {
        "produces": ["ts_code"], "consumes": ["trade_date"],
        "next_steps": [
            {"intent": "看上榜个股综合数据", "tool": "get_stock_data",
             "note": "用 data[].ts_code"},
        ],
    },
    "get_batch_pct_chg": {
        "produces": [], "consumes": ["codes"],
        "next_steps": [
            {"intent": "做相关性/Beta", "tool": "compute_correlation"},
        ],
    },

    # ── ts_code 中央枢纽：行情/财务/深度 ──
    "get_stock_data": {
        "produces": [], "consumes": ["ts_code"],
        "next_steps": [
            {"intent": "看完整历史K线", "tool": "get_historical_data",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看资金流向", "tool": "get_moneyflow",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看财务比率(ROE等)", "tool": "get_financial_ratios",
             "param_from": {"ts_code": "ts_code"}},
        ],
    },
    "get_latest_daily_close": {
        "produces": [], "consumes": ["ts_code"],
        "next_steps": [
            {"intent": "看历史走势", "tool": "get_historical_data",
             "param_from": {"ts_code": "ts_code"}},
        ],
    },
    "get_historical_data": {
        "produces": [], "consumes": ["ts_code"],
        "next_steps": [
            {"intent": "做深度量化分析(技术/风险)", "tool": "analyze_stock_performance",
             "param_from": {"stock_codes": "ts_code"}},
        ],
    },
    "get_basic_info": {
        "produces": [], "consumes": ["ts_code"],
        "next_steps": [
            {"intent": "看核心财务科目(金额)", "tool": "get_financial_summary",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看财务比率(ROE等)", "tool": "get_financial_ratios",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看利润表", "tool": "get_income_statement",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看业绩预告", "tool": "get_forecast",
             "param_from": {"ts_code": "ts_code"}},
        ],
    },
    "get_financial_summary": {
        "produces": [], "consumes": ["ts_code"],
        "next_steps": [
            {"intent": "看完整利润表", "tool": "get_income_statement",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看资产负债表", "tool": "get_balance_sheet",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看现金流量表", "tool": "get_cashflow_statement",
             "param_from": {"ts_code": "ts_code"}},
        ],
    },

    # ── 宏观孤岛：summary → 单项下钻 ──
    "get_macro_summary": {
        "produces": ["macro"], "consumes": [],
        "next_steps": [
            {"intent": "看GDP序列", "tool": "get_gdp_data"},
            {"intent": "看CPI序列", "tool": "get_cpi_data"},
            {"intent": "看PMI序列", "tool": "get_pmi_data"},
            {"intent": "看货币供应M2", "tool": "get_money_supply"},
            {"intent": "看利率LPR/SHIBOR", "tool": "get_interest_rates"},
        ],
    },

    # ── 基金 ──
    "get_fund_data": {
        "produces": [], "consumes": ["ts_code"],
        "next_steps": [
            {"intent": "看净值曲线", "tool": "get_fund_nav",
             "param_from": {"ts_code": "ts_code"}},
            {"intent": "看重仓持仓", "tool": "get_fund_portfolio",
             "param_from": {"ts_code": "ts_code"}},
        ],
    },
}


def attach_next_steps(result: Any, tool_name: str) -> Any:
    """把 ROUTING_MAP 里该工具的 next_steps 注入 result（就地，纯增量）。

    - 仅当 result 是 dict 且该工具成功(success != False)时注入。
    - param_from 能从本次 result 解析出值时，预填进 step.params。
    - 解析不到的参数静默跳过（不塞 None），保证 next_steps 干净可执行。
    """
    if not isinstance(result, dict):
        return result
    if result.get("success") is False:
        return result
    spec = ROUTING_MAP.get(tool_name)
    if not spec:
        return result

    steps: List[Dict[str, Any]] = []
    for edge in spec.get("next_steps", []):
        step: Dict[str, Any] = {"intent": edge["intent"], "tool": edge["tool"]}
        params: Dict[str, Any] = {}
        for pname, path in edge.get("param_from", {}).items():
            val = _resolve_path(result, path)
            if val is not None and val != [] and val != "":
                params[pname] = val
        if params:
            step["params"] = params
        if edge.get("note"):
            step["note"] = edge["note"]
        steps.append(step)

    if steps:
        result["next_steps"] = steps
    return result


def get_routing_map_data(tool_name: Optional[str] = None) -> Dict[str, Any]:
    """返回 LLM 友好的路由地图（compact：去掉 param_from 内部细节）。

    Args:
        tool_name: 指定则只返回该工具的出边；否则返回全图 + 实体流概览。
    """
    def _compact(name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "produces": spec.get("produces", []),
            "consumes": spec.get("consumes", []),
            "next_steps": [
                {k: v for k, v in s.items() if k in ("intent", "tool", "note")}
                for s in spec.get("next_steps", [])
            ],
        }

    if tool_name:
        spec = ROUTING_MAP.get(tool_name)
        if not spec:
            return {"tool": tool_name, "found": False,
                    "available": sorted(ROUTING_MAP.keys())}
        return {"tool": tool_name, "found": True, **_compact(tool_name, spec)}

    return {
        "entity_flow": (
            "keyword --[resolve_symbol/search_*]--> ts_code "
            "--[行情/财务/业绩/深度]--> 分析; "
            "sector/index --[get_sector_top_stocks/get_index_weight]--> codes[] "
            "--[get_batch_pct_chg/analyze_price_correlation]--> 多股分析; "
            "macro 为自洽孤岛"
        ),
        "tools": {name: _compact(name, spec) for name, spec in ROUTING_MAP.items()},
        "count": len(ROUTING_MAP),
    }
