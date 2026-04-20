#!/usr/bin/env python3
"""
测试模块化 MCP 服务器

验证新的模块化架构是否正常工作
"""

import sys
from pathlib import Path

# 添加 mcp 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """测试模块导入"""
    print("=" * 80)
    print("🧪 Testing Module Imports")
    print("=" * 80)
    
    try:
        from src.config import config
        print(f"✅ Config module: {config}")
    except Exception as e:
        print(f"❌ Config module failed: {e}")
        return False
    
    try:
        from src.cache import cache
        print(f"✅ Cache module: {cache}")
    except Exception as e:
        print(f"❌ Cache module failed: {e}")
        return False
    
    try:
        from src.database import EntityDatabase
        db = EntityDatabase("http://localhost:8004")
        print(f"✅ Database module: {db}")
    except Exception as e:
        print(f"❌ Database module failed: {e}")
        return False
    
    try:
        from src.utils import TushareAPI
        api = TushareAPI()
        print(f"✅ TushareAPI module: {api}")
    except Exception as e:
        print(f"❌ TushareAPI module failed: {e}")
        return False
    
    try:
        from src.tools.market_data import register_market_tools
        print(f"✅ Market tools module imported")
    except Exception as e:
        print(f"❌ Market tools module failed: {e}")
        return False
    
    print("=" * 80)
    print("✅ All modules imported successfully!")
    print("=" * 80)
    return True


def test_server_creation():
    """测试服务器创建"""
    print("\n" + "=" * 80)
    print("🧪 Testing Server Creation")
    print("=" * 80)
    
    try:
        from src.server import create_mcp_server
        mcp = create_mcp_server()
        print(f"✅ MCP Server created successfully")
        print(f"   Type: {type(mcp)}")
        print("=" * 80)
        return True
    except Exception as e:
        print(f"❌ Server creation failed: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return False


def main():
    """主测试函数"""
    print("\n" + "🚀 " * 20)
    print("Tushare MCP Server - Modular Architecture Test")
    print("🚀 " * 20 + "\n")
    
    # 测试模块导入
    if not test_imports():
        print("\n❌ Module import test failed!")
        sys.exit(1)
    
    # 测试服务器创建
    if not test_server_creation():
        print("\n❌ Server creation test failed!")
        sys.exit(1)
    
    print("\n" + "✅ " * 20)
    print("All tests passed! Modular architecture is working.")
    print("✅ " * 20 + "\n")
    
    print("📝 Next steps:")
    print("   1. Run the modular server: python src/server.py")
    print("   2. Or continue with the original server: python tushare_server.py")
    print("   3. Gradually migrate remaining 17 tools to src/tools/")
    print()


if __name__ == "__main__":
    main()

