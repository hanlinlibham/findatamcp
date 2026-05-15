"""统一的代码解析与"did you mean"建议。

提供：
- COMMON_INDICES: EntityStore 未覆盖的常用指数表（债券指数 / 跨市场指数等）
- resolve_symbol(): 先查常用指数表，再回落到 EntityStore（A股 + ETF）
- build_symbol_not_found(): 行情查询失败时的结构化响应，附带候选代码
"""

from typing import Any, Dict, List, Optional, Set


COMMON_INDICES: Dict[str, str] = {
    "中债新综合财富指数": "CBA00301.CS",
    "中债新综合财富": "CBA00301.CS",
    "中债综合财富": "CBA00301.CS",
    "中债-总财富(总值)指数": "CBA00101.CS",
    "中债总财富": "CBA00101.CS",
    "中债总财富指数": "CBA00101.CS",
    "中债信用债总财富": "CBA02701.CS",
    "中债国债总财富": "CBA00601.CS",
    "上证指数": "000001.SH",
    "上证综指": "000001.SH",
    "深证成指": "399001.SZ",
    "创业板指": "399006.SZ",
    "科创50": "000688.SH",
    "沪深300": "000300.SH",
    "中证500": "000905.SH",
    "中证1000": "000852.SH",
    "中证转债": "000832.SH",
    "中证转债指数": "000832.SH",
    "中证全债": "H11001.CSI",
    "国证2000": "399303.SZ",
    "恒生指数": "HSI.HI",
    "恒生科技": "HSTECH.HI",
    "标普500": "SPX.GI",
    "纳斯达克": "IXIC.GI",
    "纳斯达克综合": "IXIC.GI",
    "道琼斯": "DJI.GI",
    "道琼斯工业": "DJI.GI",
}


def _match_common_indices(keyword: str) -> List[Dict[str, str]]:
    """从常用指数表匹配（精确 + 子串）"""
    if not keyword:
        return []
    key = keyword.strip()
    if not key:
        return []
    results: List[Dict[str, str]] = []
    seen: Set[str] = set()
    if key in COMMON_INDICES:
        code = COMMON_INDICES[key]
        results.append({"code": code, "name": key, "entity_type": "index"})
        seen.add(code)
    for name, code in COMMON_INDICES.items():
        if name == key or code in seen:
            continue
        if key in name or name in key:
            results.append({"code": code, "name": name, "entity_type": "index"})
            seen.add(code)
    return results


async def resolve_symbol(keyword: str, db, limit: int = 5) -> List[Dict[str, Any]]:
    """统一解析名称→代码：常用指数 > EntityStore"""
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for item in _match_common_indices(keyword):
        if item["code"] in seen:
            continue
        out.append(item)
        seen.add(item["code"])
        if len(out) >= limit:
            return out

    if db is not None:
        try:
            entities = await db.search_entities(keyword=keyword, limit=limit)
        except Exception:
            entities = []
        for e in entities:
            code = e.get("code")
            if not code or code in seen:
                continue
            out.append({
                "code": code,
                "name": e.get("name", ""),
                "entity_type": e.get("entity_type", ""),
                "market": e.get("market", ""),
            })
            seen.add(code)
            if len(out) >= limit:
                break
    return out


async def build_symbol_not_found(
    ts_code: str,
    db,
    original_input: Optional[str] = None,
) -> Dict[str, Any]:
    """行情查询失败时的结构化响应，附带候选代码"""
    candidates = await resolve_symbol(ts_code, db, limit=5)
    if not candidates and original_input and original_input != ts_code:
        candidates = await resolve_symbol(original_input, db, limit=5)

    return {
        "success": False,
        "error": "symbol_not_found",
        "ts_code": ts_code,
        "original_input": original_input,
        "suggestion": (
            "未在历史行情库中找到该代码。"
            "请先调用 resolve_symbol 或 search_financial_entity 解析为标准 ts_code "
            "（如 600519.SH / 000832.SH / CBA00301.CS）后重试。"
        ),
        "did_you_mean": candidates,
    }
