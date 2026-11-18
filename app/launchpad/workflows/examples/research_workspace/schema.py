from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    HttpUrl,
    RootModel,
    StringConstraints,
    model_validator,
)

LibraryName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
PaperId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


Keyword = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Keywords = Annotated[list[Keyword], Field(max_length=20)]
PDF_BATCH_LIMIT = 20


class Asset(BaseModel):
    kind: Literal["code", "dataset"]
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl


class Publication(BaseModel):
    venue: str | None = Field(default=None, max_length=250)
    venue_type: Literal["conference", "journal", "preprint", "unknown"]
    year: int | None = Field(default=None, ge=1800, le=2100)
    ccf_rank: Literal["A", "B", "C"] | None = None


class NotionParent(BaseModel):
    kind: str
    id: UUID | None = None


class PdfMetadata(BaseModel):
    publication: Publication | None = None
    id: PaperId | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    source_url: HttpUrl | None = None
    abstract: str = Field(default="", max_length=6000)
    assets: list[Asset] = Field(default_factory=list, max_length=30)
    keywords: Keywords = Field(default_factory=list)
    pdf_run_id: UUID | None = None


class Paper(BaseModel):
    id: PaperId
    title: str = Field(min_length=1, max_length=500)
    source_kind: Literal["paper", "notion"] = "paper"
    abstract: str = Field(default="", max_length=6000)
    source_url: HttpUrl | None = None
    publication: Publication | None = None
    pdf_run_id: UUID | None = None
    pdf_sha256: str | None = None
    assets: list[Asset] = Field(default_factory=list, max_length=30)
    keywords: Keywords = Field(default_factory=list)
    notion_parent: NotionParent | None = None

    def search_text(self) -> str:
        return " ".join(
            [
                self.title,
                self.abstract,
                *self.keywords,
                *(asset.name for asset in self.assets),
            ]
        )


class ResearchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library: LibraryName


class ImportEvent(ResearchEvent):
    papers: list[Paper] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_ids(self) -> "ImportEvent":
        if len({paper.id for paper in self.papers}) != len(self.papers):
            raise ValueError("paper IDs must be unique within an import")
        return self


class PreviousTurn(BaseModel):
    question: str
    answer: str


class SearchEvent(ResearchEvent):
    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    keywords: str | None = Field(default=None, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)
    previous_turns: list[PreviousTurn] = Field(default_factory=list, max_length=6)


class PdfRegion(BaseModel):
    page: int
    left: float
    top: float
    right: float
    bottom: float


class PaperChunk(BaseModel):
    number: int = Field(ge=1)
    text: str = Field(min_length=1)
    headings: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    regions: list[PdfRegion] = Field(default_factory=list)


class SearchHit(BaseModel):
    paper: Paper
    score: float
    chunk: PaperChunk | None = None
    locator: str | None = None


class MeetingNote(BaseModel):
    paper: Paper
    markdown: str = Field(exclude=True)
    reconstructed: bool = False


class ReadingNote(BaseModel):
    answer: str
    cited_paper_ids: list[PaperId]
    cited_chunk_ids: list[str] = Field(default_factory=list)


class CitedPassage(PaperChunk):
    paper_id: PaperId
    locator: str | None = None


class ReadingResult(BaseModel):
    note: ReadingNote
    sources: list[Paper]
    passages: dict[str, CitedPassage] = Field(default_factory=dict)


class ReadingPlan(BaseModel):
    semantic_query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    keywords: str | None = Field(default=None, max_length=500)
    compare: bool
    asset_kinds: list[Literal["code", "dataset"]] = Field(max_length=2)


class PdfImportEvent(ResearchEvent):
    paper: PdfMetadata
    pdf_path: str
    enrich_metadata: bool = False
    match_existing: bool = False
    batch_id: UUID | None = None
    batch_position: int | None = None
    filename: str | None = None


class ConversationMessage(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    timestamp: AwareDatetime
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=6000)
    conversation_id: UUID | None = None
    conversation_title: str | None = None


class WeeklyReportEvent(ResearchEvent):
    week_start: date = Field(
        default_factory=lambda: (
            datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=6)
        )
    )
    week_end: date | None = None
    conversation_scope: Literal["all", "library"] = "all"
    messages: list[ConversationMessage] | None = Field(
        default=None, min_length=1, max_length=250
    )

    @model_validator(mode="after")
    def check_week(self) -> "WeeklyReportEvent":
        self.week_end = self.week_end or self.week_start + timedelta(days=6)
        if self.week_end < self.week_start:
            raise ValueError("结束日期不能早于开始日期。")
        if self.messages and len({item.id for item in self.messages}) != len(
            self.messages
        ):
            raise ValueError("message IDs must be unique")
        return self


class WeeklyItem(BaseModel):
    text: str
    message_ids: list[str] = Field(min_length=1)


class WeeklyReport(BaseModel):
    completed: list[WeeklyItem]
    findings: list[WeeklyItem]
    blockers: list[WeeklyItem]
    next_week: list[WeeklyItem]
    focus: list[WeeklyItem] = Field(default_factory=list)


HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class PresentationTheme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    background: HexColor = "#FFFFFF"
    text: HexColor = "#182230"
    accent: HexColor = "#2563EB"
    font: Annotated[str, StringConstraints(pattern=r"^[\w -]{1,60}$")] = "Aptos"
    chart: Literal["column", "bar", "line"] = "column"


class MeetingSkillSummary(BaseModel):
    id: UUID
    name: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64),
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)
    ]
    theme: PresentationTheme | None = None


class MeetingSkill(MeetingSkillSummary):
    instructions: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24000)
    ]
    renderer: Literal["research-ppt-skill"] | None = None

    @property
    def uses_academic_layout(self) -> bool:
        return (
            self.renderer == "research-ppt-skill" or self.name == "research-ppt-skill"
        )


class MeetingEvent(SearchEvent):
    weekly_report: str = Field(default="", max_length=30000)
    workbook_path: str | None = None
    worksheet: str | None = Field(default=None, min_length=1, max_length=31)
    category_column: str | None = Field(default=None, min_length=1, max_length=100)
    value_column: str | None = Field(default=None, min_length=1, max_length=100)
    source_ids: list[PaperId] = Field(default_factory=list, max_length=10)
    style_skill: MeetingSkill | None = None

    @property
    def uses_academic_layout(self) -> bool:
        return self.style_skill is None or self.style_skill.uses_academic_layout


class ExperimentPoint(BaseModel):
    category: str
    value: FiniteFloat
    row: int


class ExperimentSeries(BaseModel):
    worksheet: str
    category_column: str
    value_column: str
    points: list[ExperimentPoint] = Field(min_length=1, max_length=100)


MeetingSlidePurpose = Literal[
    "overview", "progress", "background", "method", "results", "risks", "plan"
]


class MeetingSlide(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    bullets: list[Annotated[str, StringConstraints(max_length=240)]] = Field(
        min_length=1, max_length=4
    )
    evidence_ids: list[str] = Field(max_length=10)
    purpose: MeetingSlidePurpose | None = None


class MeetingOutline(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    slides: list[MeetingSlide] = Field(min_length=1, max_length=8)
    theme: PresentationTheme | None = None


class PresentationResult(BaseModel):
    filename: str
    url: str
    renderer: Literal["research-ppt-skill"] | None = None


class NotionImportEvent(ResearchEvent):
    page_id: UUID | None = None
    resource_id: PaperId | None = None
    keywords: Keywords = Field(default_factory=list)
    title: str = Field(min_length=1, max_length=500)
    source_url: HttpUrl
    notion_parent: NotionParent | None = None
    markdown: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60000)
    ]


class NotionPageImportEvent(ResearchEvent):
    page_id: UUID


class NotionWorkflowEvent(RootModel[NotionImportEvent | NotionPageImportEvent]):
    pass


class TranslationEvent(ResearchEvent):
    text: Annotated[str, Field(min_length=1, max_length=12000)]
