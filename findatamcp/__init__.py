"""
findatamcp — 金融数据 MCP 服务器

企业级金融数据 MCP 服务器，提供：
- 专业金融数据工具
- 生产级性能优化（异步、缓存）
- 语义泛化支持
"""

__version__ = "2.1.0"
__author__ = "ABMind Team"


def _build_runtime_version() -> str:
    """返回应用版本 + git short SHA（成功才拼），用于 MCP serverInfo.version。

    fastmcp 默认会用库自身版本（如 3.1.0）填 serverInfo，这里改为
    把"应用版本+commit"暴露给客户端，便于 trace 回溯到具体部署。
    """
    import subprocess
    from pathlib import Path

    pkg_dir = Path(__file__).resolve().parent
    git_root = pkg_dir.parent
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(git_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if sha.returncode == 0 and sha.stdout.strip():
            return f"{__version__}+{sha.stdout.strip()}"
    except Exception:
        pass
    return __version__


__runtime_version__ = _build_runtime_version()

