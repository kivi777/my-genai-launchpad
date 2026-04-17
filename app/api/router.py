from fastapi import APIRouter

from api import events
from api import openai
from workflows.chat.routes import router as chat_router

"""
API Router Module

This module sets up the API router and includes all defined endpoints.
It uses FastAPI's APIRouter to group related endpoints and provide a prefix.
"""

router = APIRouter()

router.include_router(events.router, prefix="/events", tags=["events"])
router.include_router(openai.router, prefix="/v1", tags=["openai"])
router.include_router(chat_router, prefix="/chat", tags=["chat"])
