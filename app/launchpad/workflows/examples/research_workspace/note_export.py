from urllib.parse import urljoin

from pydantic import BaseModel

from . import config
from .schema import ReadingResult


class NoteDraft(BaseModel):
    title: str
    markdown: str


def render_note(question: str, result: ReadingResult) -> NoteDraft:
    note = result.note
    papers = {paper.id: paper for paper in result.sources}
    sections = [f"## 研究问题\n\n{question}", f"## 文献汇总\n\n{note.answer}"]
    if result.passages:
        sources = []
        for passage in result.passages.values():
            paper = papers[passage.paper_id]
            pages = ", ".join(map(str, passage.pages)) or "无页码"
            heading = " / ".join(passage.headings)
            url = (
                urljoin(config.API_URL, passage.locator)
                if passage.locator
                else paper.source_url
            )
            title = f"[{paper.title}]({url})" if url else paper.title
            sources.append(
                f"- {title} · 页码 {pages} · 片段 {passage.number}"
                + (f" · {heading}" if heading else "")
            )
        sections.append("## 证据出处\n\n" + "\n".join(sources))
    return NoteDraft(title=question.strip()[:100], markdown="\n\n".join(sections))
