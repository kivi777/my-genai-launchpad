from sqlalchemy import Column, Numeric, String, case, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from launchpad.database.research_paper import ResearchPaper
from launchpad.database.session import Base


class ResearchLibraryCounter(Base):
    __tablename__ = "research_library_counters"

    library = Column(String(64), primary_key=True)
    last_id = Column(Numeric(201, 0), nullable=False)


def next_resource_id(session: Session, library: str) -> str:
    existing = (
        select(
            func.coalesce(
                func.max(
                    case(
                        (
                            ResearchPaper.paper_id.op("~")("^[0-9]+$"),
                            cast(ResearchPaper.paper_id, Numeric),
                        ),
                    )
                ),
                0,
            )
        )
        .where(ResearchPaper.library == library)
        .scalar_subquery()
    )
    statement = insert(ResearchLibraryCounter).values(
        library=library, last_id=existing + 1
    )
    statement = statement.on_conflict_do_update(
        index_elements=[ResearchLibraryCounter.library],
        set_={
            "last_id": func.greatest(
                ResearchLibraryCounter.last_id + 1, statement.excluded.last_id
            )
        },
    )
    return str(session.scalar(statement.returning(ResearchLibraryCounter.last_id)))
