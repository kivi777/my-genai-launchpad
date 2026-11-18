import re
from dataclasses import dataclass, field

from .schema import MeetingSlide, MeetingSlidePurpose, Paper, SearchHit


def _display_width(text: str) -> float:
    return sum(1 if ord(character) > 255 else 0.5 for character in text)


def _shorten(text: str, width: int) -> str:
    if _display_width(text) <= width:
        return text
    end = 0
    for end in range(1, len(text) + 1):
        if _display_width(text[:end]) >= width - 1:
            break
    prefix = text[:end].strip()
    if text[end - 1].isascii() and text[end].isascii() and " " in prefix:
        prefix = prefix.rsplit(" ", 1)[0]
    return prefix.rstrip("：:，,；;") + "…"


def _purpose(slide: MeetingSlide) -> MeetingSlidePurpose | None:
    if slide.purpose is not None:
        return slide.purpose
    heading = re.split(r"[:：]", slide.title, maxsplit=1)[0].lower()
    labels: dict[MeetingSlidePurpose, str] = {
        "overview": r"目录|汇报内容|汇报安排|概览|\bagenda\b|\boverview\b",
        "plan": r"下周|下一步|计划|\bnext steps\b",
        "risks": r"瓶颈|限制|风险|待验证|\blimitations?\b|\brisks?\b",
        "progress": r"进展|已完成|\bprogress\b",
        "background": r"动机|背景|问题设定|\bbackground\b|\bmotivation\b",
        "method": r"方法|算法|\bmethod\b|\bapproach\b",
        "results": r"数据与|结果|对比|\bresults?\b|\bcomparison\b",
    }
    return next(
        (role for role, pattern in labels.items() if re.search(pattern, heading)), None
    )


def _point(value: str, label: str) -> dict[str, str]:
    parts = re.split(r"[:：]\s*", value, maxsplit=1)
    if len(parts) == 2 and parts[1] and _display_width(parts[0]) <= 11:
        return {"label": parts[0], "text": parts[1]}
    return {"label": label, "text": value}


def _without_repeated_citation(text: str, footer_ids: set[str]) -> str:
    match = re.search(r"\s*[（(](C\d+)[）)]\s*$", text)
    return (
        text[: match.start()]
        if match and match.start() and match[1] in footer_ids
        else text
    )


def _step_detail(point: dict[str, str], index: int) -> dict[str, str]:
    label = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", point["label"])
    text = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", point["text"])
    if label == f"要点 {index}":
        label, *detail = re.split(r"[,，:：]\s*", text, maxsplit=1)
        text = detail[0] if detail else ""
    return {"title": label, "text": text}


def _region(*items: dict, **style: str | float | bool) -> dict:
    return {"items": list(items), "pad": 0.18, **style}


def _section(heading: str, points: list[dict]) -> dict:
    return {
        "type": "section",
        "head": heading,
        "head_align": "center",
        "items": points,
        "max_size": 19,
        "after": 12,
        "valign": "middle",
        "grow": True,
    }


def _rows(points: list[dict]) -> dict:
    return {
        "type": "label_rows",
        "items": points,
        "label_color": "navy",
        "label_w": 2.25,
        "max_size": 19,
    }


def _note(point: dict) -> dict:
    return {
        "type": "note",
        "title": point["label"],
        "text": point["text"],
        "align": "left",
        "max_size": 19,
        "grow": True,
    }


def _page(title: str, layout: str, regions: dict, summary: str = "") -> dict:
    return {
        "style": "info",
        "title": title,
        "layout": layout,
        "regions": regions,
        **({"summary": summary} if summary else {}),
    }


def content_page(slide: MeetingSlide, *, wide: bool = False) -> dict:
    purpose = _purpose(slide)
    title_split = re.split(r"[:：]\s*", slide.title, maxsplit=1)
    title = _shorten(title_split[0], 14)
    lead = slide.title if len(title_split) == 1 and title != slide.title else None
    if len(title_split) == 2 and title_split[1]:
        lead = title_split[1]
    summary = "参考资料 " + "、".join(slide.evidence_ids) if slide.evidence_ids else ""
    footer_ids = set(slide.evidence_ids)
    points = [
        _point(_without_repeated_citation(bullet, footer_ids), f"要点 {i}")
        for i, bullet in enumerate(slide.bullets, 1)
    ]
    count = len(points)
    stages = [stage.strip() for stage in (lead or "").split("→")]
    process = purpose == "method" and not wide and 3 <= len(stages) <= 5 and all(stages)

    if wide or any(_display_width(point["text"]) > 100 for point in points):
        layout, regions = (
            "info_full",
            {"main": _region(_section("", points), fill="none")},
        )
    elif purpose == "overview":
        agenda = [{"title": point["label"], "text": point["text"]} for point in points]
        layout, regions = (
            "info_full",
            {
                "main": _region(
                    {
                        "type": "numbered",
                        "items": agenda,
                        "title_w": 0.22,
                        "text_size": 19,
                    },
                    fill="none",
                )
            },
        )
    elif purpose == "progress" and count >= 2:
        table = {
            "type": "table",
            "columns": ["事项", "进展"],
            "rows": [[item["label"], item["text"]] for item in points[:-1]],
            "widths": [2, 8],
            "align": ["center", "left"],
            "size": 19,
        }
        layout, regions = (
            "info_focus",
            {
                "main": _region(table, fill="none", pad=0),
                "bottom": _region(_note(points[-1]), fill="none", pad=0),
            },
        )
    elif purpose == "background" and count >= 2:
        layout, regions = (
            "info_split",
            {
                "left": _region(_section("研究问题", points[: (count + 1) // 2])),
                "right": _region(_section("背景与范围", points[(count + 1) // 2 :])),
            },
        )
    elif process:
        detail_rows = [_step_detail(point, i) for i, point in enumerate(points, 1)]
        details = (
            {"type": "steps_v", "items": detail_rows, "size": 19}
            if all(re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", bullet) for bullet in slide.bullets)
            else _section("", points)
        )
        layout, regions = (
            "info_full",
            {
                "main": _region(
                    details,
                    fill="frame",
                    band="实现细节",
                    pad=0.28,
                )
            },
        )
    elif purpose == "method" and count >= 2:
        layout, regions = (
            "info_stack",
            {
                "top": _region(_section("方法要点", points[:1]), fill="light"),
                "bottom": _region(_section("细节与条件", points[1:])),
            },
        )
    elif (
        purpose == "results"
        and count == 4
        and max(_display_width(item["text"]) for item in points[:3]) <= 60
    ):
        layout, regions = (
            "info_three_strip",
            {
                **{
                    slot: _region(_note(point), fill="none", pad=0)
                    for slot, point in zip("abc", points)
                },
                "bottom": _region(_note(points[-1]), fill="none", pad=0),
            },
        )
    elif purpose == "risks" and count >= 3:
        layout, regions = (
            "info_rows3",
            {
                "r1": _region(_rows(points[:1]), fill="none", pad=0),
                "r2": _region(_rows(points[1:2]), fill="none", pad=0),
                "r3": _region(_rows(points[2:]), fill="none", pad=0),
            },
        )
    elif purpose == "plan" and count >= 3:
        layout = "info_quad" if count == 4 else "info_three"
        regions = {
            slot: _region(_note(point), fill="none", pad=0)
            for slot, point in zip("abcd", points)
        }
    elif count >= 2:
        layout, regions = (
            "info_compare",
            {
                "left": _region(_section("要点", points[: (count + 1) // 2])),
                "right": _region(_section("补充", points[(count + 1) // 2 :])),
            },
        )
    else:
        layout, regions = (
            "info_full",
            {"main": _region(_note(points[0]), fill="none", pad=0)},
        )

    page = _page(title, layout, regions, summary)
    if process:
        page["process"] = {
            "items": [_shorten(stage, 12) for stage in stages],
            "gradient": True,
            "size": 18,
        }
        page["notes"] = slide.title
    elif lead:
        page["lead"] = _shorten(lead, 40)
        if page["lead"] != lead:
            page["notes"] = slide.title
    return page


@dataclass
class _Source:
    paper: Paper
    citations: list[str] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)

    @property
    def details(self) -> str:
        pages = "、".join(map(str, sorted(self.pages)))
        return (
            "引用 " + "、".join(self.citations) + (f" · 第 {pages} 页" if pages else "")
        )


def source_pages(
    evidence: list[SearchHit], cited: set[str]
) -> tuple[list[dict], dict[str, str]]:
    sources: dict[str, _Source] = {}
    for index, hit in enumerate(evidence, 1):
        citation = f"C{index}"
        if citation in cited:
            source = sources.setdefault(hit.paper.id, _Source(hit.paper))
            source.citations.append(citation)
            if hit.chunk:
                source.pages.update(hit.chunk.pages)

    pages, links = [], {}
    entries = list(sources.values())
    for start in range(0, len(entries), 4):
        batch = entries[start : start + 4]
        if len(batch) == 1:
            source = batch[0]
            label = "Notion 笔记" if source.paper.source_kind == "notion" else "论文"
            layout, regions = (
                "info_hero_left",
                {
                    "side": _region(
                        _note({"label": label, "text": source.details}), fill="none"
                    ),
                    "main": _region(
                        {
                            "type": "para",
                            "text": source.paper.title,
                            "align": "left",
                            "size": 21,
                        },
                        fill="frame",
                    ),
                },
            )
            if source.paper.source_url:
                links[source.paper.title] = str(source.paper.source_url)
        else:
            items = []
            for source in batch:
                label = f"{source.paper.title} · {source.details}"
                items.append(
                    {"type": "para", "text": label, "align": "left", "size": 17}
                )
                if source.paper.source_url:
                    links[label] = str(source.paper.source_url)
            layout, regions = (
                "info_full",
                {"main": _region(*items, fill="none", gap=0.24)},
            )
        pages.append(_page("资料出处", layout, regions))
    return pages, links


def chart_page(
    value_column: str, worksheet: str, category_column: str, chart: dict
) -> dict:
    page = _page(
        "实验结果",
        "info_full",
        {"main": _region(chart, fill="none", pad=0)},
        _shorten(f"工作表 {worksheet} · {category_column}", 40),
    )
    page["lead"] = _shorten(value_column, 40)
    return page
