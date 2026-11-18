from datetime import datetime
from uuid import UUID

import httpx
from pydantic import BaseModel, HttpUrl, ValidationError

from . import config
from .schema import NotionImportEvent, NotionPageImportEvent, NotionParent


class NotionError(RuntimeError):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


class NotionPage(BaseModel):
    id: UUID
    title: str
    source_url: HttpUrl
    last_edited_time: datetime
    parent: NotionParent | None = None


class NotionPageList(BaseModel):
    pages: list[NotionPage]
    next_cursor: str | None = None


def notion_client() -> httpx.AsyncClient:
    if not config.NOTION_TOKEN:
        raise NotionError("请先在后端配置 RESEARCH_NOTION_TOKEN，再刷新页面。", 503)
    return httpx.AsyncClient(
        base_url="https://api.notion.com/v1/",
        headers={
            "Authorization": f"Bearer {config.NOTION_TOKEN}",
            "Notion-Version": "2026-03-11",
        },
        timeout=25,
    )


async def notion_request(
    client: httpx.AsyncClient, method: str, path: str, **kwargs: object
) -> dict:
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.RequestError as exc:
        raise NotionError("暂时无法连接 Notion，请稍后重试。") from exc
    errors = {
        401: "Notion 连接密钥无效，请检查后端配置。",
        403: "Notion 连接缺少读取权限。",
        404: "Notion 页面不存在，或尚未授权给此连接。",
        429: "Notion 请求过于频繁，请稍后重试。",
    }
    if response.is_error:
        raise NotionError(
            errors.get(response.status_code, "Notion 暂时无法返回内容，请稍后重试。"),
            429 if response.status_code == 429 else 502,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise NotionError("Notion 返回了无法读取的内容。") from exc


def read_page(item: dict) -> NotionPage:
    title_parts = next(
        (
            prop["title"]
            for prop in item["properties"].values()
            if prop["type"] == "title"
        ),
        [],
    )
    title = "".join(part["plain_text"] for part in title_parts).strip()
    parent = item.get("parent") or {}
    kind = parent.get("type")
    return NotionPage(
        id=item["id"],
        title=title[:500] or "未命名页面",
        source_url=item["url"],
        last_edited_time=item["last_edited_time"],
        parent=NotionParent(
            kind=kind, id=parent.get(kind) if kind != "workspace" else None
        )
        if kind
        else None,
    )


async def search_notion_pages(query: str, cursor: str | None) -> NotionPageList:
    payload = {
        "page_size": 25,
        "filter": {"property": "object", "value": "page"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
    }
    if query:
        payload["query"] = query
    if cursor:
        payload["start_cursor"] = cursor
    async with notion_client() as client:
        result = await notion_request(client, "POST", "search", json=payload)
    return NotionPageList(
        pages=[
            read_page(item)
            for item in result["results"]
            if item["object"] == "page"
            and not (item.get("in_trash") or item.get("archived"))
        ],
        next_cursor=result.get("next_cursor"),
    )


async def list_notion_children(page_id: UUID, cursor: str | None) -> NotionPageList:
    params = {"page_size": 100}
    if cursor:
        params["start_cursor"] = cursor
    async with notion_client() as client:
        result = await notion_request(
            client, "GET", f"blocks/{page_id}/children", params=params
        )
    pages = []
    for block in result["results"]:
        if (
            block["type"] != "child_page"
            or block.get("in_trash")
            or block.get("archived")
        ):
            continue
        block_id = UUID(block["id"])
        pages.append(
            NotionPage(
                id=block_id,
                title=(block["child_page"]["title"].strip() or "未命名页面")[:500],
                source_url=HttpUrl(f"https://www.notion.so/{block_id.hex}"),
                last_edited_time=block["last_edited_time"],
                parent=NotionParent(kind="page_id", id=page_id),
            )
        )
    return NotionPageList(pages=pages, next_cursor=result.get("next_cursor"))


async def load_notion_note(event: NotionPageImportEvent) -> NotionImportEvent:
    path = f"pages/{event.page_id}"
    async with notion_client() as client:
        item = await notion_request(client, "GET", path)
        if item.get("in_trash") or item.get("archived"):
            raise NotionError("该 Notion 页面已归档或移入回收站。")
        page = read_page(item)
        data = await notion_request(client, "GET", f"{path}/markdown")
    markdown = data["markdown"].strip()
    if data.get("truncated") or len(markdown) > 60000:
        raise NotionError("Notion 页面过长，请拆分为较短的页面后再导入。")
    if not markdown:
        raise NotionError("Notion 页面没有可导入的正文。")
    try:
        return NotionImportEvent(
            library=event.library,
            page_id=page.id,
            title=page.title,
            source_url=page.source_url,
            notion_parent=page.parent,
            markdown=markdown,
        )
    except ValidationError as exc:
        raise NotionError("Notion 页面内容未通过导入校验。") from exc
