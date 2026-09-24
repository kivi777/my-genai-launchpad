import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import boto3
from dotenv import load_dotenv
from google.oauth2 import service_account
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelName
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelName
from pydantic_ai.models.google import GoogleModel, GoogleModelName
from pydantic_ai.models.openai import (
    OpenAIModelName,
    OpenAIChatModel,
    OpenAIResponsesModel,
)
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.google_cloud import GoogleCloudProvider
from pydantic_ai.providers.ollama import OllamaProvider

from launchpad.core.nodes.pydantic_ai_node import PydanticAIConfig, PydanticAINode

load_dotenv()


class ModelProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"
    GOOGLE_GEMINI = "google"
    GOOGLE_VERTEX_AI = "google_vertex_ai"


@dataclass(kw_only=True)
class AgentConfig(PydanticAIConfig):
    model_provider: ModelProvider
    model_name: (
        OpenAIModelName | AnthropicModelName | GoogleModelName | BedrockModelName
    )


class AgentNode(PydanticAINode, ABC):
    """LLM node. Pick the provider with `AgentConfig.model_provider`."""

    @abstractmethod
    def get_agent_config(self) -> AgentConfig:
        pass

    def build_model(self, config: AgentConfig) -> Model:
        return self.__get_model_instance(config.model_provider, config.model_name)

    def __get_model_instance(self, provider: ModelProvider, model_name: str) -> Model:
        match provider.value:
            case provider.OPENAI.value:
                return self.__get_openai_model(model_name)
            case provider.AZURE_OPENAI.value:
                return self.__get_azure_openai_model(model_name)
            case provider.ANTHROPIC.value:
                return self.__get_anthropic_model(model_name)
            case provider.OLLAMA.value:
                return self.__get_ollama_model(model_name)
            case provider.BEDROCK.value:
                return self.__get_bedrock_model(model_name)
            case provider.GOOGLE_GEMINI.value:
                return self.__get_google_gemini_model(model_name)
            case provider.GOOGLE_VERTEX_AI.value:
                return self.__get_google_vertex_ai_model(model_name)
        return self.__get_openai_model(model_name)

    def __get_openai_model(self, model_name) -> Model:
        return OpenAIResponsesModel(model_name=model_name)

    def __get_azure_openai_model(self, model_name) -> Model:
        provider = AzureProvider(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        )
        return OpenAIResponsesModel(
            model_name=model_name,
            provider=provider,
        )

    def __get_anthropic_model(self, model_name: AnthropicModelName) -> Model:
        return AnthropicModel(
            model_name=model_name,
            provider=AnthropicProvider(),
        )

    def __get_ollama_model(self, model_name: str) -> Model:
        base_url = os.getenv("OLLAMA_BASE_URL")
        if not base_url:
            raise KeyError("OLLAMA_BASE_URL not set in .env")

        return OpenAIChatModel(
            model_name=model_name, provider=OllamaProvider(base_url=base_url)
        )

    def __get_bedrock_model(self, model_name: str) -> Model:
        aws_access_key_id = os.getenv("BEDROCK_AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("BEDROCK_AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("BEDROCK_AWS_REGION")

        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        return BedrockConverseModel(
            model_name=model_name,
            provider=BedrockProvider(bedrock_client=bedrock_client),
        )

    def __get_google_gemini_model(self, model_name: str) -> Model:
        return GoogleModel(
            model_name=model_name,
            provider=GoogleProvider(),
        )

    def __get_google_vertex_ai_model(self, model_name: str) -> Model:
        credentials = service_account.Credentials.from_service_account_file(
            filename=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        provider = GoogleCloudProvider(
            credentials=credentials,
            location=os.getenv("GOOGLE_VERTEX_AI_LOCATION", "europe-west1"),
        )
        return GoogleModel(
            model_name=model_name,
            provider=provider,
        )
