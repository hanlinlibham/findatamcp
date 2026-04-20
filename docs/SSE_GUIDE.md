# Tushare MCP Server - SSE 版本指南

## 概述

SSE (Server-Sent Events) 版本使用标准的 HTTP SSE 协议进行通信，适用于：
- 需要通过 HTTP 代理访问的场景
- 单向服务器推送的需求
- Claude Desktop 等需要 SSE 传输的客户端

## 传输协议对比

| 特性 | SSE | Streamable HTTP | stdio |
|------|-----|-----------------|-------|
| 协议 | HTTP + SSE | HTTP | 标准输入/输出 |
| 双向通信 | 半双工 | 全双工 | 全双工 |
| 远程部署 | ✅ 支持 | ✅ 支持 | ❌ 本地 |
| 代理支持 | ✅ 良好 | ✅ 良好 | ❌ 不适用 |
| 浏览器支持 | ✅ 原生 | ❌ 需要封装 | ❌ 不适用 |

## 快速开始

### 1. 启动服务器

```bash
# 方式 1：使用启动脚本
./start_sse.sh

# 方式 2：直接运行
python src/server_sse.py

# 方式 3：指定端口
MCP_PORT=8006 python src/server_sse.py
```

### 2. 验证服务器

```bash
# 测试 SSE 连接
python scripts/test_sse_client.py

# 交互模式
python scripts/test_sse_client.py -i
```

## 端点说明

### SSE 端点：`GET /sse`

建立 SSE 连接，接收服务器推送的事件。

**请求示例：**
```bash
curl -N http://localhost:8006/sse
```

**响应格式：**
```
event: endpoint
data: {"sessionId": "abc123"}

event: message
data: {"jsonrpc": "2.0", "id": "1", "result": {...}}
```

### 消息端点：`POST /messages`

发送 JSON-RPC 消息到服务器。

**请求示例：**
```bash
curl -X POST "http://localhost:8006/messages?sessionId=abc123" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": "1", "method": "tools/list"}'
```

## Claude Desktop 配置

在 `~/.config/claude/claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "tushare-data": {
      "transport": "sse",
      "url": "http://localhost:8006/sse"
    }
  }
}
```

## 后端集成

注册到后端系统：

```python
# scripts/register_to_system.py
MCP_SERVER_CONFIG = {
    "name": "tushare-data",
    "display_name": "Tushare 数据服务",
    "transport": "sse",
    "url": "http://127.0.0.1:8006/sse",
    "enabled": True,
    "timeout": 30
}
```

## Python 客户端示例

```python
import asyncio
import httpx
import json

async def call_mcp_tool():
    async with httpx.AsyncClient() as client:
        # 1. 建立 SSE 连接获取 session_id
        async with client.stream("GET", "http://localhost:8006/sse") as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    session_id = data.get("sessionId")
                    break

        # 2. 调用工具
        result = await client.post(
            f"http://localhost:8006/messages?sessionId={session_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {
                    "name": "get_stock_data",
                    "arguments": {"stock_code": "600519"}
                }
            }
        )
        return result.json()

# 运行
result = asyncio.run(call_mcp_tool())
print(result)
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TUSHARE_TOKEN` | - | Tushare Pro API Token（必需） |
| `MCP_HOST` | `0.0.0.0` | 服务器监听地址 |
| `MCP_PORT` | `8006` | 服务器端口 |
| `BACKEND_API_URL` | `http://localhost:8004` | 后端 API 地址 |
| `CACHE_ENABLED` | `true` | 是否启用缓存 |

## 常见问题

### Q: SSE vs Streamable HTTP 选哪个？

- **SSE**：兼容性更好，适合需要通过代理或防火墙的场景
- **Streamable HTTP**：更高效的双向通信，适合内网部署

### Q: 连接超时怎么办？

检查：
1. 服务器是否正在运行
2. 端口是否正确
3. 防火墙是否允许连接

### Q: 如何查看服务器日志？

服务器启动时会输出详细日志：
```bash
python src/server_sse.py 2>&1 | tee server.log
```

## 工具列表

SSE 版本包含与主版本相同的 32 个工具：
- 市场数据：8 个工具
- 财务数据：5 个工具
- 宏观经济：7 个工具
- 市场统计：3 个工具
- 分析工具：5 个工具
- 搜索工具：2 个工具
- 其他：2 个工具
