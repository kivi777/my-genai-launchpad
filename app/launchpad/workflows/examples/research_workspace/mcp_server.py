import asyncio

import httpx
from mcp.server.mcpserver import MCPServer

from . import config
from .note_export import NoteDraft, render_note
from .schema import (
    NotionImportEvent,
    ReadingResult,
    ResearchEvent,
    SearchEvent,
    SearchHit,
    WeeklyReportEvent,
)

server = MCPServer("research-library")


async def run_job(action: str, request: ResearchEvent) -> dict:
    async with httpx.AsyncClient(
        base_url=config.API_URL,
        timeout=20,
        trust_env=httpx.URL(config.API_URL).host
        not in {"localhost", "127.0.0.1", "::1"},
    ) as client:
        response = await client.post(
            "/research/events",
            json={"action": action, **request.model_dump(mode="json")},
        )
        response.raise_for_status()
        job = response.json()
        async with asyncio.timeout(100):
            while True:
                response = await client.get(job["status_url"])
                response.raise_for_status()
                status = response.json()
                if status["status"] == "completed":
                    return status["outputs"]
                if status["status"] == "failed":
                    raise RuntimeError(f"Research job {job['run_id']} failed.")
                await asyncio.sleep(1)


@server.tool()
async def search_research_library(request: SearchEvent) -> list[SearchHit]:
    """Search a named library and return excerpts, pages, source URLs and assets."""
    outputs = await run_job("search", request)
    return [
        SearchHit.model_validate(hit) for hit in outputs["RetrievePapersNode"]["hits"]
    ]


@server.tool()
async def prepare_research_note(request: SearchEvent) -> NoteDraft:
    """Generate a cited research note and plan for saving in Notion."""
    outputs = await run_job("reading_note", request)
    return render_note(
        request.query, ReadingResult.model_validate(outputs["WriteReadingNoteNode"])
    )


@server.tool()
async def prepare_weekly_report(request: WeeklyReportEvent) -> NoteDraft:
    """Summarize the supplied dated research conversations into Markdown."""
    outputs = await run_job("weekly_report", request)
    return NoteDraft.model_validate(outputs["WriteWeeklyReportNode"])


@server.tool()
async def index_notion_note(request: NotionImportEvent) -> dict:
    """Index the Markdown, URL and page ID of a note fetched through Notion MCP."""
    return (await run_job("import_notion", request))["ImportNotionNode"]


if __name__ == "__main__":
    server.run()
