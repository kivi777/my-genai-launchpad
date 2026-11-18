import json
import unicodedata
from hashlib import file_digest
from uuid import UUID

from sqlalchemy import bindparam, cast, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from launchpad.database.event import Event
from launchpad.database.research_paper import (
    ResearchChunk,
    ResearchPaper,
    ResearchVector,
)
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples.research_workspace.config import (
    EMBEDDING_BACKEND,
    EMBEDDING_DIMENSIONS,
    UPLOAD_DIR,
)
from launchpad.workflows.examples.research_workspace.schema import (
    ImportEvent,
    MeetingEvent,
    MeetingNote,
    Paper,
    PaperChunk,
    SearchEvent,
    SearchHit,
)

HYBRID_SEARCH = text("""
    WITH lexical_query AS (
        SELECT websearch_to_tsquery('simple', :keywords) AS terms
    ),
    eligible_sources AS (
        SELECT paper_id FROM research_papers
        WHERE library = :library AND coalesce(payload->>'source_kind', 'paper') = :source_kind
    ),
    lexical AS (
        SELECT paper_id, number, row_number() OVER (
            ORDER BY ts_rank_cd(search_vector, terms) DESC, paper_id, number
        ) AS rank
        FROM research_chunks CROSS JOIN lexical_query
        WHERE library = :library AND search_vector @@ terms
          AND (CAST(:source_ids AS text[]) IS NULL OR paper_id = ANY(CAST(:source_ids AS text[])))
          AND (CAST(:source_kind AS text) IS NULL OR paper_id IN (SELECT paper_id FROM eligible_sources))
        ORDER BY rank LIMIT :candidates
    ),
    tag_matches AS (
        SELECT p.paper_id, c.number, match.exact
        FROM research_papers p
        JOIN LATERAL (
            SELECT bool_or(lower(tag) IN (lower(btrim(:original_query)), lower(btrim(:keywords)))) AS exact
            FROM jsonb_array_elements_text(coalesce(p.payload->'keywords', '[]'::jsonb)) AS tag
            CROSS JOIN lexical_query
            WHERE lower(tag) IN (lower(btrim(:original_query)), lower(btrim(:keywords)))
               OR to_tsvector('simple', tag) @@ terms
        ) match ON match.exact IS NOT NULL
        JOIN LATERAL (
            SELECT number FROM research_chunks c WHERE c.library = p.library AND c.paper_id = p.paper_id
            ORDER BY number LIMIT 1
        ) c ON true
        WHERE p.library = :library
          AND (CAST(:source_ids AS text[]) IS NULL OR p.paper_id = ANY(CAST(:source_ids AS text[])))
          AND (CAST(:source_kind AS text) IS NULL OR p.paper_id IN (SELECT paper_id FROM eligible_sources))
        ORDER BY match.exact DESC, p.paper_id LIMIT :candidates
    ),
    distances AS (
        SELECT paper_id, number, bge_embedding <=> CAST(:embedding AS vector) AS distance
        FROM research_chunks WHERE library = :library AND bge_embedding IS NOT NULL
          AND embedding_backend = :embedding_backend
          AND (CAST(:source_ids AS text[]) IS NULL OR paper_id = ANY(CAST(:source_ids AS text[])))
          AND (CAST(:source_kind AS text) IS NULL OR paper_id IN (SELECT paper_id FROM eligible_sources))
        ORDER BY distance, paper_id, number LIMIT :candidates
    ),
    semantic AS (
        SELECT paper_id, number, row_number() OVER (ORDER BY distance, paper_id, number) AS rank
        FROM distances WHERE distance < 1
    ),
    fused AS (
        SELECT paper_id, number, sum(score) AS score, bool_or(exact) AS exact
        FROM (
            SELECT paper_id, number, 1.0 / (60 + rank) AS score, false AS exact FROM lexical
            UNION ALL
            SELECT paper_id, number, 1.0 / (60 + rank) AS score, false AS exact FROM semantic
            UNION ALL
            SELECT paper_id, number, 1.0 / 61 AS score, exact FROM tag_matches
        ) ranked
        GROUP BY paper_id, number
    ),
    diverse AS (
        SELECT *, row_number() OVER (PARTITION BY paper_id ORDER BY exact DESC, score DESC, number) AS paper_rank
        FROM fused
    )
    SELECT papers.payload - 'notion_markdown' AS paper, chunks.chunk, CAST(score AS double precision) AS score
    FROM diverse
    JOIN research_papers papers ON papers.library = :library AND papers.paper_id = diverse.paper_id
    JOIN research_chunks chunks ON chunks.library = papers.library
        AND chunks.paper_id = papers.paper_id AND chunks.number = diverse.number
    ORDER BY paper_rank, exact DESC, score DESC, diverse.paper_id, diverse.number LIMIT :limit
""").bindparams(
    bindparam("source_ids", value=None), bindparam("source_kind", value=None)
)


def normalized_title(title: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", title).casefold()
        if char.isalnum()
    )


def matching_pdf(session: Session, library: str, paper: Paper) -> Paper | None:
    payloads = session.scalars(
        select(ResearchPaper.payload)
        .where(
            ResearchPaper.library == library,
            func.coalesce(ResearchPaper.payload["source_kind"].astext, "paper")
            == "paper",
        )
        .order_by(ResearchPaper.paper_id)
    )
    title = normalized_title(paper.title)
    candidates = []
    for payload in payloads:
        if paper.pdf_sha256 and payload.get("pdf_sha256") == paper.pdf_sha256:
            return Paper.model_validate(payload)
        if title and normalized_title(payload.get("title") or "") == title:
            candidates.append(payload)
    return Paper.model_validate(candidates[0]) if len(candidates) == 1 else None


def original_pdf_id(previous: Paper, incoming: Paper) -> UUID | None:
    if not previous.pdf_run_id or not incoming.pdf_sha256:
        return None
    try:
        with (UPLOAD_DIR / previous.pdf_run_id.hex / "paper.pdf").open("rb") as source:
            digest = previous.pdf_sha256 or file_digest(source, "sha256").hexdigest()
    except FileNotFoundError:
        return None
    return previous.pdf_run_id if digest == incoming.pdf_sha256 else None


def upsert_papers(
    event: ImportEvent,
    passages: dict[str, list[tuple[PaperChunk, list[float]]]],
    *,
    match_existing: bool = False,
    notion_markdown: str | None = None,
) -> tuple[list[Paper], bool]:
    papers = event.papers
    replaced = False
    with SessionLocal.begin() as session:
        # Resolve duplicate identity and replace the index under the same library lock.
        session.execute(
            select(func.pg_advisory_xact_lock(915781, func.hashtext(event.library)))
        )
        if match_existing:
            (paper,) = papers
            previous = matching_pdf(session, event.library, paper)
            if previous is not None:
                passages = {previous.id: passages[paper.id]}
                # A byte-identical upload can keep the PDF ID and all reader annotations.
                stable_pdf = original_pdf_id(previous, paper)
                papers = [
                    paper.model_copy(
                        update={
                            "id": previous.id,
                            "pdf_run_id": stable_pdf or paper.pdf_run_id,
                            "source_url": paper.source_url or previous.source_url,
                            "assets": paper.assets or previous.assets,
                        }
                    )
                ]
                replaced = True
        statement = insert(ResearchPaper).values(
            [
                {
                    "library": event.library,
                    "paper_id": paper.id,
                    "payload": paper.model_dump(mode="json")
                    | (
                        {"notion_markdown": notion_markdown}
                        if paper.source_kind == "notion" and notion_markdown is not None
                        else {}
                    ),
                    "search_text": paper.search_text(),
                }
                for paper in sorted(papers, key=lambda paper: paper.id)
            ]
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["library", "paper_id"],
                set_={
                    "payload": statement.excluded.payload,
                    "search_text": statement.excluded.search_text,
                    "embedding": None,
                },
            )
        )

        ids = [paper.id for paper in papers]
        session.execute(
            delete(ResearchChunk).where(
                ResearchChunk.library == event.library, ResearchChunk.paper_id.in_(ids)
            )
        )
        for paper_id, chunks in passages.items():
            for offset in range(0, len(chunks), 100):
                session.execute(
                    insert(ResearchChunk).values(
                        [
                            {
                                "library": event.library,
                                "paper_id": paper_id,
                                "number": chunk.number,
                                "chunk": chunk.model_dump(mode="json"),
                                "embedding_backend": EMBEDDING_BACKEND,
                                "bge_embedding": cast(
                                    json.dumps(vector),
                                    ResearchVector(EMBEDDING_DIMENSIONS),
                                ),
                            }
                            for chunk, vector in chunks[offset : offset + 100]
                        ]
                    )
                )
    return papers, replaced


class MeetingSourceUnavailable(ValueError):
    pass


def read_notion_markdown(
    session: Session, library: str, paper_id: str, payload: dict
) -> tuple[str, bool]:
    markdown = payload.get("notion_markdown")
    if markdown is None:
        markdown = session.scalar(
            select(Event.data["markdown"].as_string())
            .where(
                Event.workflow_type == "RESEARCH_NOTION",
                Event.data["library"].as_string() == library,
                Event.task_context["nodes"]["ImportNotionNode"]["note_id"].as_string()
                == paper_id,
            )
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(1)
        )
    if markdown is not None:
        return markdown, False

    parts = []
    headings = []
    for chunk in session.scalars(
        select(ResearchChunk.chunk)
        .where(ResearchChunk.library == library, ResearchChunk.paper_id == paper_id)
        .order_by(ResearchChunk.number)
    ):
        current = chunk.get("headings", [])
        if current != headings:
            parts.extend(f"## {heading}" for heading in current)
        parts.append(chunk["text"])
        headings = current
    return "\n\n".join(parts), True


def read_selected_meeting_notes(
    library: str, source_ids: list[str]
) -> list[MeetingNote]:
    with SessionLocal() as session:
        rows = dict(
            session.execute(
                select(ResearchPaper.paper_id, ResearchPaper.payload).where(
                    ResearchPaper.library == library,
                    ResearchPaper.paper_id.in_(source_ids),
                )
            )
            .tuples()
            .all()
        )
        if set(source_ids) - rows.keys():
            raise MeetingSourceUnavailable("部分所选资料已不存在，请刷新后重新选择。")
        if any(payload.get("source_kind") != "notion" for payload in rows.values()):
            return []
        notes = []
        for paper_id in source_ids:
            payload = rows[paper_id]
            markdown, reconstructed = read_notion_markdown(
                session, library, paper_id, payload
            )
            if not markdown.strip():
                raise MeetingSourceUnavailable(
                    "所选 Notion 笔记没有可用正文，请重新导入或选择其他笔记。"
                )
            notes.append(
                MeetingNote(
                    paper=Paper.model_validate(payload),
                    markdown=markdown,
                    reconstructed=reconstructed,
                )
            )
        return notes


def hybrid_search(
    event: SearchEvent,
    vector: list[float],
    *,
    original_query: str | None = None,
    balance_sources: bool = False,
) -> list[SearchHit]:
    sources = event.source_ids if isinstance(event, MeetingEvent) else []
    limit = max(event.limit, len(sources))
    parameters = {
        "library": event.library,
        "keywords": event.keywords or event.query,
        "original_query": original_query or event.query,
        "embedding": json.dumps(vector),
        "embedding_backend": EMBEDDING_BACKEND,
        "candidates": max(20, limit * 4),
        "limit": limit,
        "source_ids": sources or None,
    }
    with SessionLocal() as session:
        rows = session.execute(HYBRID_SEARCH, parameters)
        hits = [SearchHit.model_validate(dict(row)) for row in rows.mappings()]
        if not sources:
            kinds = {hit.paper.source_kind for hit in hits}
            if balance_sources and limit > 1 and len(kinds) == 1:
                other_kind = "paper" if "notion" in kinds else "notion"
                # A shared candidate cap can hide an entire source type.
                other = (
                    session.execute(
                        HYBRID_SEARCH,
                        parameters | {"source_kind": other_kind, "limit": 1},
                    )
                    .mappings()
                    .first()
                )
                if other is not None:
                    hits = hits[: limit - 1] + [SearchHit.model_validate(dict(other))]
            return hits
        missing = set(sources) - {hit.paper.id for hit in hits}
        if missing:
            rows = session.execute(
                select(ResearchPaper.payload, ResearchChunk.chunk)
                .join(
                    ResearchChunk,
                    (ResearchChunk.library == ResearchPaper.library)
                    & (ResearchChunk.paper_id == ResearchPaper.paper_id),
                )
                .where(
                    ResearchPaper.library == event.library,
                    ResearchPaper.paper_id.in_(missing),
                )
                .distinct(ResearchPaper.paper_id)
                .order_by(ResearchPaper.paper_id, ResearchChunk.number)
            )
            fallback = [
                SearchHit(
                    paper=Paper.model_validate(paper),
                    chunk=PaperChunk.model_validate(chunk),
                    score=0,
                )
                for paper, chunk in rows
            ]
            if {hit.paper.id for hit in fallback} != missing:
                raise ValueError("所选资料已删除或没有可用片段，请重新选择。")
            hits = fallback + hits
        covered = set()
        primary, remaining = [], []
        for hit in hits:
            (remaining if hit.paper.id in covered else primary).append(hit)
            covered.add(hit.paper.id)
        return (primary + remaining)[:limit]
