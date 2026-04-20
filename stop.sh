#!/bin/bash
# findatamcp 停止脚本

cd "$(dirname "$0")"

echo "⏹️  停止 findatamcp..."
pm2 stop findata-mcp
pm2 delete findata-mcp

echo "✅ 服务已停止"
