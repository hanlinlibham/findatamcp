-- 将 Tushare MCP 服务器配置持久化到数据库
-- 使用方式: psql -h localhost -U your_user -d your_database -f register_to_database.sql

-- 插入或更新 tushare-data 服务器配置
INSERT INTO global_mcp_servers (
    display_name,
    server_name,
    url,
    connection_type,
    timeout_seconds,
    is_enabled,
    extra_config,
    priority,
    description,
    created_by
) VALUES (
    'Tushare Data',                                    -- display_name
    'tushare-data',                                    -- server_name
    'http://127.0.0.1:8006/sse',                      -- url
    'streamableHttp',                                  -- connection_type (sse → streamableHttp)
    30,                                                -- timeout_seconds
    true,                                              -- is_enabled
    '{}'::jsonb,                                       -- extra_config
    50,                                                -- priority
    'Tushare股票数据和金融实体搜索服务。提供8个工具：股票数据查询、实时行情、历史数据、财务指标、基本信息、股票搜索、金融实体搜索（支持拼音）、精确查询。集成本地金融实体数据库（全部A股+基金）。',  -- description
    'system'                                           -- created_by
)
ON CONFLICT (server_name) 
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    url = EXCLUDED.url,
    connection_type = EXCLUDED.connection_type,
    timeout_seconds = EXCLUDED.timeout_seconds,
    is_enabled = EXCLUDED.is_enabled,
    description = EXCLUDED.description,
    updated_at = now()
RETURNING 
    id, 
    server_name, 
    display_name, 
    url,
    connection_type,
    is_enabled,
    created_at;

