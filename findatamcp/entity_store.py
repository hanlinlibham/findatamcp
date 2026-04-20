"""
本地金融实体存储 - 基于 Tushare 数据 + pypinyin 拼音索引

启动时从 tushare 加载 A 股 + ETF 基金的基础信息到内存，
提供拼音搜索、代码搜索、名称搜索，零外部依赖。
"""

import re
import logging
from typing import Dict, Any, List, Optional
from pypinyin import lazy_pinyin, Style

logger = logging.getLogger(__name__)


class EntityStore:
    """内存实体存储，提供快速搜索"""

    def __init__(self):
        self._entities: List[Dict[str, Any]] = []
        self._code_index: Dict[str, Dict[str, Any]] = {}  # ts_code -> entity
        self._symbol_index: Dict[str, Dict[str, Any]] = {}  # 裸码 -> entity
        self._loaded = False

    async def load(self, api) -> int:
        """从 tushare 加载数据并构建索引"""
        entities = []

        # A 股
        try:
            df = api.pro.stock_basic(
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    name = row['name']
                    entities.append({
                        'code': row['ts_code'],
                        'symbol': row['symbol'],
                        'name': name,
                        'entity_type': 'stock',
                        'market': row['ts_code'].split('.')[-1],
                        'industry': row.get('industry', ''),
                        'area': row.get('area', ''),
                        'pinyin_initials': _pinyin_initials(name),
                        'pinyin_full': _pinyin_full(name),
                    })
                logger.info(f"  Loaded {len(df)} stocks")
        except Exception as e:
            logger.error(f"Failed to load stock_basic: {e}")

        # ETF / 场内基金
        try:
            fdf = api.pro.fund_basic(
                market='E',
                fields='ts_code,name,management,type,fund_type,list_date,status'
            )
            if fdf is not None and not fdf.empty:
                # 只保留上市中的
                fdf = fdf[fdf['status'] == 'L']
                for _, row in fdf.iterrows():
                    name = row['name']
                    ts_code = row['ts_code']
                    entities.append({
                        'code': ts_code,
                        'symbol': ts_code.split('.')[0],
                        'name': name,
                        'entity_type': 'fund',
                        'market': ts_code.split('.')[-1],
                        'industry': row.get('fund_type', ''),
                        'area': row.get('management', ''),
                        'pinyin_initials': _pinyin_initials(name),
                        'pinyin_full': _pinyin_full(name),
                    })
                logger.info(f"  Loaded {len(fdf)} funds (listed)")
        except Exception as e:
            logger.error(f"Failed to load fund_basic: {e}")

        # 构建索引
        self._entities = entities
        self._code_index = {e['code']: e for e in entities}
        self._symbol_index = {e['symbol']: e for e in entities}
        self._loaded = True
        logger.info(f"EntityStore ready: {len(entities)} entities")
        return len(entities)

    async def search_entities(
        self,
        keyword: str,
        entity_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索实体：支持拼音首字母、代码、名称"""
        if not self._loaded:
            return []

        keyword_lower = keyword.lower().strip()
        results = []

        for e in self._entities:
            if entity_type and e['entity_type'] != entity_type:
                continue

            # 精确代码匹配优先
            if keyword_lower == e['code'].lower() or keyword_lower == e['symbol']:
                results.insert(0, e)
                continue

            # 代码前缀
            if e['symbol'].startswith(keyword_lower) or e['code'].lower().startswith(keyword_lower):
                results.append(e)
                continue

            # 拼音首字母匹配
            if e['pinyin_initials'].startswith(keyword_lower):
                results.append(e)
                continue

            # 名称包含
            if keyword in e['name']:
                results.append(e)
                continue

            # 拼音全拼包含
            if keyword_lower in e['pinyin_full']:
                results.append(e)
                continue

            # 行业匹配
            if e.get('industry') and keyword in e['industry']:
                results.append(e)
                continue

        return results[:limit]

    async def get_entity_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """精确代码查询"""
        code = code.strip()
        # 先试精确匹配
        if code in self._code_index:
            return self._code_index[code]
        code_upper = code.upper()
        if code_upper in self._code_index:
            return self._code_index[code_upper]
        # 裸码匹配
        symbol = code.split('.')[0]
        if symbol in self._symbol_index:
            return self._symbol_index[symbol]
        return None

    async def get_stats(self) -> Dict[str, Any]:
        stocks = sum(1 for e in self._entities if e['entity_type'] == 'stock')
        funds = sum(1 for e in self._entities if e['entity_type'] == 'fund')
        return {
            'total': len(self._entities),
            'stocks': stocks,
            'funds': funds,
            'loaded': self._loaded,
        }

    def __repr__(self) -> str:
        return f"EntityStore(entities={len(self._entities)}, loaded={self._loaded})"


def _pinyin_initials(name: str) -> str:
    """提取拼音首字母，如 '平安银行' -> 'payh'"""
    try:
        return ''.join(lazy_pinyin(name, style=Style.FIRST_LETTER))
    except Exception:
        return ''


def _pinyin_full(name: str) -> str:
    """提取全拼，如 '平安银行' -> 'pinganyinhang'"""
    try:
        return ''.join(lazy_pinyin(name))
    except Exception:
        return ''
