import json

from sqlalchemy import cast, delete, text
from sqlalchemy.dialects.postgresql import insert

from launchpad.database.research_paper import (
    ResearchChunk,
    ResearchPaper,
    ResearchVector,
)
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples.research_workspace.config import (
    EMBEDDING_BACKEND,
    EMBEDDING_DIMENSIONS,
)
from launchpad.workflows.examples.research_workspace.schema import (
    ImportEvent,
    PaperChunk,
    SearchEvent,
    SearchHit,
)

HYBRID_SEARCH = text("""
    WITH lexical_query AS (
        SELECT websearch_to_tsquery('simple', :keywords) AS terms
    ),
    lexical AS (
        SELECT paper_id, number, row_number() OVER (
            ORDER BY ts_rank_cd(search_vector, terms) DESC, paper_id, number
        ) AS rank
        FROM research_chunks CROSS JOIN lexical_query
        WHERE library = :library AND search_vector @@ terms
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
        ORDER BY match.exact DESC, p.paper_id LIMIT :candidates
    ),
    distances AS (
        SELECT paper_id, number, bge_embedding <=> CAST(:embedding AS vector) AS distance
        FROM research_chunks WHERE library = :library AND bge_embedding IS NOT NULL
          AND embedding_backend = :embedding_backend
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
    SELECT papers.payload AS paper, chunks.chunk, CAST(score AS double precision) AS score
    FROM diverse
    JOIN research_papers papers ON papers.library = :library AND papers.paper_id = diverse.paper_id
    JOIN research_chunks chunks ON chunks.library = papers.library
        AND chunks.paper_id = papers.paper_id AND chunks.number = diverse.number
    ORDER BY paper_rank, exact DESC, score DESC, diverse.paper_id, diverse.number LIMIT :limit
""")


def upsert_papers(
    event: ImportEvent,
    passages: dict[str, list[tuple[PaperChunk, list[float]]]],
) -> None:
    rows = [
        {
            "library": event.library,
            "paper_id": paper.id,
            "payload": paper.model_dump(mode="json"),
            "search_text": paper.search_text(),
        }
        for paper in sorted(event.papers, key=lambda paper: paper.id)
    ]
    statement = insert(ResearchPaper).values(rows)
    with SessionLocal.begin() as session:
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

        ids = [paper.id for paper in event.papers]
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


def hybrid_search(
    event: SearchEvent, vector: list[float], *, original_query: str | None = None
) -> list[SearchHit]:
    with SessionLocal() as session:
        rows = session.execute(
            HYBRID_SEARCH,
            {
                "library": event.library,
                "keywords": event.keywords or event.query,
                "original_query": original_query or event.query,
                "embedding": json.dumps(vector),
                "embedding_backend": EMBEDDING_BACKEND,
                "candidates": max(20, event.limit * 4),
                "limit": event.limit,
            },
        )
        return [SearchHit.model_validate(dict(row)) for row in rows.mappings()]
