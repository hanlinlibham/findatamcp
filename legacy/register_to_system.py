#!/usr/bin/env python3
"""
将Tushare MCP服务器注册到系统

通过API将tushare-data服务器配置保存到数据库中
"""

import asyncio
import httpx
import sys
from pathlib import Path

# 配置
BACKEND_URL = "http://localhost:8004"  # 后端API地址（实际端口）
MCP_SERVER_CONFIG = {
    "name": "tushare-data",
    "display_name": "Tushare 数据服务",
    "transport": "sse",  # SSE transport
    "url": "http://127.0.0.1:8006/sse",
    "enabled": True,
    "timeout": 30,
    "description": "Tushare股票市场数据服务器，提供实时行情、历史数据、财务指标等功能",
    "env": {},
    "args": []
}


async def register_server():
    """注册MCP服务器到系统"""
    print("=" * 60)
    print("🔧 注册 Tushare MCP 服务器到系统")
    print("=" * 60)
    print()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. 持久化服务器配置
            print("📝 正在保存服务器配置...")
            response = await client.post(
                f"{BACKEND_URL}/api/mcp/servers/persist",
                json=MCP_SERVER_CONFIG
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 服务器配置已保存")
                print(f"   ID: {result.get('id')}")
                print(f"   名称: {result.get('name')}")
                print(f"   URL: {result.get('url')}")
                print()
                
                # 2. 连接到服务器
                server_name = MCP_SERVER_CONFIG["name"]
                print(f"🔌 正在连接到 {server_name}...")
                
                connect_response = await client.post(
                    f"{BACKEND_URL}/api/mcp/servers/{server_name}/connect"
                )
                
                if connect_response.status_code == 200:
                    connect_result = connect_response.json()
                    if connect_result.get("connected"):
                        print(f"✅ 成功连接到 {server_name}")
                        print()
                        
                        # 3. 获取工具列表
                        print("🔍 正在获取工具列表...")
                        tools_response = await client.get(
                            f"{BACKEND_URL}/api/mcp/servers/{server_name}/tools"
                        )
                        
                        if tools_response.status_code == 200:
                            tools_result = tools_response.json()
                            tools = tools_result.get("tools", [])
                            print(f"✅ 发现 {len(tools)} 个工具:")
                            for i, tool in enumerate(tools, 1):
                                print(f"   {i}. {tool.get('name')} - {tool.get('description', '')[:50]}...")
                            print()
                        else:
                            print(f"⚠️ 获取工具列表失败: {tools_response.text}")
                    else:
                        print(f"❌ 连接失败: {connect_result}")
                        return False
                else:
                    print(f"❌ 连接请求失败: {connect_response.text}")
                    return False
                
                print("=" * 60)
                print("✅ Tushare MCP 服务器注册完成")
                print("=" * 60)
                print()
                print("📊 服务器信息:")
                print(f"   名称: {server_name}")
                print(f"   URL: {MCP_SERVER_CONFIG['url']}")
                print(f"   状态: 已连接")
                print()
                print("🎯 使用方式:")
                print('   在深度研究工作流中调用:')
                print('   result = await _call_mcp_tool("tushare-data", "get_stock_data", {"stock_code": "000001"})')
                print()
                
                return True
            else:
                print(f"❌ 保存配置失败: {response.status_code}")
                print(f"   响应: {response.text}")
                return False
                
    except httpx.ConnectError:
        print(f"❌ 无法连接到后端服务器: {BACKEND_URL}")
        print(f"   请确保后端服务正在运行")
        return False
    except Exception as e:
        print(f"❌ 注册失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_server_status():
    """检查服务器状态"""
    print("🔍 检查 Tushare MCP 服务器状态...")
    print()
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 检查后端服务
            try:
                backend_response = await client.get(f"{BACKEND_URL}/health")
                if backend_response.status_code == 200:
                    print("✅ 后端服务运行正常")
                else:
                    print(f"⚠️ 后端服务状态异常: {backend_response.status_code}")
            except Exception as e:
                print(f"❌ 后端服务未运行: {BACKEND_URL}")
                print(f"   请先启动后端服务")
                return False
            
            # 检查Tushare MCP服务
            try:
                mcp_response = await client.get(MCP_SERVER_CONFIG["url"].replace("/sse", "/health"))
                if mcp_response.status_code == 200:
                    print("✅ Tushare MCP 服务运行正常")
                else:
                    print(f"⚠️ Tushare MCP 服务状态异常: {mcp_response.status_code}")
            except Exception as e:
                print(f"❌ Tushare MCP 服务未运行: {MCP_SERVER_CONFIG['url']}")
                print(f"   请先运行: cd /home/abmind_v01/mcp && bash start.sh")
                return False
            
            print()
            return True
            
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        return False


def main():
    """主函数"""
    print()
    
    # 检查服务状态
    status_ok = asyncio.run(check_server_status())
    
    if not status_ok:
        print()
        print("⚠️ 请确保以下服务正在运行:")
        print("   1. 后端服务 (localhost:8089)")
        print("   2. Tushare MCP 服务 (localhost:8006)")
        print()
        print("启动命令:")
        print("   # 启动后端")
        print("   cd /home/abmind_v01 && bash start_services.sh")
        print()
        print("   # 启动 Tushare MCP")
        print("   cd /home/abmind_v01/mcp && bash start.sh")
        print()
        sys.exit(1)
    
    # 注册服务器
    success = asyncio.run(register_server())
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

