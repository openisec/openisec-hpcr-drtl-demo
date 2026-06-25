from fastapi import APIRouter
from app.api.v1.endpoints import auth, sessions, messages

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(messages.router)
