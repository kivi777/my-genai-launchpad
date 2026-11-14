import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEMO_MODE = os.getenv("RESEARCH_DEMO_MODE") == "1"
OFFLINE_MODE = os.getenv("RESEARCH_OFFLINE_MODE") == "1"
USE_SAMPLE_MODELS = DEMO_MODE or OFFLINE_MODE
CHAT_MODEL = os.getenv("RESEARCH_CHAT_MODEL", "deepseek-flash")
INTENT_MODEL = os.getenv("RESEARCH_INTENT_MODEL", "deepseek-flash")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TRACING = (
    os.getenv("RESEARCH_LANGFUSE_ENABLED") == "1"
    and bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
    and bool(os.getenv("LANGFUSE_SECRET_KEY"))
)
LANGFUSE_PROJECT_ID = os.getenv("LANGFUSE_PROJECT_ID")
LANGFUSE_BASE_URL = (
    os.getenv("LANGFUSE_BASE_URL")
    or os.getenv("LANGFUSE_HOST")
    or "https://cloud.langfuse.com"
)
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
EMBEDDING_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_BACKEND = (
    "offline:hashed-terms-v1" if OFFLINE_MODE else f"siliconflow:{EMBEDDING_MODEL}"
)
EMBEDDING_DIMENSIONS = 1024

EXTERNAL_MCP_URL = os.getenv("RESEARCH_EXTERNAL_MCP_URL")
EXTERNAL_MCP_TOOL = os.getenv("RESEARCH_EXTERNAL_MCP_TOOL")
PPT_MCP_URL = os.getenv("RESEARCH_PPT_MCP_URL")
PPT_OUTPUT_DIR = os.getenv("RESEARCH_PPT_OUTPUT_DIR", "/tmp/launchpad-research-decks")
UPLOAD_DIR = Path(
    os.getenv("RESEARCH_UPLOAD_DIR")
    or Path(__file__).resolve().parents[5] / "data" / "research-uploads"
).resolve()
API_URL = os.getenv("RESEARCH_API_URL", "http://127.0.0.1:8080")
