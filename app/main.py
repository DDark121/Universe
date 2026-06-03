from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.cache import get_redis_client
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    RequestContextMiddleware,
    register_exception_handlers,
)
from app.db.seed import seed_initial_data

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger.info("app_startup")
    await seed_initial_data()
    yield
    redis = get_redis_client()
    await redis.aclose()
    logger.info("app_shutdown")


app = FastAPI(title="Universe Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()],
    allow_origin_regex=(
        settings.cors_allow_origin_regex.strip()
        if settings.cors_allow_origin_regex and settings.cors_allow_origin_regex.strip()
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(api_router)
