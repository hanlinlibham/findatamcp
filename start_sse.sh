#!/bin/bash
# Tushare MCP Server - SSE 版本启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 默认端口
PORT=${MCP_PORT:-8110}
HOST=${MCP_HOST:-0.0.0.0}

echo "======================================"
echo "🚀 Tushare MCP Server (SSE Version)"
echo "======================================"
echo "   Host: $HOST"
echo "   Port: $PORT"
echo "   Transport: SSE"
echo ""
echo "📡 Endpoints:"
echo "   SSE: http://$HOST:$PORT/sse"
echo "   Messages: http://$HOST:$PORT/messages"
echo "======================================"
echo ""

# 检查 .env 文件
if [ -f ".env" ]; then
    echo "✅ Found .env file"
else
    echo "⚠️  No .env file found. Make sure TUSHARE_TOKEN is set."
fi

# 启动服务器
/host/opt/miniforge/envs/able_bff/bin/python3.12 src/server_sse.py
