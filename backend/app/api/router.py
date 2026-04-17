from fastapi import APIRouter

from app.api.routes.fetches import router as fetches_router
from app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(fetches_router)
