"""Standalone MCP process for rendering editable PowerPoint slides."""

from pathlib import Path
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from . import config
from .schema import ExperimentSeries, MeetingOutline, PresentationResult, SearchHit

server = MCPServer("research-presentation")


@server.tool()
def render_meeting_pptx(
    outline: MeetingOutline, experiment: ExperimentSeries, evidence: list[SearchHit]
) -> PresentationResult:
    """Create a PowerPoint with literature citations and an editable Excel-derived chart."""
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches, Pt

    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    cover = deck.slides.add_slide(deck.slide_layouts[0])
    cover.shapes.title.text = outline.title

    for item in outline.slides:
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = item.title
        box = slide.shapes.add_textbox(
            Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.6)
        )
        for index, text in enumerate(item.bullets):
            paragraph = (
                box.text_frame.paragraphs[0]
                if index == 0
                else box.text_frame.add_paragraph()
            )
            paragraph.text = text
            paragraph.font.size = Pt(19)
            paragraph.space_after = Pt(10)
        box.text_frame.word_wrap = True
        if item.evidence_ids:
            footer = slide.shapes.add_textbox(
                Inches(0.8), Inches(6.65), Inches(11.7), Inches(0.5)
            )
            footer.text_frame.text = "文献证据 " + "  ".join(item.evidence_ids)

    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = f"实验结果 · {experiment.value_column}"
    chart_data = CategoryChartData()
    chart_data.categories = [point.category for point in experiment.points]
    chart_data.add_series(
        experiment.value_column, [point.value for point in experiment.points]
    )
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1),
        Inches(1.5),
        Inches(11.3),
        Inches(4.9),
        chart_data,
    )
    source = slide.shapes.add_textbox(Inches(1), Inches(6.6), Inches(11.3), Inches(0.5))
    source.text_frame.text = (
        f"来源：工作表 {experiment.worksheet} · {experiment.category_column} / {experiment.value_column}"
        f" · {len(experiment.points)} 条数据"
    )

    for start in range(0, len(evidence), 5):
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = "文献出处"
        box = slide.shapes.add_textbox(
            Inches(0.8), Inches(1.5), Inches(11.7), Inches(5.4)
        )
        box.text_frame.word_wrap = True
        for index, hit in enumerate(evidence[start : start + 5], start + 1):
            paragraph = (
                box.text_frame.paragraphs[0]
                if index == start + 1
                else box.text_frame.add_paragraph()
            )
            pages = ", ".join(map(str, hit.chunk.pages)) if hit.chunk else ""
            run = paragraph.add_run()
            run.text = f"[C{index}] {hit.paper.title}" + (
                f" · 页 {pages}" if pages else ""
            )
            if hit.paper.source_url:
                run.hyperlink.address = str(hit.paper.source_url)
            run.font.size = Pt(16)
            paragraph.space_after = Pt(11)

    directory = Path(config.PPT_OUTPUT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.pptx"
    deck.save(directory / filename)
    return PresentationResult(filename=filename, url=f"/research/decks/{filename}")


if __name__ == "__main__":
    server.run()
