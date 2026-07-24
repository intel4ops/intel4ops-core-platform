from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingestion_routes import router as ingestion_router
from app.api.membership_routes import router as membership_router
from app.api.routes import router
from app.api.source_system_routes import router as source_system_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(membership_router)
app.include_router(source_system_router)
app.include_router(ingestion_router)
