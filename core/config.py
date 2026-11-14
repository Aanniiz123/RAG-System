from dotenv import load_dotenv
import os

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set in the environment")
    return value


class Settings:
    DATABASE_URL: str = _required_env("DATABASE_URL")
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "documents")
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    GROQ_API_KEY: str = _required_env("GROQ_API_KEY")
    GROQ_MODEL: str = _required_env("GROQ_MODEL")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    BUSINESS_TIMEZONE : str | None = None

setting = Settings()
