import asyncio

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..schema import ExperimentPoint, ExperimentSeries, MeetingEvent


def read_series(event: MeetingEvent) -> ExperimentSeries:
    from openpyxl import load_workbook

    workbook = load_workbook(
        event.workbook_path, read_only=True, data_only=True, keep_links=False
    )
    try:
        rows = workbook[event.worksheet].values
        headers = next(rows, ())
        names = (event.category_column, event.value_column)
        if names[0] == names[1] or any(headers.count(name) != 1 for name in names):
            raise ValueError("Choose distinct, unique column names from the first row.")
        category, value = (headers.index(name) for name in names)
        points = []
        for row_number, row in enumerate(rows, 2):
            if row_number > 10001:
                raise ValueError("Worksheet exceeds 10,000 rows.")
            if row[category] is None and row[value] is None:
                continue
            if row[category] is None or type(row[value]) not in (int, float):
                raise ValueError(
                    f"Expected a category and numeric value on row {row_number}."
                )
            points.append(
                ExperimentPoint(
                    category=str(row[category])[:100], value=row[value], row=row_number
                )
            )
            if len(points) > 100:
                raise ValueError(
                    "Select a chart series with no more than 100 data rows."
                )
        return ExperimentSeries(
            worksheet=event.worksheet,
            category_column=names[0],
            value_column=names[1],
            points=points,
        )
    finally:
        workbook.close()


class ReadExperimentsNode(Node):
    async def process(self, task_context: TaskContext) -> TaskContext:
        self.save_output(await asyncio.to_thread(read_series, task_context.event))
        return task_context
