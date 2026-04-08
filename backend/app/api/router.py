from fastapi import APIRouter
from app.api.endpoints import auth, reports, ai, metrics, emergency, medications, users, agents

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(emergency.router, prefix="/emergency", tags=["emergency"])
api_router.include_router(medications.router, prefix="/medications", tags=["medications"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
