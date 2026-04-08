from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.router import api_router
from app.scheduler.jobs import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the background APScheduler loop concurrently on HTTP startup
    start_scheduler()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-grade Action-based AI Healthcare Assistant Backend",
    lifespan=lifespan
)

# CORS setup for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

# ── Real-time WebSocket routes (no /api/v1 prefix — direct WS path) ──
from app.realtime.websocket import router as ws_router
app.include_router(ws_router)

@app.get("/")
async def root():
    return {"message": "Welcome to CareAI Action-Agent API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
