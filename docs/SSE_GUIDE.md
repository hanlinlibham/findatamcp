# findatamcp - SSE 部署指南

## 概述

SSE (Server-Sent Events) 入口使用标准 HTTP SSE 协议，适用于：
- 需要通过 HTTP 代理访问的场景
- 单向服务器推送的需求
- Claude Desktop 等依赖 SSE 传输的客户端

项目同时提供 Streamable HTTP 入口（`findatamcp/server.py`），优先推荐该方式；SSE 仅在客户端不支持 Streamable HTTP 时使用。

## 传输协议对比

| 特性 | SSE | Streamable HTTP | stdio |
|------|-----|-----------------|-------|
| 协议 | HTTP + SSE | HTTP | 标准输入/输出 |
| 双向通信 | 半双工 | 全双工 | 全双工 |
| 远程部署 | ✅ | ✅ | ❌ 本地 |
| 代理支持 | ✅ | ✅ | ❌ |
| 浏览器支持 | ✅ 原生 | ❌ 需封装 | ❌ |

## 快速开始

### 启动服务器

```bash
# 方式 1：启动脚本（前台）
./start_sse.sh

# 方式 2：直接运行
python -m findatamcp.server_sse

# 方式 3：自定义端口
MCP_PORT=8006 python -m findatamcp.server_sse
```

### 验证连接

```bash
python tests/test_sse_client.py          # 一次性测试
python tests/test_sse_client.py -i       # 交互模式
```

## 端点说明

### `GET /sse`

建立 SSE 连接，服务器会先下发 `endpoint` 事件，携带 `sessionId`；后续 JSON-RPC 响应通过 `message` 事件推送。

```bash
curl -N http://127.0.0.1:8006/sse
```

```
event: endpoint
data: {"sessionId": "abc123"}

event: message
data: {"jsonrpc": "2.0", "id": "1", "result": {...}}
```

### `POST /messages`

发送 JSON-RPC 请求，需带上 `sessionId`。

```bash
curl -X POST "http://127.0.0.1:8006/messages?sessionId=abc123" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": "1", "method": "tools/list"}'
```

## Claude Desktop 配置

`~/.config/claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "findatamcp": {
      "transport": "sse",
      "url": "http://127.0.0.1:8006/sse"
    }
  }
}
```

## Python 客户端示例

```python
import asyncio
import httpx
import json


async def call_mcp_tool():
    async with httpx.AsyncClient() as client:
        # 1. 建立 SSE 连接获取 sessionId
        async with client.stream("GET", "http://127.0.0.1:8006/sse") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    session_id = data.get("sessionId")
                    break

        # 2. 调用工具
        result = await client.post(
            f"http://127.0.0.1:8006/messages?sessionId={session_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {
                    "name": "get_stock_data",
                    "arguments": {"stock_code": "600519"},
                },
            },
        )
        return result.json()


print(asyncio.run(call_mcp_tool()))
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TUSHARE_TOKEN` | — | Tushare Pro API Token（必需） |
| `MCP_SERVER_HOST` | `127.0.0.1` | 绑定地址 |
| `MCP_SERVER_PORT` | `8006` | 端口 |
| `SERVER_BASE_URL` | `http://127.0.0.1:8006` | 大数据资源外链基址 |
| `CACHE_ENABLED` | `true` | 是否启用缓存 |

## 常见问题

**Q：SSE vs Streamable HTTP 怎么选？**
- SSE：兼容性更好，适合穿透代理 / 防火墙的远端
- Streamable HTTP：双向效率更高，内网或本地优先

**Q：连接超时怎么办？**
1. 确认服务进程存活（`pm2 list` 或本地日志）
2. 确认端口一致（`.env`、`pm2.config.js`、客户端配置）
3. 若跨机器部署，确认防火墙与 CORS 策略

**Q：日志在哪？**
- PM2：`~/.mcp-logs/findata-mcp-{out,error}.log`
- 前台：`python -m findatamcp.server_sse 2>&1 | tee server.log`
