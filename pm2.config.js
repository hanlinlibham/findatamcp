/**
 * PM2 配置 - findatamcp (findata MCP)
 *
 * 真实运行态 SoT（2026-06-07 由 Claude Code 校正）：
 *   两个 app —— http(streamable-http, :8111, backend 使用) + sse(:8006)。
 *   旧版本此文件只定义单 app `findata-mcp` 且 python 路径/transport 都与
 *   线上不符（线上是 ad-hoc 起的），本次对齐并加上崩溃自修复硬化
 *   （exp_backoff + max_memory_restart + min_uptime/max_restarts），
 *   与 gangtise-ultra 同款稳定性配置。
 *
 * 启动: pm2 start pm2.config.js && pm2 save
 * 重启: pm2 restart findata-mcp-http findata-mcp-sse
 * 日志: pm2 logs findata-mcp-http
 */

const path = require('path');
const os = require('os');

const pythonPath = process.env.FINDATA_PYTHON || '/opt/miniforge/envs/able_bff/bin/python';
const mcpDir = process.env.FINDATA_MCP_DIR || __dirname;
const logDir = process.env.FINDATA_LOG_DIR || path.join(os.homedir(), '.mcp-logs');

// 两个 transport 共用的稳定性 / 崩溃自修复配置
const hardening = {
  interpreter: 'none',
  exec_mode: 'fork',
  instances: 1,
  autorestart: true,
  watch: false,
  max_memory_restart: '1G',        // ~5x 当前 ~180MB，封顶防泄漏拖垮共享机
  min_uptime: '10s',               // 10s 内崩 = 视为启动失败
  max_restarts: 15,                // min_uptime 窗口内最多 15 次
  restart_delay: 3000,             // 重启间隔 3s
  exp_backoff_restart_delay: 100,  // 指数退避，从 100ms 起
  kill_timeout: 5000,
  log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
  merge_logs: true,
};

module.exports = {
  apps: [
    {
      ...hardening,
      name: 'findata-mcp-http',
      script: pythonPath,
      args: 'findatamcp/server.py',
      cwd: mcpDir,
      error_file: path.join(logDir, 'findata-mcp-http-error.log'),
      out_file: path.join(logDir, 'findata-mcp-http-out.log'),
      env: {
        PYTHONUNBUFFERED: '1',
        MCP_SERVER_HOST: '0.0.0.0',
        MCP_SERVER_PORT: '8111',
        MCP_TRANSPORT: 'streamable-http',
      },
    },
    {
      ...hardening,
      name: 'findata-mcp-sse',
      script: pythonPath,
      args: 'findatamcp/server_sse.py',
      cwd: mcpDir,
      error_file: path.join(logDir, 'findata-mcp-sse-error.log'),
      out_file: path.join(logDir, 'findata-mcp-sse-out.log'),
      env: {
        PYTHONUNBUFFERED: '1',
        MCP_SERVER_HOST: '0.0.0.0',
        MCP_SERVER_PORT: '8006',
        MCP_TRANSPORT: 'sse',
      },
    },
  ],
};
