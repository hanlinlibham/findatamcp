"""
统一错误码定义 (P1-1)

提供标准化的错误码，便于前端处理和日志分析。
"""


class ErrorCode:
    """MCP 工具错误码"""

    # 工具层错误
    TOOL_NOT_SUPPORTED = "tool_not_supported"     # 工具不支持该操作
    SCHEMA_ERROR = "schema_error"                  # 参数格式错误

    # 数据层错误
    NO_DATA = "no_data"                            # 未找到数据
    NO_DATA_IN_RANGE = "no_data_in_range"          # 代码有效但区间内无数据
    INVALID_DATE = "invalid_date"                  # 无效日期
    INVALID_STOCK_CODE = "invalid_stock_code"      # 无效股票代码
    SYMBOL_NOT_FOUND = "symbol_not_found"          # 名称/代码无法解析为标准 ts_code
    INVALID_INDEX_CODE = "invalid_index_code"      # 无效指数代码
    INVALID_SECTOR = "invalid_sector"              # 无效行业/板块

    # 参数层错误
    MISSING_PARAM = "missing_param"                # 缺少必填参数
    INVALID_ENUM = "invalid_enum"                  # 枚举参数取值非法

    # API 层错误
    PRO_REQUIRED = "pro_required"                  # 需要 Tushare Pro
    RATE_LIMITED = "rate_limited"                  # 触发频率限制
    UPSTREAM_ERROR = "upstream_error"              # 上游 API 错误
    TIMEOUT = "timeout"                            # 请求超时

    # 权限错误
    INSUFFICIENT_POINTS = "insufficient_points"    # 积分不足
    UNAUTHORIZED = "unauthorized"                  # 未授权

    @classmethod
    def get_message(cls, code: str) -> str:
        """获取错误码对应的默认消息"""
        messages = {
            cls.TOOL_NOT_SUPPORTED: "该工具不支持此操作",
            cls.SCHEMA_ERROR: "参数格式错误",
            cls.NO_DATA: "未找到数据",
            cls.NO_DATA_IN_RANGE: "代码有效，但指定区间内无数据",
            cls.INVALID_DATE: "无效的日期格式",
            cls.INVALID_STOCK_CODE: "无效的股票代码",
            cls.SYMBOL_NOT_FOUND: "无法将该名称/代码解析为标准 ts_code",
            cls.INVALID_INDEX_CODE: "无效的指数代码",
            cls.INVALID_SECTOR: "无效的行业/板块名称",
            cls.MISSING_PARAM: "缺少必填参数",
            cls.INVALID_ENUM: "枚举参数取值非法",
            cls.PRO_REQUIRED: "此功能需要 Tushare Pro 权限",
            cls.RATE_LIMITED: "请求过于频繁，请稍后重试",
            cls.UPSTREAM_ERROR: "数据源服务异常",
            cls.TIMEOUT: "请求超时",
            cls.INSUFFICIENT_POINTS: "Tushare 积分不足",
            cls.UNAUTHORIZED: "未授权访问"
        }
        return messages.get(code, "未知错误")

    @classmethod
    def get_default_hint(cls, code: str) -> str:
        """获取错误码对应的默认 hint（可路由的恢复建议）。

        调用方未显式传 hint 时回退到这里，保证错误返回总带可操作指引。
        """
        hints = {
            cls.SYMBOL_NOT_FOUND: "先调用 resolve_symbol(关键词) 解析为标准 ts_code，再传入本工具；勿直接把中文名称当代码传入。",
            cls.INVALID_STOCK_CODE: "代码需带交易所后缀，如 600519.SH / 000001.SZ；不确定时先用 resolve_symbol 解析。",
            cls.INVALID_INDEX_CODE: "指数代码格式如 000300.SH（宽基）或 801010.SI（申万）；可用 resolve_symbol 解析名称。",
            cls.NO_DATA_IN_RANGE: "代码有效但该区间无数据，请放宽 start_date/end_date 或确认是否为交易日。",
            cls.NO_DATA: "确认代码与报告期/日期是否正确；非交易日会自动回退到最近交易日。",
            cls.INVALID_SECTOR: "用 get_industry_overview(action='classify') 查看合法行业名，或用 get_sector_top_stocks 的板块口径。",
            cls.MISSING_PARAM: "请补齐必填参数后重试。",
            cls.INVALID_ENUM: "请从下方 valid_values 列出的合法取值中选择。",
            cls.PRO_REQUIRED: "该数据需 Tushare Pro 权限，请确认 TUSHARE_TOKEN 已配置 Pro。",
            cls.RATE_LIMITED: "触发频率限制，请稍后重试或降低调用频率。",
        }
        return hints.get(code, "")
