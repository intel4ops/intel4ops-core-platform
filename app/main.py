from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ingestion_routes import router as ingestion_router
from app.api.intelligence_routes import router as intelligence_router
from app.api.membership_routes import router as membership_router
from app.api.raw_lineage_routes import router as raw_lineage_router
from app.api.routes import router
from app.api.source_system_routes import router as source_system_router
from app.api.trust_routes import router as trust_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        safe_error = {key: value for key, value in error.items() if key not in {"input", "ctx"}}
        errors.append(safe_error)
    return JSONResponse(status_code=422, content={"detail": errors})


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
app.include_router(raw_lineage_router)
app.include_router(trust_router)
app.include_router(intelligence_router)
