"""搜索查询工具

提供金融实体搜索相关的MCP工具，包括：
- search_financial_entity: 搜索金融实体（使用后端API）
- get_entity_by_code: 根据代码查询实体
- search_stocks: 搜索股票（使用金融数据API）
"""

from typing import Dict, Any, Optional
import httpx
import pandas as pd
from datetime import datetime
from fastmcp import FastMCP

from ..config import config
from ..entity_store import EntityStore
from ..utils.tushare_api import TushareAPI


def register_search_tools(mcp: FastMCP, api: TushareAPI, db: EntityStore):
    """注册搜索查询工具"""

    @mcp.tool(tags={"搜索"})
    async def search_financial_entity(
        keyword: str,
        entity_type: Optional[str] = None,
        market: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        搜索金融实体（股票、基金）- 使用本地数据库

        支持多种搜索方式：
        - 拼音首字母：payh -> 平安银行
        - 股票代码：000001 -> 平安银行
        - 名称搜索：平安 -> 平安银行、平安保险等

        Args:
            keyword: 搜索关键词（支持拼音首字母、代码、名称）
            entity_type: 实体类型（stock=股票, fund=基金），可选
            market: 市场筛选（SH=上海, SZ=深圳, BJ=北京, OF=场外），可选
            limit: 返回数量，默认10，最大100

        Returns:
            包含实体列表的字典，每个实体包含：
            - code: 实体代码（如 000001.SZ）
            - name: 实体名称（如 平安银行）
            - entity_type: 实体类型（stock/fund）
            - market: 市场代码
            - pinyin_initials: 拼音首字母

        Examples:
            >>> # 按名称搜索
            >>> result = await search_financial_entity("平安")
            >>> # 按拼音首字母搜索
            >>> result = await search_financial_entity("payh")
            >>> # 只搜索股票
            >>> result = await search_financial_entity("银行", entity_type="stock")
            >>> # 只搜索沪市股票
            >>> result = await search_financial_entity("科技", entity_type="stock", market="SH")
        """
        try:
            entities = await db.search_entities(
                keyword=keyword,
                entity_type=entity_type,
                limit=min(limit, 100)  # 限制最大值
            )

            return {
                "success": True,
                "total": len(entities),
                "entities": entities,
                "query": keyword,
                "timestamp": datetime.now().isoformat()
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "请求超时，后端服务可能未启动",
                "keyword": keyword
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": f"无法连接到后端服务: {config.BACKEND_API_URL}",
                "keyword": keyword
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"搜索异常: {str(e)}",
                "keyword": keyword
            }

    @mcp.tool(tags={"搜索"})
    async def get_entity_by_code(code: str) -> Dict[str, Any]:
        """
        根据代码精确查询金融实体

        Args:
            code: 实体代码（支持带后缀如 000001.SZ 或不带后缀如 000001）

        Returns:
            实体详细信息，包含：
            - code: 完整代码
            - name: 实体名称
            - entity_type: 类型（stock/fund）
            - market: 市场
            - pinyin_full: 完整拼音
            - pinyin_initials: 拼音首字母

        Examples:
            >>> result = await get_entity_by_code("000001.SZ")
            >>> print(result["entity"]["name"])  # 平安银行
            >>> result = await get_entity_by_code("000001")  # 自动添加后缀
        """
        try:
            entity = await db.get_entity_by_code(code)

            if entity:
                return {
                    "success": True,
                    "entity": entity,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到代码为 {code} 的实体",
                    "code": code
                }
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "请求超时，后端服务可能未启动",
                "code": code
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": f"无法连接到后端服务: {config.BACKEND_API_URL}",
                "code": code
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"查询异常: {str(e)}",
                "code": code
            }

    @mcp.tool(tags={"搜索"})
    async def search_stocks(keyword: str = "", limit: int = 10, query: str = "") -> Dict[str, Any]:
        """
        搜索股票和指数（根据名称或代码）

        支持 A 股、港股、美股、各类指数。

        Args:
            keyword: 搜索关键词（名称或代码，如"银行"、"沪深300"、"000001"、"腾讯"、"Apple"）。也可用 query 参数名
            limit: 返回结果数量限制，默认10

        Returns:
            stocks: 匹配的 A 股列表
            indices: 匹配的指数列表
            hk_stocks: 匹配的港股列表
            us_stocks: 匹配的美股列表

        Examples:
            >>> result = await search_stocks("腾讯")
            >>> for hk in result["hk_stocks"]:
            ...     print(f"{hk['name']} ({hk['ts_code']})")
        """
        try:
            # 兼容 query 别名
            keyword = keyword or query
            if not keyword:
                return {"success": False, "error": "请提供搜索关键词（参数名: keyword 或 query）"}

            if not api.is_available():
                return {
                    "success": False,
                    "error": "需要 Pro 数据权限",
                    "keyword": keyword
                }

            # 搜索 A 股
            df = api.pro.stock_basic(
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market'
            )

            stock_results = []
            if not df.empty:
                matched = df[
                    df['name'].str.contains(keyword, case=False, na=False) |
                    df['symbol'].str.contains(keyword, case=False, na=False) |
                    df['ts_code'].str.contains(keyword, case=False, na=False)
                ]
                stock_results = matched.head(limit).to_dict('records')

            # 搜索指数
            index_results = []
            try:
                idx_df = api.pro.index_basic(fields='ts_code,name,market,publisher,category')
                if idx_df is not None and not idx_df.empty:
                    idx_matched = idx_df[
                        idx_df['name'].str.contains(keyword, case=False, na=False) |
                        idx_df['ts_code'].str.contains(keyword, case=False, na=False)
                    ]
                    for _, row in idx_matched.head(limit).iterrows():
                        index_results.append({
                            "ts_code": row['ts_code'],
                            "name": row['name'],
                            "market": row.get('market', ''),
                            "publisher": row.get('publisher', ''),
                            "category": row.get('category', ''),
                            "asset_type": "index"
                        })
            except Exception:
                pass

            # 搜索港股
            hk_results = []
            try:
                hk_df = api.pro.hk_basic(fields='ts_code,name,enname,market,list_status')
                if hk_df is not None and not hk_df.empty:
                    hk_matched = hk_df[
                        hk_df['name'].str.contains(keyword, case=False, na=False) |
                        hk_df['ts_code'].str.contains(keyword, case=False, na=False) |
                        hk_df['enname'].str.contains(keyword, case=False, na=False)
                    ]
                    for _, row in hk_matched.head(limit).iterrows():
                        hk_results.append({
                            "ts_code": row['ts_code'],
                            "name": row['name'],
                            "enname": row.get('enname', ''),
                            "market": row.get('market', ''),
                            "list_status": row.get('list_status', ''),
                            "asset_type": "hk"
                        })
            except Exception:
                pass

            # 搜索美股
            us_results = []
            try:
                us_df = api.pro.us_basic(fields='ts_code,name,enname,classify')
                if us_df is not None and not us_df.empty:
                    us_matched = us_df[
                        us_df['name'].str.contains(keyword, case=False, na=False) |
                        us_df['ts_code'].str.contains(keyword, case=False, na=False) |
                        us_df['enname'].str.contains(keyword, case=False, na=False)
                    ]
                    for _, row in us_matched.head(limit).iterrows():
                        _name = row['name']
                        _enname = row.get('enname', '')
                        # name 可能为 NaN，fallback 到 enname
                        if pd.isna(_name):
                            _name = _enname if not pd.isna(_enname) else row['ts_code']
                        us_results.append({
                            "ts_code": row['ts_code'],
                            "name": _name,
                            "enname": _enname if not pd.isna(_enname) else '',
                            "classify": row.get('classify', ''),
                            "asset_type": "us"
                        })
            except Exception:
                pass

            total_count = len(stock_results) + len(index_results) + len(hk_results) + len(us_results)
            if total_count > 0:
                return {
                    "success": True,
                    "keyword": keyword,
                    "count": total_count,
                    "stocks": stock_results,
                    "indices": index_results,
                    "hk_stocks": hk_results,
                    "us_stocks": us_results,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "未找到匹配的股票或指数",
                    "keyword": keyword
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"搜索异常: {str(e)}",
                "keyword": keyword
            }