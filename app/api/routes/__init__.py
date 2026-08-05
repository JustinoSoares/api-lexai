"""Rotas da API."""

from fastapi import APIRouter

from app.api.routes import chat, history

api_router = APIRouter()
api_router.include_router(chat.router)
api_router.include_router(history.router)