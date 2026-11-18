import logging
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from launchpad.database.event import Event
from launchpad.database.repository import GenericRepository
from launchpad.database.session import db_session
from launchpad.worker.config import celery_app
from launchpad.workflows.examples.research_workspace.observability import (
    TaskMonitor,
    stage,
)
from launchpad.workflows.workflow_registry import WorkflowRegistry

"""
Workflow Task Processing Module

This module handles asynchronous processing of workflow events using Celery.
It manages the lifecycle of event processing from database retrieval through
workflow execution and result storage.
"""


@celery_app.task(name="process_incoming_event")
def process_incoming_event(event_id: str):
    """Processes an incoming event through its designated workflow.

    This Celery task handles the asynchronous processing of events by:
    1. Retrieving the event from the database
    2. Determining the appropriate workflow
    3. Executing the workflow
    4. Storing the results

    Args:
        event_id: Unique identifier of the event to process
        workflow_type: Type of workflow to use for processing the event
    """
    with contextmanager(db_session)() as session:
        # Initialize repository for database operations
        repository = GenericRepository(session=session, model=Event)

        # Retrieve event from database
        db_event = repository.get(id=event_id)
        if db_event is None:
            raise ValueError(f"Event with id {event_id} not found")

        if db_event.workflow_type.startswith("RESEARCH_"):
            queue_ms = (
                max(
                    0,
                    round(
                        (datetime.now() - db_event.created_at).total_seconds() * 1000
                    ),
                )
                if db_event.created_at
                else None
            )
            with TaskMonitor(db_event.id).run(
                db_event.workflow_type,
                db_event.research_conversation_id,
                queue_ms=queue_ms,
            ):
                with stage("initialize"):
                    workflow = WorkflowRegistry[db_event.workflow_type].value()
                task_context = workflow.run(db_event.data)
                with stage("save_result"):
                    db_event.task_context = task_context.model_dump(mode="json")
                    repository.update(obj=db_event)
            return

        # Execute workflow and store results
        workflow = WorkflowRegistry[db_event.workflow_type].value()
        task_context = workflow.run(db_event.data).model_dump(mode="json")

        db_event.task_context = task_context

        # Update event with processing results
        repository.update(obj=db_event)


@celery_app.task(
    name="process_research_pdf_batch", acks_late=True, reject_on_worker_lost=True
)
def process_research_pdf_batch(run_ids: list[str]) -> None:
    from launchpad.workflows.examples.research_workspace.jobs import get_job

    for event_id in run_ids:
        job = get_job(UUID(event_id))
        if job is None or job.status == "completed":
            continue
        try:
            process_incoming_event(event_id)
        except Exception:
            logging.getLogger(__name__).exception(
                "research_batch_paper_failed", extra={"run_id": event_id}
            )
