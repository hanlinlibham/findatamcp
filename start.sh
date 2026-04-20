#!/bin/bash
# findatamcp 启动脚本

cd "$(dirname "$0")"

LOG_DIR="${FINDATA_LOG_DIR:-$HOME/.mcp-logs}"
mkdir -p "$LOG_DIR"

echo "🚀 启动 findatamcp..."
echo "   日志目录: $LOG_DIR"
echo ""

pm2 start pm2.config.js

echo ""
echo "✅ 服务已启动"
echo "   pm2 list          # 查看状态"
echo "   pm2 logs findata-mcp"
echo "   pm2 restart findata-mcp"
echo "   pm2 stop findata-mcp"
