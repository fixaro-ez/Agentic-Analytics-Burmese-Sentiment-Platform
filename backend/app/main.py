from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import close_pool
from .routers import analytics, brands, chat, entities, etl, mining, scraping
from .services.scraping import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    await stop_scheduler()
    await close_pool()


app = FastAPI(
    title="Burmese Sentiment Analytics API",
    description="API for the Agentic Analytics & Burmese Sentiment Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
app.include_router(brands.router, prefix="/api/brands", tags=["brands"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(etl.router, prefix="/api/etl", tags=["etl"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(mining.router, prefix="/api/mining", tags=["mining"])
app.include_router(scraping.router, prefix="/api/scraping", tags=["scraping"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "burmese-sentiment-api"}
