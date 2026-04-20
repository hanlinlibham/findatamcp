#!/bin/bash
# Tushare MCP 服务器停止脚本

cd "$(dirname "$0")"

echo "⏹️  停止 Tushare MCP 服务器..."
pm2 stop tushare-mcp
pm2 delete tushare-mcp

echo "✅ 服务已停止！"

