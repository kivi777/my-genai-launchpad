import asyncio
import re
from collections import Counter
from hashlib import blake2b

import httpx

from launchpad.database.research_repository import (
    hybrid_search,
    read_selected_meeting_notes,
    upsert_papers,
)

from . import config
from .observability import stage
from .schema import (
    ImportEvent,
    MeetingEvent,
    MeetingNote,
    Paper,
    PaperChunk,
    SearchEvent,
    SearchHit,
)

_demo_library: dict[tuple[str, str], tuple[Paper, list[PaperChunk], str | None]] = {}


def sample_embedding(text: str) -> list[float]:
    vector = [0.0] * config.EMBEDDING_DIMENSIONS
    for term in re.findall(r"[^\W_]+", text.casefold()):
        digest = blake2b(term.encode(), digest_size=4).digest()
        index = int.from_bytes(digest, "big") % len(vector)
        vector[index] += 1.0
    return vector


async def embeddings(texts: list[str]) -> list[list[float]]:
    if config.OFFLINE_MODE:
        return [sample_embedding(text) for text in texts]
    if not config.SILICONFLOW_API_KEY:
        raise RuntimeError("Set SILICONFLOW_API_KEY for research embeddings")
    vectors = []
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"}, timeout=60
    ) as client:
        for offset in range(0, len(texts), 16):
            inputs = texts[offset : offset + 16]
            response = await client.post(
                config.EMBEDDING_URL,
                json={
                    "model": config.EMBEDDING_MODEL,
                    "input": inputs,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
            items = sorted(response.json()["data"], key=lambda item: item["index"])
            if [item["index"] for item in items] != list(range(len(inputs))) or any(
                len(item["embedding"]) != config.EMBEDDING_DIMENSIONS for item in items
            ):
                raise ValueError(
                    "Expected one 1024-dimensional BGE-M3 vector per input"
                )
            vectors.extend(item["embedding"] for item in items)
    return vectors


async def import_papers(
    event: ImportEvent,
    pdf_chunks: list[PaperChunk] | None = None,
    *,
    match_existing: bool = False,
    notion_markdown: str | None = None,
) -> tuple[list[Paper], bool]:
    passages = {
        paper.id: pdf_chunks or [PaperChunk(number=1, text=paper.search_text())]
        for paper in event.papers
    }
    if config.DEMO_MODE:
        _demo_library.update(
            {
                (event.library, paper.id): (paper, passages[paper.id], notion_markdown)
                for paper in event.papers
            }
        )
        return event.papers, False
    with stage("embed_documents") as metrics:
        metrics.update(
            chunks=sum(map(len, passages.values())), model=config.EMBEDDING_BACKEND
        )
        vectors = iter(
            await embeddings(
                [
                    "\n".join(
                        filter(
                            None,
                            (
                                paper.title,
                                " ".join(paper.keywords),
                                chunk.text,
                            ),
                        )
                    )
                    for paper in event.papers
                    for chunk in passages[paper.id]
                ]
            )
        )
    with stage("store_documents") as metrics:
        papers, replaced = await asyncio.to_thread(
            upsert_papers,
            event,
            {
                paper_id: [(chunk, next(vectors)) for chunk in chunks]
                for paper_id, chunks in passages.items()
            },
            match_existing=match_existing,
            notion_markdown=notion_markdown,
        )
        metrics.update(
            documents=len(event.papers), chunks=sum(map(len, passages.values()))
        )
    return papers, replaced


async def selected_meeting_notes(event: MeetingEvent) -> list[MeetingNote]:
    if not event.source_ids:
        return []
    if not config.DEMO_MODE:
        return await asyncio.to_thread(
            read_selected_meeting_notes, event.library, event.source_ids
        )
    notes = []
    for paper_id in event.source_ids:
        document = _demo_library.get((event.library, paper_id))
        if document is None:
            return []
        paper, _, markdown = document
        if paper.source_kind != "notion" or markdown is None:
            return []
        notes.append(MeetingNote(paper=paper, markdown=markdown))
    return notes


async def search_papers(
    event: SearchEvent, *, original_query: str | None = None
) -> list[SearchHit]:
    if config.DEMO_MODE:
        sources = getattr(event, "source_ids", ())
        terms = set(re.findall(r"\w+", (event.keywords or event.query).casefold()))
        hits = []
        for (library, _), (paper, chunks, _) in _demo_library.items():
            if library == event.library and (not sources or paper.id in sources):
                for chunk in chunks:
                    counts = Counter(
                        re.findall(
                            r"\w+",
                            f"{paper.title} {' '.join(paper.keywords)} {chunk.text}".casefold(),
                        )
                    )
                    score = sum(counts[term] for term in terms)
                    if score or (sources and chunk is chunks[0]):
                        hits.append(SearchHit(paper=paper, score=score, chunk=chunk))
        ranked = sorted(hits, key=lambda hit: (-hit.score, hit.paper.id))
        top = ranked[: event.limit]
        if not isinstance(event, MeetingEvent) and event.limit > 1 and top:
            kinds = {hit.paper.source_kind for hit in top}
            other = next(
                (
                    hit
                    for hit in ranked[event.limit :]
                    if hit.paper.source_kind not in kinds
                ),
                None,
            )
            if other:
                return top[:-1] + [other]
        return top
    with stage("embed_query") as metrics:
        metrics["model"] = config.EMBEDDING_BACKEND
        (vector,) = await embeddings([event.query])
    with stage("hybrid_search") as metrics:
        hits = await asyncio.to_thread(
            hybrid_search,
            event,
            vector,
            original_query=original_query,
            balance_sources=not isinstance(event, MeetingEvent),
        )
        metrics["hits"] = len(hits)
    return hits
