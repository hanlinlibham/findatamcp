#!/bin/bash
# Tushare MCP 服务器启动脚本

cd "$(dirname "$0")"

# 创建日志目录
LOG_DIR="$HOME/.mcp-logs"
mkdir -p "$LOG_DIR"

echo "🚀 启动 Tushare MCP 服务器..."
echo "   Python: ~/miniforge3/envs/mcp_server/bin/python"
echo "   日志目录: $LOG_DIR"
echo ""

pm2 start pm2.config.js

echo ""
echo "✅ 服务已启动！"
echo ""
echo "📊 查看状态:"
echo "   pm2 list"
echo ""
echo "📝 查看日志:"
echo "   pm2 logs tushare-mcp"
echo ""
echo "🔄 重启服务:"
echo "   pm2 restart tushare-mcp"
echo ""
echo "⏹️  停止服务:"
echo "   pm2 stop tushare-mcp"
