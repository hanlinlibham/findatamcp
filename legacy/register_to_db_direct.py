#!/usr/bin/env python3
"""
直接将 Tushare MCP 服务器注册到数据库
当后端API不可用时使用此脚本
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加backend路径
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

async def register_to_database():
    """直接注册到数据库"""
    try:
        import asyncpg
        from app.core.config import settings as app_settings
        
        print("=" * 60)
        print("🔧 直接注册 Tushare MCP 到数据库")
        print("=" * 60)
        print()
        
        # 连接数据库
        print("📊 连接数据库...")
        print(f"   URL: {app_settings.DATABASE_URL[:50]}...")
        
        conn = await asyncpg.connect(app_settings.DATABASE_URL)
        
        # 插入或更新配置
        query = """
            INSERT INTO global_mcp_servers (
                display_name, server_name, url, connection_type,
                timeout_seconds, is_enabled, extra_config, priority, description
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            ON CONFLICT (server_name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                url = EXCLUDED.url,
                connection_type = EXCLUDED.connection_type,
                timeout_seconds = EXCLUDED.timeout_seconds,
                is_enabled = EXCLUDED.is_enabled,
                description = EXCLUDED.description,
                updated_at = now()
            RETURNING id, server_name, display_name, is_enabled, created_at
        """
        
        print("💾 写入配置...")
        row = await conn.fetchrow(
            query,
            "Tushare Data",                     # display_name
            "tushare-data",                     # server_name
            "http://127.0.0.1:8006/sse",       # url
            "streamableHttp",                   # connection_type
            30,                                 # timeout_seconds
            True,                               # is_enabled
            '{}',                               # extra_config
            50,                                 # priority
            "Tushare股票数据和金融实体搜索服务。提供8个工具+4个Resources+4个Prompts。支持股票数据查询、金融实体搜索（拼音）、全部A股+基金查询。"  # description
        )
        
        # 关闭连接
        await conn.close()
        
        if row:
            print()
            print("✅ 注册成功！")
            print()
            print("📊 服务器信息:")
            print(f"   ID: {row['id']}")
            print(f"   名称: {row['server_name']}")
            print(f"   显示名: {row['display_name']}")
            print(f"   状态: {'启用' if row['is_enabled'] else '禁用'}")
            print(f"   创建时间: {row['created_at']}")
            print()
            print("=" * 60)
            print("🎯 下一步：")
            print("=" * 60)
            print()
            print("1. 刷新前端页面")
            print("2. 在MCP服务器列表中找到 'Tushare Data'")
            print("3. 点击连接按钮")
            print("4. 查看8个工具、4个Resources、4个Prompts")
            print()
            print("💡 提示：")
            print("   - 可以通过 entity://code/贵州茅台 Resource查询代码")
            print("   - 使用 search_financial_entity 工具搜索股票")
            print("   - 在Deep Research中直接使用")
            print()
            return True
        else:
            print("❌ 注册失败：未返回结果")
            return False
            
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print()
        print("请确保：")
        print("1. 在backend目录下运行")
        print("2. 已安装所需依赖")
        print()
        print("或使用SQL脚本注册：")
        print("  psql -d abmind -f /home/abmind_v01/mcp/register_to_database.sql")
        return False
    except Exception as e:
        print(f"❌ 注册失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(register_to_database())
    sys.exit(0 if success else 1)

