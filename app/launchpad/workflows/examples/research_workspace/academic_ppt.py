import json
import logging
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .academic_ppt_layout import chart_page, content_page, source_pages
from .schema import ExperimentSeries, MeetingOutline, PresentationTheme, SearchHit

logger = logging.getLogger(__name__)
_SCRIPTS = Path(__file__).parent / "skills/research-ppt-skill/ppt_scripts"


def _run_skill_script(name: str, *arguments: Path | str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPTS / name), *map(str, arguments)],
        env={"PYTHONDONTWRITEBYTECODE": "1", "PPT_THEME": "blue"},
        timeout=20,
        capture_output=True,
        text=True,
    )


def render_academic_deck(
    outline: MeetingOutline,
    experiment: ExperimentSeries | None,
    evidence: list[SearchHit],
    theme: PresentationTheme | None,
    destination: Path,
) -> None:
    from pptx import Presentation

    cover = {
        "type": "cover",
        "style": "panel",
        "title": outline.title,
        "panel_title": "科研汇报",
        "size": 20 if len(outline.title) > 64 else 32,
    }
    references, links = source_pages(
        evidence,
        {citation for slide in outline.slides for citation in slide.evidence_ids},
    )
    appendix = []
    if experiment:
        kind = (
            {"column": "bar", "bar": "barh", "line": "line"}[theme.chart]
            if theme
            else "bar"
        )
        appendix.append(
            chart_page(
                experiment.value_column,
                experiment.worksheet,
                experiment.category_column,
                {
                    "type": "chart",
                    "kind": kind,
                    "categories": [point.category for point in experiment.points],
                    "series": [
                        {
                            "name": experiment.value_column,
                            "values": [point.value for point in experiment.points],
                        }
                    ],
                },
            )
        )
    appendix.extend(references)

    with TemporaryDirectory(prefix="research-ppt-") as temporary:
        source = Path(temporary) / "content.json"
        generated = source.with_name("slides.pptx")
        diagnostics = source.with_name("lint.json")
        wide_pages: set[int] = set()
        for attempt in range(2):
            slides = [
                cover,
                *(
                    content_page(slide, wide=index in wide_pages)
                    for index, slide in enumerate(outline.slides, 2)
                ),
                *appendix,
            ]
            source.write_text(
                json.dumps(
                    {"title": outline.title, "slides": slides}, ensure_ascii=False
                ),
                encoding="utf-8",
            )
            render = _run_skill_script(
                "dense_deck.py", "--content", source, "--output", generated
            )
            if render.returncode:
                raise ValueError("科研排版脚本生成失败，请检查大纲和图表数据。")
            lint = _run_skill_script(
                "lint.py", "--input", generated, "--json", diagnostics
            )
            if lint.returncode not in (0, 1) or not diagnostics.exists():
                raise ValueError("科研 PPT 版式检查未能运行。")
            issues = json.loads(diagnostics.read_text(encoding="utf-8"))
            overflow = {
                issue["slide"]
                for issue in issues
                if issue["level"] == "error"
                and issue["message"].startswith(("文字可能溢出", "超出页面边界"))
            }
            if not overflow:
                break
            if attempt or not overflow.issubset(range(2, len(outline.slides) + 2)):
                pages = "、".join(map(str, sorted(overflow)))
                raise ValueError(
                    f"PPT 第 {pages} 页内容超出版面，请缩短该页内容后重试。"
                )
            wide_pages = overflow

        audit = _run_skill_script("spec_audit.py", source, generated, "Launchpad")
        if audit.returncode or "\n不合规 " in audit.stdout:
            logger.warning("research_ppt_spec_audit_review_required")

        deck = Presentation(generated)
        for slide in list(deck.slides)[len(deck.slides) - len(references) :]:
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for paragraph in shape.text_frame.paragraphs:
                    url = links.get(paragraph.text)
                    if url:
                        for run in paragraph.runs:
                            run.hyperlink.address = url
        deck.save(destination)
