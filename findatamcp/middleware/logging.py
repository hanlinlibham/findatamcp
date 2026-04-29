"""
请求日志中间件

记录每个 MCP 请求的关键信息,便于追踪客户端行为、统计使用、排查问题。

日志前缀(grep 友好):
  🔌 init       initialize 握手(协议版本 + 客户端信息)
  🔧 tool       CallToolRequest(工具名 + 参数摘要)
  ✅/❌ tool    工具完成/失败(含耗时)
  📊 resource   ReadResourceRequest(URI + 耗时)
  📋 list       ListTools / ListResources / ListResourceTemplates / ListPrompts(结果数)

工具参数仅记录前 6 个 key,每个值最多 40 字符,避免污染日志。
"""
import logging
import time

from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext

logger = logging.getLogger(__name__)


def _summarize_args(args, max_keys: int = 6, max_val: int = 40) -> str:
    """把 dict 参数压成单行摘要,截断长值,避免日志爆炸。"""
    if not args:
        return ""
    items = []
    for k, v in list(args.items())[:max_keys]:
        s = v if isinstance(v, str) else repr(v)
        if len(s) > max_val:
            s = s[:max_val] + "…"
        items.append(f"{k}={s}")
    extra = len(args) - max_keys
    suffix = f" +{extra}more" if extra > 0 else ""
    return " ".join(items) + suffix


class LoggingMiddleware(Middleware):
    """全局 MCP 请求日志:tool / resource / list / init 入口与耗时。"""

    async def on_initialize(self, context: MiddlewareContext, call_next: CallNext):
        # context.message 是 InitializeRequest(包一层 params),其它 hook 才是裸 params
        msg = context.message
        params = getattr(msg, "params", msg)
        ci = getattr(params, "clientInfo", None) or getattr(params, "client_info", None)
        client = f"{getattr(ci, 'name', '?')}/{getattr(ci, 'version', '?')}" if ci else "?"
        proto = getattr(params, "protocolVersion", None) or getattr(params, "protocol_version", "?")
        logger.info("🔌 init client=%s proto=%s", client, proto)
        return await call_next(context)

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext):
        params = context.message
        name = getattr(params, "name", "?")
        args = getattr(params, "arguments", None) or {}
        logger.info("🔧 tool=%s %s", name, _summarize_args(args))
        t0 = time.monotonic()
        try:
            result = await call_next(context)
            dt_ms = (time.monotonic() - t0) * 1000
            tag = "❌" if getattr(result, "is_error", False) else "✅"
            logger.info("%s tool=%s done %.0fms", tag, name, dt_ms)
            return result
        except Exception as e:
            dt_ms = (time.monotonic() - t0) * 1000
            logger.exception("❌ tool=%s FAILED %.0fms err=%s", name, dt_ms, e)
            raise

    async def on_read_resource(self, context: MiddlewareContext, call_next: CallNext):
        uri = str(getattr(context.message, "uri", "?"))
        t0 = time.monotonic()
        try:
            result = await call_next(context)
            dt_ms = (time.monotonic() - t0) * 1000
            logger.info("📊 resource=%s %.0fms", uri, dt_ms)
            return result
        except Exception as e:
            dt_ms = (time.monotonic() - t0) * 1000
            logger.exception("❌ resource=%s FAILED %.0fms err=%s", uri, dt_ms, e)
            raise

    async def _log_list(self, context, call_next, label):
        result = await call_next(context)
        try:
            n = len(result)
        except TypeError:
            n = "?"
        logger.info("📋 %s n=%s", label, n)
        return result

    async def on_list_tools(self, context, call_next):
        return await self._log_list(context, call_next, "list_tools")

    async def on_list_resources(self, context, call_next):
        return await self._log_list(context, call_next, "list_resources")

    async def on_list_resource_templates(self, context, call_next):
        return await self._log_list(context, call_next, "list_resource_templates")

    async def on_list_prompts(self, context, call_next):
        return await self._log_list(context, call_next, "list_prompts")
