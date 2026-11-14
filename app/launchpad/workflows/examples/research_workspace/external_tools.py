import json

from mcp import Client
from pydantic_ai import ModelRetry

from . import config
from .observability import stage


async def query_external_research_tool(query: str) -> str:
    """Request supplemental information from the configured read-only research tool."""
    if not query.strip() or len(query) > 1000:
        raise ModelRetry("Send a research query between 1 and 1000 characters.")
    try:
        with stage("external_tool"):
            async with Client(
                config.EXTERNAL_MCP_URL, read_timeout_seconds=15
            ) as client:
                result = await client.call_tool(
                    config.EXTERNAL_MCP_TOOL, {"query": query}
                )
            if result.is_error:
                raise RuntimeError("External research MCP returned an error")
    except Exception:
        return "External research tool unavailable."
    data = result.structured_content
    if data is None:
        data = [
            item.model_dump(mode="json")
            for item in result.content
            if item.type == "text"
        ]
    return json.dumps(data, ensure_ascii=False)[:8000]
