from pydantic import BaseModel


class TicketEvent(BaseModel):
    message: str
