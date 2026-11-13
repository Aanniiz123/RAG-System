from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    DATABASE_URL : str = os.getenv("DATABASE_URL")
    QDRANT_URL  : str = os.getenv()
    QDRANT_COLLECTION   : str = os.getenv()
    EMBEDDING_MODEL : str = os.getenv()
    EMBEDDING_DEVICE    : str = os.getenv()

setting = Settings()