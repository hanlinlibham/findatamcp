"""统一的指数代码解析与失败回退建议。

数据来源：
- 结构化 INDEX_ENTRIES：~90 条常用指数（宽基 / 风格 / 主题 / 申万行业 / 港美 / 债券），
  每条带 ts_code、官方名、别名、分类、data_source。
- EntityStore（运行时注入）：tushare 加载的 ~7.5k A 股 + ETF 基金。

对外 API：
- resolve_symbol(): 名称/别名/代码 → 候选条目（结构化）
- build_symbol_not_found(): 行情查询失败时的结构化响应
- lookup_by_code(): code → entry，供 market_data 决定 data_source 路由
- COMMON_INDICES: 向后兼容的 name→code 扁平 dict
"""

from typing import Any, Dict, List, Optional, Set


# ============================================================
# 结构化指数表
#
# data_source 取值：
#   "index_daily"  → 走 api.pro.index_daily（A 股全部指数 + 中证全债 + 中证转债等）
#   "index_global" → 走 api.pro.index_global（港美主流，代码无后缀）
#   "unavailable"  → tushare 不提供该数据源（中债登 CBA*.CS 系列）
# ============================================================
INDEX_ENTRIES: List[Dict[str, Any]] = [
    # ---------- A. 宽基指数 ----------
    {"code": "000001.SH", "name": "上证指数",  "aliases": ["上证综指", "上证综合", "上证综合指数"],          "category": "宽基", "data_source": "index_daily"},
    {"code": "399106.SZ", "name": "深证综指",  "aliases": ["深证综合", "深证综合指数"],                       "category": "宽基", "data_source": "index_daily"},
    {"code": "399001.SZ", "name": "深证成指",  "aliases": ["深成指", "深圳成指", "深证成份指数"],             "category": "宽基", "data_source": "index_daily"},
    {"code": "000016.SH", "name": "上证50",   "aliases": ["SSE50"],                                          "category": "宽基", "data_source": "index_daily"},
    {"code": "000010.SH", "name": "上证180",  "aliases": [],                                                  "category": "宽基", "data_source": "index_daily"},
    {"code": "000009.SH", "name": "上证380",  "aliases": [],                                                  "category": "宽基", "data_source": "index_daily"},
    {"code": "000300.SH", "name": "沪深300",  "aliases": ["HS300", "CSI300", "300指数"],                     "category": "宽基", "data_source": "index_daily"},
    {"code": "000510.SH", "name": "中证A500", "aliases": ["A500"],                                            "category": "宽基", "data_source": "index_daily"},
    {"code": "930050.CSI","name": "中证A50",  "aliases": ["A50"],                                             "category": "宽基", "data_source": "index_daily"},
    {"code": "000905.SH", "name": "中证500",  "aliases": ["CSI500", "500指数"],                              "category": "宽基", "data_source": "index_daily"},
    {"code": "000906.SH", "name": "中证800",  "aliases": ["CSI800"],                                          "category": "宽基", "data_source": "index_daily"},
    {"code": "000852.SH", "name": "中证1000", "aliases": ["CSI1000", "1000指数"],                            "category": "宽基", "data_source": "index_daily"},
    {"code": "932000.CSI","name": "中证2000", "aliases": ["CSI2000"],                                         "category": "宽基", "data_source": "index_daily"},
    {"code": "000985.CSI","name": "中证全指", "aliases": ["全指"],                                            "category": "宽基", "data_source": "index_daily"},
    {"code": "000688.SH", "name": "科创50",   "aliases": ["STAR50", "科创板50"],                              "category": "宽基", "data_source": "index_daily"},
    {"code": "000698.SH", "name": "科创100",  "aliases": [],                                                  "category": "宽基", "data_source": "index_daily"},
    {"code": "399006.SZ", "name": "创业板指", "aliases": ["创业板指数", "创业板", "GEM"],                     "category": "宽基", "data_source": "index_daily"},
    {"code": "399673.SZ", "name": "创业板50", "aliases": [],                                                  "category": "宽基", "data_source": "index_daily"},
    {"code": "399330.SZ", "name": "深证100",  "aliases": ["深100"],                                           "category": "宽基", "data_source": "index_daily"},
    {"code": "399303.SZ", "name": "国证2000","aliases": [],                                                   "category": "宽基", "data_source": "index_daily"},
    {"code": "899050.BJ", "name": "北证50",   "aliases": ["BSE50"],                                           "category": "宽基", "data_source": "index_daily"},

    # ---------- B. 风格/策略指数 ----------
    {"code": "000922.CSI", "name": "中证红利",  "aliases": ["红利", "红利指数"],            "category": "策略", "data_source": "index_daily"},
    {"code": "000015.SH",  "name": "上证红利",  "aliases": [],                              "category": "策略", "data_source": "index_daily"},
    {"code": "H30269.CSI", "name": "红利低波",  "aliases": ["中证红利低波"],                "category": "策略", "data_source": "index_daily"},
    {"code": "000919.CSI", "name": "300价值",  "aliases": ["沪深300价值"],                  "category": "风格", "data_source": "index_daily"},

    # ---------- C. 主流主题/行业指数 ----------
    {"code": "399997.SZ",  "name": "中证白酒",   "aliases": ["白酒指数", "白酒"],                "category": "主题", "data_source": "index_daily"},
    {"code": "000932.CSI", "name": "中证消费",   "aliases": ["消费指数"],                        "category": "主题", "data_source": "index_daily"},
    {"code": "399932.SZ",  "name": "800消费",   "aliases": ["中证800消费"],                     "category": "主题", "data_source": "index_daily"},
    {"code": "399933.SZ",  "name": "800医卫",   "aliases": ["中证800医卫", "800医药"],          "category": "主题", "data_source": "index_daily"},
    {"code": "399986.SZ",  "name": "中证银行",   "aliases": ["银行指数"],                        "category": "主题", "data_source": "index_daily"},
    {"code": "399967.SZ",  "name": "中证军工",   "aliases": ["军工指数"],                        "category": "主题", "data_source": "index_daily"},
    {"code": "399971.SZ",  "name": "中证传媒",   "aliases": ["传媒指数"],                        "category": "主题", "data_source": "index_daily"},
    {"code": "399975.SZ",  "name": "证券公司",   "aliases": ["证券指数", "中证证券", "券商指数"],"category": "主题", "data_source": "index_daily"},
    {"code": "399550.SZ",  "name": "央视50",    "aliases": [],                                  "category": "主题", "data_source": "index_daily"},
    {"code": "931865.CSI", "name": "中证半导",   "aliases": ["半导体指数", "半导体"],            "category": "主题", "data_source": "index_daily"},
    {"code": "931151.CSI", "name": "光伏产业",   "aliases": ["光伏指数", "光伏"],                "category": "主题", "data_source": "index_daily"},
    {"code": "399808.SZ",  "name": "中证新能",   "aliases": ["新能源指数", "新能源"],            "category": "主题", "data_source": "index_daily"},
    {"code": "930997.CSI", "name": "新能源车",   "aliases": ["新能源汽车", "新能源车指数"],      "category": "主题", "data_source": "index_daily"},
    {"code": "931071.CSI", "name": "人工智能",   "aliases": ["AI指数"],                          "category": "主题", "data_source": "index_daily"},
    {"code": "H30590.CSI", "name": "机器人",     "aliases": ["机器人指数"],                      "category": "主题", "data_source": "index_daily"},
    {"code": "980086.CNI", "name": "创新药",     "aliases": ["创新药指数"],                      "category": "主题", "data_source": "index_daily"},
    {"code": "H30217.CSI", "name": "医疗器械",   "aliases": ["医疗器械指数"],                    "category": "主题", "data_source": "index_daily"},
    {"code": "930743.CSI", "name": "中证生科",   "aliases": ["生命科技指数"],                    "category": "主题", "data_source": "index_daily"},
    {"code": "980017.SZ",  "name": "国证芯片",   "aliases": ["芯片指数", "芯片"],                "category": "主题", "data_source": "index_daily"},
    {"code": "931039.CSI", "name": "银行AH",     "aliases": [],                                  "category": "主题", "data_source": "index_daily"},
    {"code": "000807.CSI", "name": "食品饮料",   "aliases": [],                                  "category": "主题", "data_source": "index_daily"},

    # ---------- D. 申万一级行业（31 条）----------
    {"code": "801010.SI", "name": "农林牧渔(申万)",   "aliases": ["农林牧渔", "申万农林牧渔"],          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801030.SI", "name": "基础化工(申万)",   "aliases": ["基础化工", "申万化工"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801040.SI", "name": "钢铁(申万)",       "aliases": ["钢铁", "申万钢铁"],                  "category": "申万一级", "data_source": "index_daily"},
    {"code": "801050.SI", "name": "有色金属(申万)",   "aliases": ["有色金属", "有色", "申万有色"],      "category": "申万一级", "data_source": "index_daily"},
    {"code": "801080.SI", "name": "电子(申万)",       "aliases": ["电子板块", "申万电子"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801110.SI", "name": "家用电器(申万)",   "aliases": ["家用电器", "家电", "申万家电"],      "category": "申万一级", "data_source": "index_daily"},
    {"code": "801120.SI", "name": "食品饮料(申万)",   "aliases": ["食饮", "申万食品饮料"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801130.SI", "name": "纺织服饰(申万)",   "aliases": ["纺织服饰", "申万纺服"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801140.SI", "name": "轻工制造(申万)",   "aliases": ["轻工制造", "申万轻工"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801150.SI", "name": "医药生物(申万)",   "aliases": ["医药生物", "医药板块", "申万医药"],   "category": "申万一级", "data_source": "index_daily"},
    {"code": "801160.SI", "name": "公用事业(申万)",   "aliases": ["公用事业", "申万公用"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801170.SI", "name": "交通运输(申万)",   "aliases": ["交通运输", "交运", "申万交运"],      "category": "申万一级", "data_source": "index_daily"},
    {"code": "801180.SI", "name": "房地产(申万)",     "aliases": ["房地产", "地产", "申万地产"],        "category": "申万一级", "data_source": "index_daily"},
    {"code": "801200.SI", "name": "商贸零售(申万)",   "aliases": ["商贸零售", "申万商贸"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801210.SI", "name": "社会服务(申万)",   "aliases": ["社会服务", "申万社服"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801230.SI", "name": "综合(申万)",       "aliases": ["申万综合"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801710.SI", "name": "建筑材料(申万)",   "aliases": ["建筑材料", "建材", "申万建材"],      "category": "申万一级", "data_source": "index_daily"},
    {"code": "801720.SI", "name": "建筑装饰(申万)",   "aliases": ["建筑装饰", "建筑", "申万建筑"],      "category": "申万一级", "data_source": "index_daily"},
    {"code": "801730.SI", "name": "电力设备(申万)",   "aliases": ["电力设备", "申万电力设备"],          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801740.SI", "name": "国防军工(申万)",   "aliases": ["国防军工", "申万军工"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801750.SI", "name": "计算机(申万)",     "aliases": ["计算机", "申万计算机"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801760.SI", "name": "传媒(申万)",       "aliases": ["申万传媒"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801770.SI", "name": "通信(申万)",       "aliases": ["申万通信"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801780.SI", "name": "银行(申万)",       "aliases": ["申万银行"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801790.SI", "name": "非银金融(申万)",   "aliases": ["非银金融", "非银", "申万非银"],      "category": "申万一级", "data_source": "index_daily"},
    {"code": "801880.SI", "name": "汽车(申万)",       "aliases": ["申万汽车"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801890.SI", "name": "机械设备(申万)",   "aliases": ["机械设备", "申万机械"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801950.SI", "name": "煤炭(申万)",       "aliases": ["申万煤炭"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801960.SI", "name": "石油石化(申万)",   "aliases": ["石油石化", "申万石化"],              "category": "申万一级", "data_source": "index_daily"},
    {"code": "801970.SI", "name": "环保(申万)",       "aliases": ["申万环保"],                          "category": "申万一级", "data_source": "index_daily"},
    {"code": "801980.SI", "name": "美容护理(申万)",   "aliases": ["美容护理", "申万美护"],              "category": "申万一级", "data_source": "index_daily"},

    # ---------- E. 港股/美股（走 index_global，代码无后缀）----------
    {"code": "HSI",  "name": "恒生指数",       "aliases": ["恒指", "HangSeng"],                "category": "港股", "data_source": "index_global"},
    {"code": "SPX",  "name": "标普500",        "aliases": ["标普", "SP500", "S&P500"],         "category": "美股", "data_source": "index_global"},
    {"code": "IXIC", "name": "纳斯达克综合",   "aliases": ["纳指", "纳斯达克", "NASDAQ"],      "category": "美股", "data_source": "index_global"},
    {"code": "DJI",  "name": "道琼斯工业",     "aliases": ["道指", "道琼斯", "DOW"],           "category": "美股", "data_source": "index_global"},

    # ---------- F. 债券指数 ----------
    {"code": "H11001.CSI",  "name": "中证全债",            "aliases": ["中证综合债"],                                  "category": "债券",  "data_source": "index_daily"},
    {"code": "000832.CSI",  "name": "中证转债",            "aliases": ["中证转债指数", "转债指数"],                    "category": "债券",  "data_source": "index_daily"},
    # 以下中债登 CBA 系列：tushare 不提供数据源，仅作为"识别"用，命中时给明确错误
    {"code": "CBA00301.CS", "name": "中债新综合财富指数",  "aliases": ["中债新综合财富", "中债综合财富", "中债新综合"], "category": "债券",  "data_source": "unavailable"},
    {"code": "CBA00101.CS", "name": "中债总财富指数",      "aliases": ["中债总财富", "中债-总财富(总值)指数"],         "category": "债券",  "data_source": "unavailable"},
    {"code": "CBA00601.CS", "name": "中债国债总财富指数",  "aliases": ["中债国债总财富"],                              "category": "债券",  "data_source": "unavailable"},
    {"code": "CBA02701.CS", "name": "中债信用债总财富指数","aliases": ["中债信用债总财富"],                            "category": "债券",  "data_source": "unavailable"},
]


# ============================================================
# 派生索引（启动时构建一次）
# ============================================================
_NAME_TO_ENTRY: Dict[str, Dict[str, Any]] = {}
_CODE_TO_ENTRY: Dict[str, Dict[str, Any]] = {}


def _build_indices() -> None:
    for e in INDEX_ENTRIES:
        _CODE_TO_ENTRY[e["code"]] = e
        _NAME_TO_ENTRY.setdefault(e["name"], e)
        for a in e.get("aliases", []):
            _NAME_TO_ENTRY.setdefault(a, e)


_build_indices()


# 向后兼容：name → code 扁平表
COMMON_INDICES: Dict[str, str] = {n: e["code"] for n, e in _NAME_TO_ENTRY.items()}


# ============================================================
# 对外查询 API
# ============================================================
def lookup_by_code(code: str) -> Optional[Dict[str, Any]]:
    """按 ts_code 精确查找指数条目"""
    if not code:
        return None
    return _CODE_TO_ENTRY.get(code) or _CODE_TO_ENTRY.get(code.upper())


def lookup_by_name(name: str) -> Optional[Dict[str, Any]]:
    """按名称/别名精确查找指数条目"""
    if not name:
        return None
    return _NAME_TO_ENTRY.get(name.strip())


def _candidate_from_entry(e: Dict[str, Any], matched_name: str) -> Dict[str, Any]:
    return {
        "code": e["code"],
        "name": e["name"],
        "matched_as": matched_name if matched_name != e["name"] else None,
        "entity_type": "index",
        "category": e.get("category"),
        "data_source": e.get("data_source"),
    }


def _match_index_entries(keyword: str) -> List[Dict[str, Any]]:
    """从 INDEX_ENTRIES 匹配（精确 → 子串）"""
    if not keyword:
        return []
    key = keyword.strip()
    if not key:
        return []
    results: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    # 精确（名 / 别名 / 代码）
    e = lookup_by_name(key)
    if e:
        results.append(_candidate_from_entry(e, key))
        seen.add(e["code"])
    e = lookup_by_code(key)
    if e and e["code"] not in seen:
        results.append(_candidate_from_entry(e, key))
        seen.add(e["code"])

    # 子串（含 / 被含）
    for name, entry in _NAME_TO_ENTRY.items():
        if entry["code"] in seen:
            continue
        if key in name or name in key:
            results.append(_candidate_from_entry(entry, name))
            seen.add(entry["code"])
    return results


async def resolve_symbol(keyword: str, db, limit: int = 5) -> List[Dict[str, Any]]:
    """统一解析名称→代码：INDEX_ENTRIES（指数）+ EntityStore（A股 + ETF）"""
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for item in _match_index_entries(keyword):
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
        for ent in entities:
            code = ent.get("code")
            if not code or code in seen:
                continue
            out.append({
                "code": code,
                "name": ent.get("name", ""),
                "entity_type": ent.get("entity_type", ""),
                "market": ent.get("market", ""),
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
    """行情查询失败时的结构化响应"""
    candidates = await resolve_symbol(ts_code, db, limit=5)
    if not candidates and original_input and original_input != ts_code:
        candidates = await resolve_symbol(original_input, db, limit=5)

    # 如果候选里有 unavailable，给一个更明确的提示
    has_unavailable = any(c.get("data_source") == "unavailable" for c in candidates)
    if has_unavailable:
        suggestion = (
            "候选指数中含 tushare 不提供的数据源（如中债登 CBA*.CS 系列）。"
            "如需中债指数行情，请改用 wind / iFinD / 中债登官方数据接口。"
        )
    else:
        suggestion = (
            "未在历史行情库中找到该代码。"
            "请先调用 resolve_symbol 或 search_financial_entity 解析为标准 ts_code "
            "（如 000300.SH / 000832.CSI / 801080.SI / HSI）后重试。"
        )

    return {
        "success": False,
        "error": "symbol_not_found",
        "ts_code": ts_code,
        "original_input": original_input,
        "suggestion": suggestion,
        "did_you_mean": candidates,
    }
