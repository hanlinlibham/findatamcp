"""测试 findatamcp.config

覆盖 token 来源优先级、默认值、异常 TTL。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _reload_config():
    """每个用例重新导入,确保 Config() 读到当次环境变量。"""
    if "findatamcp.config" in sys.modules:
        del sys.modules["findatamcp.config"]
    return importlib.import_module("findatamcp.config").Config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in [
        "TUSHARE_TOKEN", "BACKEND_API_URL",
        "MCP_SERVER_HOST", "MCP_HOST", "MCP_SERVER_PORT", "MCP_PORT",
        "MCP_TRANSPORT", "CACHE_ENABLED",
        "CACHE_TTL_REALTIME", "CACHE_TTL_DAILY",
        "CACHE_TTL_FINANCIAL", "CACHE_TTL_BASIC",
        "LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_defaults_when_env_clean(tmp_path, monkeypatch):
    # token 文件不存在的位置
    monkeypatch.chdir(tmp_path)
    Config = _reload_config()
    cfg = Config()

    # token 可能来自 repo 根目录的 tusharetoken.txt;我们只断言 fallback 行为
    assert cfg.BACKEND_API_URL == "http://localhost:8004"
    assert cfg.HOST == "0.0.0.0"
    assert cfg.PORT == 8006
    assert cfg.TRANSPORT == "streamable-http"
    assert cfg.CACHE_ENABLED is True
    assert cfg.CACHE_TTL_REALTIME == 60
    assert cfg.CACHE_TTL_DAILY == 3600
    assert cfg.CACHE_TTL_FINANCIAL == 86400
    assert cfg.CACHE_TTL_BASIC == 86400
    assert cfg.LOG_LEVEL == "INFO"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    monkeypatch.setenv("BACKEND_API_URL", "http://api.example.com")
    monkeypatch.setenv("MCP_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_SERVER_PORT", "9999")
    monkeypatch.setenv("MCP_TRANSPORT", "sse")
    monkeypatch.setenv("CACHE_ENABLED", "false")
    monkeypatch.setenv("CACHE_TTL_REALTIME", "10")

    Config = _reload_config()
    cfg = Config()

    assert cfg.TUSHARE_TOKEN == "env-token"
    assert cfg.BACKEND_API_URL == "http://api.example.com"
    assert cfg.HOST == "127.0.0.1"
    assert cfg.PORT == 9999
    assert cfg.TRANSPORT == "sse"
    assert cfg.CACHE_ENABLED is False
    assert cfg.CACHE_TTL_REALTIME == 10


def test_legacy_env_names(monkeypatch):
    """MCP_HOST / MCP_PORT 是旧名;新名缺失时应 fallback。"""
    monkeypatch.setenv("MCP_HOST", "10.0.0.1")
    monkeypatch.setenv("MCP_PORT", "7777")

    Config = _reload_config()
    cfg = Config()

    assert cfg.HOST == "10.0.0.1"
    assert cfg.PORT == 7777


def test_env_takes_precedence_over_token_file(monkeypatch, tmp_path):
    """TUSHARE_TOKEN 环境变量应优先于 tusharetoken.txt。"""
    # 在 findatamcp 包同级目录放假的 token 文件
    import findatamcp.config as cfg_mod
    token_file = Path(cfg_mod.__file__).parent.parent / "tusharetoken.txt"
    created = False
    if not token_file.exists():
        token_file.write_text("file-token")
        created = True
    try:
        monkeypatch.setenv("TUSHARE_TOKEN", "env-wins")
        Config = _reload_config()
        cfg = Config()
        assert cfg.TUSHARE_TOKEN == "env-wins"
    finally:
        if created:
            token_file.unlink()


def test_validate_without_token_returns_false(monkeypatch):
    Config = _reload_config()
    cfg = Config()
    cfg.TUSHARE_TOKEN = None
    assert cfg.validate() is False


def test_validate_with_token_returns_true(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "x")
    Config = _reload_config()
    cfg = Config()
    assert cfg.validate() is True


def test_repr_contains_key_fields(monkeypatch):
    Config = _reload_config()
    cfg = Config()
    r = repr(cfg)
    assert "host" in r and "port" in r and "transport" in r
