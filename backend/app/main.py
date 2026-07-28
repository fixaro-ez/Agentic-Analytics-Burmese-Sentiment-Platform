from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import close_pool
from .routers import alerts, analytics, chat, entities, etl, mining, scraping


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
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

app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(etl.router, prefix="/api/etl", tags=["etl"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(mining.router, prefix="/api/mining", tags=["mining"])
app.include_router(scraping.router, prefix="/api/scraping", tags=["scraping"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "burmese-sentiment-api"}
