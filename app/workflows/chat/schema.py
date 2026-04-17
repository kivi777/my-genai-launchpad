from pydantic import BaseModel


class ChatCompletionEventSchema(BaseModel):
    id: str
    role: str
    content: str
