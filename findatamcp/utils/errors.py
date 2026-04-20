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
    INVALID_DATE = "invalid_date"                  # 无效日期
    INVALID_STOCK_CODE = "invalid_stock_code"      # 无效股票代码
    INVALID_SECTOR = "invalid_sector"              # 无效行业/板块

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
            cls.INVALID_DATE: "无效的日期格式",
            cls.INVALID_STOCK_CODE: "无效的股票代码",
            cls.INVALID_SECTOR: "无效的行业/板块名称",
            cls.PRO_REQUIRED: "此功能需要 Tushare Pro 权限",
            cls.RATE_LIMITED: "请求过于频繁，请稍后重试",
            cls.UPSTREAM_ERROR: "数据源服务异常",
            cls.TIMEOUT: "请求超时",
            cls.INSUFFICIENT_POINTS: "Tushare 积分不足",
            cls.UNAUTHORIZED: "未授权访问"
        }
        return messages.get(code, "未知错误")
