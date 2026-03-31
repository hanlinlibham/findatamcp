/**
 * PM2 配置文件 - AbleMind FinData MCP 服务器 (本地开发)
 *
 * 使用方式：
 *   启动: pm2 start pm2.config.js
 *   停止: pm2 stop findata-mcp
 *   重启: pm2 restart findata-mcp
 *   查看: pm2 list
 *   日志: pm2 logs findata-mcp
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
  mcpDir: '/home/abmind_v01/mcp',
  logDir: '/home/abmind_v01/tmp/logs/mcp'
};

module.exports = {
  apps: [
    {
      name: 'findata-mcp',
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
      error_file: path.join(config.logDir, 'findata-mcp-error.log'),
      out_file: path.join(config.logDir, 'findata-mcp-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,

      // 环境变量
      env: {
        PYTHONUNBUFFERED: '1',
        MCP_SERVER_HOST: '0.0.0.0',
        MCP_SERVER_PORT: '8006'
      },

      // 进程管理
      kill_timeout: 5000,
      wait_ready: false,
      listen_timeout: 5000
    }
  ]
};
