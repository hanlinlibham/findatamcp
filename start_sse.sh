#!/bin/bash
# findatamcp — SSE 版本启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=${MCP_PORT:-8110}
HOST=${MCP_HOST:-127.0.0.1}
PYTHON_BIN="${FINDATA_PYTHON:-python3}"

echo "======================================"
echo "🚀 findatamcp (SSE)"
echo "======================================"
echo "   Host: $HOST"
echo "   Port: $PORT"
echo "   Python: $PYTHON_BIN"
echo ""
echo "📡 Endpoints:"
echo "   SSE:      http://$HOST:$PORT/sse"
echo "   Messages: http://$HOST:$PORT/messages"
echo "======================================"
echo ""

if [ -f ".env" ]; then
    echo "✅ Found .env file"
else
    echo "⚠️  未找到 .env — 请确认 TUSHARE_TOKEN 已设置"
fi

exec "$PYTHON_BIN" findatamcp/server_sse.py
