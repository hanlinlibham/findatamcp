"""大数据文件存储管理器

当工具返回数据超过阈值时，将数据存为文件并返回下载 URL。
- .jsonl: 行式 JSON，供下游（AG Grid 等）渲染；日期/代码列强制字符串化、NaN → null
- .json:  整体 JSON 数组，MCP 资源端点回读用
- schema: 列语义 sidecar，{col: {"type": date|string|number|bool}}
"""

import os
import re
import json
import math
import asyncio
import logging
from uuid import uuid4
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("/tmp/tushare_mcp_data")
FILE_TTL_HOURS = 24
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "http://39.96.218.64:8111")

# 列名启发式：日期/时间语义
_DATE_COL_RE = re.compile(r"date|time|^dt_|_dt$", re.I)
# 列名启发式：标识符类（证券代码/ID）—— 强制 string 防止被当 number
_ID_COL_RE = re.compile(r"code|symbol|^id$|_id$|ts_code", re.I)
# 合集：这些列在 JSONL 里强制字符串化
_FORCE_STR_COL_RE = re.compile(
    r"date|time|^dt_|_dt$|code|symbol|^id$|_id$|ts_code", re.I
)


def _is_force_str_col(name: str) -> bool:
    return bool(_FORCE_STR_COL_RE.search(name))


def _is_date_col(name: str) -> bool:
    return bool(_DATE_COL_RE.search(name))


def _is_id_col(name: str) -> bool:
    return bool(_ID_COL_RE.search(name))


def _normalize_value(value: Any, force_str: bool) -> Any:
    """JSONL 类型规范化：NaN/None → null；日期/代码列 → str；其他保持原类型。"""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if force_str:
        return str(value)
    return value


def _infer_col_type(col_name: str, rows: List[Dict[str, Any]]) -> str:
    """按列名启发式 + 首个非空值类型推断列语义。返回 date|string|number|bool。"""
    if _is_date_col(col_name):
        return "date"
    if _is_id_col(col_name):
        return "string"
    # 列名无提示，看值
    for row in rows:
        v = row.get(col_name)
        if v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, (int, float)):
            return "number"
        if isinstance(v, (datetime, date)):
            return "date"
        return "string"
    return "string"  # 全空列保守判为 string


def infer_schema(rows: List[Dict[str, Any]], columns: List[str]) -> Dict[str, Dict[str, str]]:
    """生成列 schema：{col: {"type": ...}}。"""
    return {c: {"type": _infer_col_type(c, rows)} for c in columns}


@dataclass
class DataFileMeta:
    data_id: str
    tool_name: str
    query_params: Dict[str, Any]
    total_rows: int
    columns: List[str]
    jsonl_path: str
    json_path: str
    created_at: str
    expires_at: str
    schema: Dict[str, Dict[str, str]] = field(default_factory=dict)


class DataFileStore:
    _instance: Optional["DataFileStore"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._index: Dict[str, DataFileMeta] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"DataFileStore initialized, dir={DATA_DIR}")

    def store(
        self,
        rows: List[Dict[str, Any]],
        tool_name: str,
        query_params: Dict[str, Any],
    ) -> DataFileMeta:
        data_id = uuid4().hex[:12]
        now = datetime.now()
        expires = now + timedelta(hours=FILE_TTL_HOURS)

        jsonl_path = str(DATA_DIR / f"{data_id}.jsonl")
        json_path = str(DATA_DIR / f"{data_id}.json")

        columns = list(rows[0].keys()) if rows else []
        force_str = {c for c in columns if _is_force_str_col(c)}
        schema = infer_schema(rows, columns)

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for row in rows:
                normalized = {
                    k: _normalize_value(v, k in force_str)
                    for k, v in row.items()
                }
                f.write(json.dumps(normalized, ensure_ascii=False, default=str))
                f.write("\n")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, default=str)

        meta = DataFileMeta(
            data_id=data_id,
            tool_name=tool_name,
            query_params=query_params,
            total_rows=len(rows),
            columns=columns,
            jsonl_path=jsonl_path,
            json_path=json_path,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            schema=schema,
        )
        self._index[data_id] = meta
        logger.info(f"Stored {len(rows)} rows as {data_id} ({tool_name})")
        return meta

    def get(self, data_id: str) -> Optional[DataFileMeta]:
        meta = self._index.get(data_id)
        if meta is None:
            return None
        if datetime.now() > datetime.fromisoformat(meta.expires_at):
            self._remove(data_id)
            return None
        return meta

    def _remove(self, data_id: str):
        meta = self._index.pop(data_id, None)
        if meta:
            for p in (meta.jsonl_path, meta.json_path):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def cleanup_expired(self):
        now = datetime.now()
        expired = [
            did for did, m in self._index.items()
            if now > datetime.fromisoformat(m.expires_at)
        ]
        for did in expired:
            self._remove(did)
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired data files")

    async def start_cleanup_loop(self):
        if self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("DataFileStore cleanup loop started")

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(3600)
            self.cleanup_expired()

    def get_download_urls(self, data_id: str) -> Dict[str, str]:
        base = SERVER_BASE_URL.rstrip("/")
        return {
            "jsonl": f"{base}/data/{data_id}.jsonl",
            "json": f"{base}/data/{data_id}.json",
        }


data_file_store = DataFileStore()
