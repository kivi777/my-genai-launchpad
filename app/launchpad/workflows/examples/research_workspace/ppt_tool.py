"""Standalone MCP process for rendering editable PowerPoint slides."""

from pathlib import Path
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import config
from .academic_ppt import render_academic_deck
from .schema import (
    ExperimentSeries,
    MeetingOutline,
    PresentationResult,
    PresentationTheme,
    SearchHit,
)

server = MCPServer("research-presentation")


@server.tool()
def render_meeting_pptx(
    outline: MeetingOutline,
    experiment: ExperimentSeries | None,
    evidence: list[SearchHit],
    theme: PresentationTheme | None = None,
    academic_layout: bool = False,
) -> PresentationResult:
    """Create a PowerPoint with literature citations and an editable Excel-derived chart."""
    directory = Path(config.PPT_OUTPUT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.pptx"
    result = PresentationResult(filename=filename, url=f"/research/decks/{filename}")
    if academic_layout:
        try:
            render_academic_deck(
                outline, experiment, evidence, theme, directory / filename
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return result.model_copy(update={"renderer": "research-ppt-skill"})

    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.enum.shapes import MSO_SHAPE
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

    chart = None
    if experiment:
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = f"实验结果 · {experiment.value_column}"
        chart_data = CategoryChartData()
        chart_data.categories = [point.category for point in experiment.points]
        chart_data.add_series(
            experiment.value_column, [point.value for point in experiment.points]
        )
        chart_types = {
            "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "bar": XL_CHART_TYPE.BAR_CLUSTERED,
            "line": XL_CHART_TYPE.LINE_MARKERS,
        }
        chart = slide.shapes.add_chart(
            chart_types[theme.chart if theme else "column"],
            Inches(1),
            Inches(1.5),
            Inches(11.3),
            Inches(4.9),
            chart_data,
        ).chart
        source = slide.shapes.add_textbox(
            Inches(1), Inches(6.6), Inches(11.3), Inches(0.5)
        )
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

    if theme:
        background = RGBColor.from_string(theme.background[1:])
        text_color = RGBColor.from_string(theme.text[1:])
        accent = RGBColor.from_string(theme.accent[1:])
        for slide in deck.slides:
            fill = slide.background.fill
            fill.solid()
            fill.fore_color.rgb = background
            stripe = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, 0, 0, deck.slide_width, Inches(0.08)
            )
            stripe.fill.solid()
            stripe.fill.fore_color.rgb = accent
            stripe.line.fill.background()
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for paragraph in shape.text_frame.paragraphs:
                    paragraph.font.name = theme.font
                    paragraph.font.color.rgb = text_color
                    for run in paragraph.runs:
                        run.font.name = theme.font
                        run.font.color.rgb = text_color
        if chart is not None:
            series_format = chart.series[0].format
            if theme.chart == "line":
                series_format.line.color.rgb = accent
            else:
                series_format.fill.solid()
                series_format.fill.fore_color.rgb = accent
            for axis in (chart.category_axis, chart.value_axis):
                axis.tick_labels.font.name = theme.font
                axis.tick_labels.font.color.rgb = text_color

    deck.save(directory / filename)
    return result


if __name__ == "__main__":
    server.run()
