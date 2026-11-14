from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from . import config


def deepseek_model(name: str) -> OpenAIChatModel:
    if not config.DEEPSEEK_API_KEY:
        raise RuntimeError("Set DEEPSEEK_API_KEY for the research workspace")
    return OpenAIChatModel(
        name,
        provider=OpenAIProvider(
            base_url=config.DEEPSEEK_BASE_URL, api_key=config.DEEPSEEK_API_KEY
        ),
    )
