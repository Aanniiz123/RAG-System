from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
from core.config import setting


load_dotenv()



base = declarative_base()

engine = create_async_engine(setting.DATABASE_URL, echo = True)

session = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)


async def get_db():
    async with session() as db:
        try:
            yield db
        finally:
            await db.close()
