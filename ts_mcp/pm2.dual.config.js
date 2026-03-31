/**
 * PM2 配置文件 - AbleMind FinData MCP 服务器 (SSE + HTTP 双版本)
 *
 * 使用方式：
 *   启动: pm2 start pm2.dual.config.js
 *   停止: pm2 stop findata-mcp-sse findata-mcp-http
 *   重启: pm2 restart findata-mcp-sse findata-mcp-http
 *   查看: pm2 list
 *   日志: pm2 logs findata-mcp-sse / pm2 logs findata-mcp-http
 */

const path = require('path');
const os = require('os');

// 自动检测环境
const isLocal = os.platform() === 'darwin';
const homeDir = os.homedir();

// 路径配置
const config = isLocal ? {
  // macOS 本地开发
  pythonPath: path.join(homeDir, 'miniforge3/envs/mcp_server/bin/python'),
  mcpDir: __dirname,
  logDir: path.join(homeDir, '.mcp-logs')
} : {
  // Linux 生产服务器
  pythonPath: '/opt/miniforge/envs/able_bff/bin/python',
  mcpDir: '/home/tushare_mcp/ts_mcp',
  logDir: '/home/tushare_mcp/ts_mcp/logs'
};

module.exports = {
  apps: [
    // SSE 版本 - 端口 8006
    {
      name: 'findata-mcp-sse',
      script: config.pythonPath,
      args: 'src/server_sse.py',
      cwd: config.mcpDir,

      // 单实例模式
      instances: 1,
      exec_mode: 'fork',

      // 自动重启配置
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      max_memory_restart: '2G',

      // 日志配置
      error_file: path.join(config.logDir, 'findata-mcp-sse-error.log'),
      out_file: path.join(config.logDir, 'findata-mcp-sse-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,

      // 环境变量
      env: {
        PYTHONUNBUFFERED: '1',
        MCP_SERVER_HOST: '0.0.0.0',
        MCP_SERVER_PORT: '8006',
        MCP_TRANSPORT: 'sse'
      },

      // 进程管理
      kill_timeout: 5000,
      wait_ready: false,
      listen_timeout: 5000
    },

    // HTTP 版本 - 端口 8111
    {
      name: 'findata-mcp-http',
      script: config.pythonPath,
      args: 'src/server.py',
      cwd: config.mcpDir,

      // 单实例模式
      instances: 1,
      exec_mode: 'fork',

      // 自动重启配置
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      max_memory_restart: '2G',

      // 日志配置
      error_file: path.join(config.logDir, 'findata-mcp-http-error.log'),
      out_file: path.join(config.logDir, 'findata-mcp-http-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,

      // 环境变量
      env: {
        PYTHONUNBUFFERED: '1',
        MCP_SERVER_HOST: '0.0.0.0',
        MCP_SERVER_PORT: '8111',
        MCP_TRANSPORT: 'streamable-http'
      },

      // 进程管理
      kill_timeout: 5000,
      wait_ready: false,
      listen_timeout: 5000
    }
  ]
};
