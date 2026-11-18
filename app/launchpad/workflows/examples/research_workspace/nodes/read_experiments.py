import asyncio
from itertools import chain, islice

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..schema import ExperimentPoint, ExperimentSeries, MeetingEvent


def _select_column(options: list[int], headers: tuple, query: str) -> int | None:
    match = next(
        (index for index in options if str(headers[index]).casefold() in query), None
    )
    return match if match is not None else next(iter(options), None)


def read_series(event: MeetingEvent) -> ExperimentSeries:
    from openpyxl import load_workbook

    workbook = load_workbook(
        event.workbook_path, read_only=True, data_only=True, keep_links=False
    )
    try:
        sheets = [workbook[event.worksheet]] if event.worksheet else workbook.worksheets
        query = event.query.casefold()
        for sheet in sheets:
            rows = iter(sheet.values)
            headers = next(rows, ())
            sample = list(islice(rows, 20))
            available = [
                index
                for index, header in enumerate(headers)
                if header not in (None, "") and headers.count(header) == 1
            ]
            values = [
                index
                for index in available
                if any(type(row[index]) in (int, float) for row in sample)
            ]
            explicit = (
                event.category_column is not None or event.value_column is not None
            )
            if event.value_column:
                values = [
                    index for index in available if headers[index] == event.value_column
                ]
            value = _select_column(values, headers, query)
            categories = [index for index in available if index != value]
            if event.category_column:
                categories = [
                    index
                    for index in categories
                    if headers[index] == event.category_column
                ]
            elif any(index not in values for index in categories):
                categories = [index for index in categories if index not in values]
            category = _select_column(categories, headers, query)
            if value is None or category is None:
                continue
            points = []
            for row_number, row in enumerate(chain(sample, rows), 2):
                if row_number > 10001:
                    raise ValueError("实验表格超过 10,000 行。")
                if row[category] is None and row[value] is None:
                    continue
                if row[category] is None or type(row[value]) not in (int, float):
                    if explicit:
                        raise ValueError(f"第 {row_number} 行需要类别和数值。")
                    continue
                points.append(
                    ExperimentPoint(
                        category=str(row[category])[:100],
                        value=row[value],
                        row=row_number,
                    )
                )
                if len(points) > 100:
                    raise ValueError("实验图表最多支持 100 条数据。")
            if points:
                return ExperimentSeries(
                    worksheet=sheet.title,
                    category_column=str(headers[category]),
                    value_column=str(headers[value]),
                    points=points,
                )
        raise ValueError(
            "未找到可绘图的数据。请在首行填写列名，并提供一列类别和一列有效数值。"
        )
    finally:
        workbook.close()


class ReadExperimentsNode(Node):
    async def process(self, task_context: TaskContext) -> TaskContext:
        if task_context.event.workbook_path:
            self.save_output(await asyncio.to_thread(read_series, task_context.event))
        return task_context
