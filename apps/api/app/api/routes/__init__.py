from app.api.routes.ai import router as ai_router
from app.api.routes.ask import router as ask_router
from app.api.routes.documents import router as documents_router
from app.api.routes.search import router as search_router

__all__ = [
    "ai_router",
    "ask_router",
    "conversations_router",
    "documents_router",
    "search_router",
]
from app.api.routes.conversations import router as conversations_router
