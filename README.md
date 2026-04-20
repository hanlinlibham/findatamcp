# 🚀 Tushare MCP Server

企业级金融数据 MCP 服务器 - 模块化架构

## ✨ 特性

- **21个专业工具**：覆盖行情、财务、分析全流程
- **生产级性能**：异步非阻塞、智能缓存、数据对齐
- **语义泛化**：支持"白酒行业"→龙头股代码列表的智能转换
- **模块化设计**：清晰的代码结构，易于维护和扩展

## 📦 快速开始

### 1. 环境准备

```bash
# 激活 conda 环境
conda activate able_bff

# 进入项目目录
cd /home/abmind_v01/mcp
```

### 2. 运行服务器

**方式A：原服务器（生产稳定，21个工具完整）**
```bash
python tushare_server.py --port 8006
```

**方式B：模块化服务器（Streamable HTTP）**
```bash
python src/server.py
```

**方式C：SSE 版本（Server-Sent Events）**
```bash
# 使用启动脚本
./start_sse.sh

# 或直接运行
python src/server_sse.py

# 自定义端口
MCP_PORT=8006 python src/server_sse.py
```

SSE 端点：
- 事件流：`http://localhost:8006/sse`
- 消息接收：`http://localhost:8006/messages`

**方式D：PM2（推荐生产环境）**
```bash
cd scripts
pm2 start ecosystem.config.js
```

## 🧪 测试

```bash
# 测试模块化架构
python test_modular_server.py
```

## 📊 项目状态

### 重构进度

- ✅ **第1阶段**：目录整理 + 核心模块提取（100%）
- 🔄 **第2阶段**：架构设计 + 示例迁移（30%）
- 📋 **第3阶段**：完整迁移 + 测试（待开始）

### 代码统计

| 指标 | 数值 |
| :--- | :---: |
| 核心模块 | 510行 |
| 已迁移工具 | 4/21 |
| 代码精简 | -73% |
| 测试状态 | ✅ 通过 |

## 📁 目录结构

```
mcp/
├── src/              # 源代码（模块化）
│   ├── config.py     # 配置管理
│   ├── cache.py      # 缓存机制
│   ├── database.py   # 数据库查询
│   ├── server.py     # 新主入口
│   ├── utils/        # 工具函数
│   └── tools/        # MCP 工具
│
├── docs/             # 文档
├── scripts/          # 脚本
├── archive/          # 归档
└── tests/            # 测试
```

## 📚 文档

- **[完整重构方案](REFACTORING_PLAN.md)** - 详细的重构计划
- **[完成总结](REFACTORING_COMPLETE_SUMMARY.md)** - 重构成果报告
- **[目录结构](DIRECTORY_STRUCTURE.txt)** - 可视化目录结构
- **[项目文档](docs/README.md)** - 详细的项目文档

## 🔧 配置

环境变量（`.env` 文件）：

```bash
# Tushare Token（必需）
TUSHARE_TOKEN=your_token_here

# 后端 API 地址
BACKEND_API_URL=http://localhost:8004

# 服务器配置
MCP_HOST=0.0.0.0
MCP_PORT=8006

# 缓存配置
CACHE_ENABLED=true
```

## 🎯 核心工具

### 已模块化（4个）⭐
- `get_stock_data` - 获取股票综合数据
- `get_realtime_price` - 获取实时行情
- `get_historical_data` - 获取历史数据
- `get_basic_info` - 获取基本信息

### 待迁移（17个）
- 财务数据工具（5个）
- 业绩数据工具（2个）
- 市场数据工具（2个）
- 搜索查询工具（3个）
- 高级分析工具（5个）

## 💡 重构亮点

### 1. 核心模块提取
- ✅ 配置管理（80行）
- ✅ 缓存机制（180行）
- ✅ 数据库查询（120行）
- ✅ API包装器（80行）

### 2. 代码精简
- 原 `tushare_collector_full.py`：1514行
- 新 `src/utils/tushare_api.py`：80行
- **减少 95%** ⭐⭐⭐

### 3. 架构优化
- 依赖注入模式
- 工具注册模式
- 异步非阻塞调用
- 智能缓存管理

## 📈 性能优化

- **异步非阻塞**：避免事件循环阻塞
- **智能缓存**：
  - 实时数据：60秒
  - 日线数据：1小时
  - 财务数据：24小时
- **数据对齐**：自动处理停牌和缺失值

## 🚀 下一步

### 选项A：完成工具迁移（推荐）
预计时间：2-3小时

### 选项B：保持当前状态（实用）
- 原服务器稳定运行
- 新架构已验证
- 可逐步迁移

## 📧 支持

查看详细文档或联系开发团队。

---

**版本**：2.0.0（模块化重构版）  
**状态**：✅ 测试通过  
**环境**：conda able_bff (Python 3.12.12)
