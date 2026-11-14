from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from launchpad.database.research_deletion import lock_pdf
from launchpad.database.research_reader import ResearchAnnotation, ResearchReaderNote
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples.research_workspace import config

router = APIRouter()
Channel = Literal["annotations", "notes"]
Unit = Annotated[float, Field(ge=0, le=1)]
TABLES = {"annotations": ResearchAnnotation, "notes": ResearchReaderNote}


class Rectangle(BaseModel):
    left: Unit
    top: Unit
    right: Unit
    bottom: Unit

    @model_validator(mode="after")
    def ordered_edges(self) -> "Rectangle":
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Highlight rectangle must have positive area")
        return self


class ReaderNoteInput(BaseModel):
    page: int = Field(ge=1)
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
    ]


class AnnotationInput(ReaderNoteInput):
    quote: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)
    ]
    regions: list[Rectangle] = Field(min_length=1, max_length=200)


class ReaderNoteResult(ReaderNoteInput):
    id: UUID
    updated_at: datetime


class AnnotationResult(AnnotationInput):
    id: UUID
    updated_at: datetime


def require_pdf(pdf_id: UUID) -> None:
    if not (config.UPLOAD_DIR / pdf_id.hex / "paper.pdf").is_file():
        raise HTTPException(404, "PDF 文件不存在。")


@router.get("/pdf/{pdf_id}/{channel}")
def list_reader_entries(
    pdf_id: UUID, channel: Channel
) -> list[AnnotationResult] | list[ReaderNoteResult]:
    require_pdf(pdf_id)
    table = TABLES[channel].__table__
    result_type = AnnotationResult if channel == "annotations" else ReaderNoteResult
    statement = (
        select(table)
        .where(table.c.pdf_id == pdf_id)
        .order_by(table.c.updated_at.desc(), table.c.id)
    )
    with SessionLocal() as session:
        return [
            result_type.model_validate(row)
            for row in session.execute(statement).mappings()
        ]


def save_reader_entry(
    pdf_id: UUID, entry_id: UUID, channel: Channel, payload: ReaderNoteInput
) -> AnnotationResult | ReaderNoteResult:
    table = TABLES[channel].__table__
    values = payload.model_dump(mode="json")
    statement = (
        insert(table)
        .values(id=entry_id, pdf_id=pdf_id, **values)
        .on_conflict_do_update(
            index_elements=[table.c.id],
            set_={**values, "updated_at": func.now()},
            where=table.c.pdf_id == pdf_id,
        )
        .returning(*table.c)
    )
    result_type = AnnotationResult if channel == "annotations" else ReaderNoteResult
    with SessionLocal.begin() as session:
        lock_pdf(session, pdf_id)
        require_pdf(pdf_id)
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, "记录不存在。")
        return result_type.model_validate(row)


@router.put("/pdf/{pdf_id}/annotations/{entry_id}")
def save_annotation(
    pdf_id: UUID, entry_id: UUID, payload: AnnotationInput
) -> AnnotationResult:
    return save_reader_entry(pdf_id, entry_id, "annotations", payload)


@router.put("/pdf/{pdf_id}/notes/{entry_id}")
def save_note(
    pdf_id: UUID, entry_id: UUID, payload: ReaderNoteInput
) -> ReaderNoteResult:
    return save_reader_entry(pdf_id, entry_id, "notes", payload)


@router.delete("/pdf/{pdf_id}/{channel}/{entry_id}", status_code=204)
def delete_reader_entry(pdf_id: UUID, channel: Channel, entry_id: UUID) -> Response:
    require_pdf(pdf_id)
    table = TABLES[channel].__table__
    with SessionLocal.begin() as session:
        session.execute(
            delete(table).where(table.c.pdf_id == pdf_id, table.c.id == entry_id)
        )
    return Response(status_code=204)
