#!/bin/bash
# 将 Tushare MCP 服务器注册到数据库

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}🔧 注册 Tushare MCP 到数据库${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# 从.env读取数据库配置
if [ -f /home/abmind_v01/backend/.env ]; then
    export $(cat /home/abmind_v01/backend/.env | grep -E "^(POSTGRES_|DATABASE_)" | xargs)
fi

# 数据库连接信息（根据实际情况调整）
DB_HOST="${DATABASE_HOST:-localhost}"
DB_PORT="${DATABASE_PORT:-5432}"
DB_NAME="${DATABASE_NAME:-abmind}"
DB_USER="${DATABASE_USER:-postgres}"

echo -e "${YELLOW}📊 数据库信息:${NC}"
echo -e "   Host: ${DB_HOST}"
echo -e "   Port: ${DB_PORT}"
echo -e "   Database: ${DB_NAME}"
echo -e "   User: ${DB_USER}"
echo ""

# 询问密码
echo -e "${YELLOW}请输入数据库密码:${NC}"
read -s DB_PASSWORD

echo ""
echo -e "${YELLOW}📝 正在注册配置到数据库...${NC}"

# 执行SQL
PGPASSWORD="$DB_PASSWORD" psql \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -f /home/abmind_v01/mcp/register_to_database.sql

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}======================================${NC}"
    echo -e "${GREEN}✅ 注册成功！${NC}"
    echo -e "${GREEN}======================================${NC}"
    echo ""
    echo -e "${YELLOW}📝 下一步：${NC}"
    echo -e "   1. 刷新前端页面查看 'Tushare Data' 服务器"
    echo -e "   2. 在前端点击连接按钮连接到服务器"
    echo -e "   3. 查看8个可用工具"
    echo ""
else
    echo ""
    echo -e "${RED}======================================${NC}"
    echo -e "${RED}❌ 注册失败${NC}"
    echo -e "${RED}======================================${NC}"
    echo ""
    echo -e "${YELLOW}请检查：${NC}"
    echo -e "   1. 数据库连接信息是否正确"
    echo -e "   2. 数据库用户是否有权限"
    echo -e "   3. global_mcp_servers 表是否存在"
    echo ""
fi

