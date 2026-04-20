#!/usr/bin/env python3
"""
SSE 客户端测试脚本

测试 Tushare MCP SSE 服务器是否正常工作。

使用方法：
    python scripts/test_sse_client.py

    # 指定服务器地址
    python scripts/test_sse_client.py --url http://localhost:8006
"""

import asyncio
import argparse
import json
import sys
import uuid
from typing import Optional

try:
    import httpx
except ImportError:
    print("❌ 请安装 httpx: pip install httpx")
    sys.exit(1)


class MCPSSEClient:
    """MCP SSE 客户端"""

    def __init__(self, base_url: str = "http://localhost:8006"):
        self.base_url = base_url.rstrip("/")
        self.sse_url = f"{self.base_url}/sse"
        self.messages_url = f"{self.base_url}/messages"
        self.session_id: Optional[str] = None

    async def connect(self) -> bool:
        """建立 SSE 连接并获取 session_id"""
        print(f"🔌 连接到 SSE 端点: {self.sse_url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("GET", self.sse_url) as response:
                    if response.status_code != 200:
                        print(f"❌ 连接失败: HTTP {response.status_code}")
                        return False

                    # 读取第一个事件获取 session_id
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            try:
                                event = json.loads(data)
                                if "sessionId" in event:
                                    self.session_id = event["sessionId"]
                                    print(f"✅ 连接成功, session_id: {self.session_id}")
                                    return True
                            except json.JSONDecodeError:
                                pass
                        # 只读取一条消息
                        break

                    print("⚠️  未收到 session_id")
                    return False

        except httpx.ConnectError as e:
            print(f"❌ 无法连接到服务器: {e}")
            return False
        except Exception as e:
            print(f"❌ 连接错误: {e}")
            return False

    async def send_message(self, method: str, params: dict = None) -> dict:
        """发送 JSON-RPC 消息"""
        if not self.session_id:
            raise RuntimeError("未建立连接，请先调用 connect()")

        message = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {}
        }

        print(f"📤 发送消息: {method}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.messages_url}?sessionId={self.session_id}",
                    json=message,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    result = response.json()
                    return result
                elif response.status_code == 202:
                    # 异步响应
                    return {"status": "accepted", "message": "Response will be sent via SSE"}
                else:
                    print(f"❌ 请求失败: HTTP {response.status_code}")
                    return {"error": response.text}

        except Exception as e:
            print(f"❌ 发送消息错误: {e}")
            return {"error": str(e)}

    async def list_tools(self) -> list:
        """获取工具列表"""
        result = await self.send_message("tools/list")
        if "result" in result:
            return result["result"].get("tools", [])
        return []

    async def call_tool(self, name: str, arguments: dict = None) -> dict:
        """调用工具"""
        return await self.send_message("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })


async def test_server(url: str):
    """测试 SSE 服务器"""
    print("=" * 60)
    print("🧪 Tushare MCP SSE 服务器测试")
    print("=" * 60)
    print()

    client = MCPSSEClient(url)

    # 1. 测试连接
    print("📋 测试 1: 建立 SSE 连接")
    connected = await client.connect()
    if not connected:
        print("❌ 测试失败: 无法建立连接")
        return False
    print()

    # 2. 测试获取工具列表
    print("📋 测试 2: 获取工具列表")
    tools = await client.list_tools()
    if tools:
        print(f"✅ 发现 {len(tools)} 个工具:")
        for i, tool in enumerate(tools[:5], 1):
            print(f"   {i}. {tool.get('name')}")
        if len(tools) > 5:
            print(f"   ... 还有 {len(tools) - 5} 个工具")
    else:
        print("⚠️  未获取到工具列表")
    print()

    # 3. 测试调用工具
    print("📋 测试 3: 调用 get_tool_metadata 工具")
    result = await client.call_tool("get_tool_metadata", {})
    if "result" in result:
        content = result["result"].get("content", [])
        if content:
            print("✅ 工具调用成功:")
            try:
                data = json.loads(content[0].get("text", "{}"))
                print(f"   - 工具总数: {data.get('total_tools', 'N/A')}")
                print(f"   - 服务器名称: {data.get('server_name', 'N/A')}")
            except:
                print(f"   响应: {content[0]}")
    elif "error" in result:
        print(f"⚠️  工具调用错误: {result['error']}")
    else:
        print(f"📥 响应: {result}")
    print()

    print("=" * 60)
    print("✅ SSE 服务器测试完成")
    print("=" * 60)
    return True


async def interactive_mode(url: str):
    """交互模式"""
    print("=" * 60)
    print("🔧 Tushare MCP SSE 客户端 - 交互模式")
    print("=" * 60)
    print()
    print("命令:")
    print("  list      - 列出所有工具")
    print("  call <name> [args]  - 调用工具")
    print("  quit      - 退出")
    print()

    client = MCPSSEClient(url)

    # 建立连接
    if not await client.connect():
        print("❌ 无法连接到服务器")
        return

    while True:
        try:
            cmd = input("\n> ").strip()

            if not cmd:
                continue

            if cmd == "quit" or cmd == "exit":
                print("👋 再见!")
                break

            if cmd == "list":
                tools = await client.list_tools()
                if tools:
                    print(f"\n📦 工具列表 ({len(tools)} 个):")
                    for tool in tools:
                        print(f"  - {tool.get('name')}: {tool.get('description', '')[:60]}...")
                continue

            if cmd.startswith("call "):
                parts = cmd[5:].split(None, 1)
                name = parts[0]
                args = {}
                if len(parts) > 1:
                    try:
                        args = json.loads(parts[1])
                    except json.JSONDecodeError:
                        print("⚠️  参数格式错误，请使用 JSON 格式")
                        continue

                result = await client.call_tool(name, args)
                print(f"\n📥 响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                continue

            print("❓ 未知命令。输入 'quit' 退出。")

        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")


def main():
    parser = argparse.ArgumentParser(description="Tushare MCP SSE 客户端测试")
    parser.add_argument(
        "--url",
        default="http://localhost:8006",
        help="SSE 服务器地址 (默认: http://localhost:8006)"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="进入交互模式"
    )
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive_mode(args.url))
    else:
        asyncio.run(test_server(args.url))


if __name__ == "__main__":
    main()
