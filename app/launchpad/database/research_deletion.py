from hashlib import sha256
from pathlib import Path
from shutil import rmtree
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from launchpad.database.event import Event
from launchpad.database.research_paper import ResearchPaper
from launchpad.database.research_reader import ResearchAnnotation, ResearchReaderNote
from launchpad.database.session import engine
from launchpad.worker.config import celery_app
from launchpad.workflows.examples.research_workspace.config import UPLOAD_DIR


class PaperChangedError(Exception):
    pass


class ImportInProgressError(Exception):
    pass


def lock_pdf(session: Session, pdf_id: UUID) -> None:
    session.execute(
        select(
            func.pg_advisory_xact_lock(int.from_bytes(pdf_id.bytes[:8], signed=True))
        )
    )


def delete_paper(library: str, paper_id: str, expected_pdf: UUID | None) -> None:
    papers = ResearchPaper.__table__
    scope = (
        papers.c.library == library,
        papers.c.paper_id == paper_id,
        func.coalesce(papers.c.payload["source_kind"].astext, "paper") == "paper",
    )
    digest = sha256(f"{library}/{paper_id}".encode()).hexdigest()
    staged = UPLOAD_DIR / ".deleting" / digest
    key = int(digest[:16], 16) - 2**63
    # Keep the same PostgreSQL connection through commit and file cleanup.
    with engine.connect() as connection, Session(bind=connection) as session:
        session.execute(select(func.pg_advisory_lock(key)))
        try:
            _delete_locked(session, scope, library, paper_id, expected_pdf, staged)
        finally:
            session.rollback()
            session.execute(select(func.pg_advisory_unlock(key)))


def _delete_locked(
    session: Session,
    scope: tuple,
    library: str,
    paper_id: str,
    expected_pdf: UUID | None,
    staged: Path,
) -> None:
    session.execute(select(func.pg_advisory_xact_lock(915781, func.hashtext(library))))
    papers = ResearchPaper.__table__
    current = session.execute(
        select(papers.c.payload).where(*scope).with_for_update()
    ).one_or_none()
    if current is None:
        if staged.exists():
            rmtree(staged)
        return

    current_pdf = current.payload.get("pdf_run_id")
    current_pdf = UUID(current_pdf) if current_pdf else None
    if current_pdf != expected_pdf:
        raise PaperChangedError

    versions = list(
        session.execute(
            select(
                Event.id, Event.data, Event.task_context.is_(None).label("pending")
            ).where(
                Event.workflow_type == "RESEARCH_PDF",
                Event.data["library"].as_string() == library,
                or_(
                    Event.data["paper"]["id"].as_string() == paper_id,
                    Event.task_context["nodes"]["ImportPdfNode"]["paper_id"].as_string()
                    == paper_id,
                ),
            )
        )
    )
    if any(
        version.pending
        and celery_app.AsyncResult(str(version.id)).state not in {"FAILURE", "REVOKED"}
        for version in versions
    ):
        raise ImportInProgressError

    pdf_ids = {
        UUID(value)
        for version in versions
        if (value := version.data["paper"].get("pdf_run_id"))
    }
    if current_pdf:
        pdf_ids.add(current_pdf)
    if pdf_ids:
        # Legacy metadata imports can reference an existing PDF from another library.
        shared = session.scalars(
            select(papers.c.payload["pdf_run_id"].astext).where(
                papers.c.payload["pdf_run_id"].astext.in_(
                    [str(pdf_id) for pdf_id in pdf_ids]
                ),
                (papers.c.library != library) | (papers.c.paper_id != paper_id),
            )
        )
        pdf_ids.difference_update(UUID(value) for value in shared)

    for pdf_id in sorted(pdf_ids):
        lock_pdf(session, pdf_id)

    moved = []
    try:
        for pdf_id in pdf_ids:
            original = UPLOAD_DIR / pdf_id.hex / "paper.pdf"
            quarantine = staged / pdf_id.hex
            if original.is_file():
                staged.mkdir(parents=True, exist_ok=True)
                original.rename(quarantine)
            if quarantine.is_file():
                moved.append((original, quarantine))
        if pdf_ids:
            for model in (ResearchAnnotation, ResearchReaderNote):
                session.execute(delete(model).where(model.pdf_id.in_(pdf_ids)))
        if versions:
            session.execute(
                delete(Event).where(Event.id.in_([version.id for version in versions]))
            )
        session.execute(delete(papers).where(*scope))
        session.commit()
    except Exception:
        for original, quarantine in moved:
            quarantine.rename(original)
        raise
    if staged.exists():
        rmtree(staged)
    for original, _ in moved:
        if original.parent.is_dir() and not any(original.parent.iterdir()):
            original.parent.rmdir()
