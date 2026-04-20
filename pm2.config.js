/**
 * PM2 配置 - findatamcp
 *
 * 使用方式：
 *   启动: pm2 start pm2.config.js
 *   停止: pm2 stop findata-mcp
 *   重启: pm2 restart findata-mcp
 *   查看: pm2 list
 *   日志: pm2 logs findata-mcp
 *
 * 生产环境部署前请设置以下环境变量：
 *   FINDATA_PYTHON  — Python 解释器绝对路径
 *   FINDATA_MCP_DIR — 仓库路径（缺省：本文件所在目录）
 *   FINDATA_LOG_DIR — 日志目录（缺省：~/.mcp-logs）
 *   MCP_SERVER_HOST — 绑定地址（缺省：127.0.0.1）
 *   MCP_SERVER_PORT — 端口（缺省：8006）
 */

const path = require('path');
const os = require('os');

const pythonPath =
  process.env.FINDATA_PYTHON ||
  path.join(os.homedir(), 'miniforge3/envs/mcp_server/bin/python');

const mcpDir = process.env.FINDATA_MCP_DIR || __dirname;
const logDir = process.env.FINDATA_LOG_DIR || path.join(os.homedir(), '.mcp-logs');

module.exports = {
  apps: [
    {
      name: 'findata-mcp',
      script: pythonPath,
      args: 'findatamcp/server.py',
      cwd: mcpDir,

      instances: 1,
      exec_mode: 'fork',

      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      max_memory_restart: '2G',

      error_file: path.join(logDir, 'findata-mcp-error.log'),
      out_file: path.join(logDir, 'findata-mcp-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,

      env: {
        PYTHONUNBUFFERED: '1',
        MCP_SERVER_HOST: process.env.MCP_SERVER_HOST || '127.0.0.1',
        MCP_SERVER_PORT: process.env.MCP_SERVER_PORT || '8006',
      },

      kill_timeout: 5000,
      wait_ready: false,
      listen_timeout: 5000,
    },
  ],
};
