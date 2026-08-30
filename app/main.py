from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.access_routes import me_router
from app.api.access_routes import organization_router as access_organization_router
from app.api.action_routes import router as action_router
from app.api.ai_profile_routes import router as ai_profile_router
from app.api.analysis_case_routes import router as analysis_case_router
from app.api.canonical_mapping_routes import catalog_router as canonical_mapping_catalog_router
from app.api.canonical_mapping_routes import tenant_router as canonical_mapping_tenant_router
from app.api.causal_intelligence_routes import catalog_router as causal_intelligence_catalog_router
from app.api.causal_intelligence_routes import tenant_router as causal_intelligence_tenant_router
from app.api.command_routes import router as command_router
from app.api.commercial_routes import catalog_router as commercial_catalog_router
from app.api.commercial_routes import tenant_router as commercial_tenant_router
from app.api.decision_intelligence_routes import catalog_router as decision_catalog_router
from app.api.decision_intelligence_routes import tenant_router as decision_tenant_router
from app.api.decision_intelligence_routes import workspace_router as decision_workspace_router
from app.api.economics_routes import router as economics_router
from app.api.entities_routes import router as entities_router
from app.api.executive_narrative_routes import router as executive_narrative_router
from app.api.finding_routes import router as finding_router
from app.api.forecasting_routes import router as forecasting_router
from app.api.gateway_routes import router as gateway_router
from app.api.industry_pack_routes import catalog_router as industry_pack_catalog_router
from app.api.industry_pack_routes import tenant_router as industry_pack_tenant_router
from app.api.ingestion_routes import router as ingestion_router
from app.api.intelligence_routes import router as intelligence_router
from app.api.invitation_routes import accept_router as invitation_accept_router
from app.api.invitation_routes import router as invitation_router
from app.api.job_to_cash_routes import router as job_to_cash_router
from app.api.knowledge_graph_routes import catalog_router as knowledge_graph_catalog_router
from app.api.knowledge_graph_routes import tenant_router as knowledge_graph_tenant_router
from app.api.knowledge_pack_routes import router as knowledge_pack_router
from app.api.learning_routes import router as learning_router
from app.api.membership_routes import router as membership_router
from app.api.memory_effectiveness_routes import router as memory_effectiveness_router
from app.api.oikb_routes import router as oikb_router
from app.api.operational_memory_routes import router as operational_memory_router
from app.api.orchestration_routes import engine_router
from app.api.orchestration_routes import router as orchestration_router
from app.api.raw_lineage_routes import router as raw_lineage_router
from app.api.recovery_ledger_routes import router as recovery_ledger_router
from app.api.recovery_portfolio_routes import router as recovery_portfolio_router
from app.api.recovery_workspace_routes import router as recovery_workspace_router
from app.api.reliability_routes import router as reliability_router
from app.api.routes import router
from app.api.semantic_review_routes import router as semantic_review_router
from app.api.semantic_routes import router as semantic_router
from app.api.signature_routes import catalog_router as signature_catalog_router
from app.api.signature_routes import tenant_router as signature_tenant_router
from app.api.source_system_routes import router as source_system_router
from app.api.statistical_routes import router as statistical_router
from app.api.trust_routes import router as trust_router
from app.api.value_scan_routes import router as value_scan_router
from app.api.workspace_routes import catalog_router as workspace_catalog_router
from app.api.workspace_routes import tenant_router as workspace_tenant_router
from app.auth.request_context import RequestContextMiddleware
from app.core.config import get_settings
from app.ground_truth_validation.routes import router as validation_router

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        safe_error = {key: value for key, value in error.items() if key not in {"input", "ctx"}}
        errors.append(safe_error)
    if not _gateway_path(request):
        return JSONResponse(status_code=422, content={"detail": errors})
    transport = getattr(request.state, "gateway_transport_context", {})
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_INPUT",
                "message": "Request validation failed",
                "request_id": transport.get("request_id", "unavailable"),
                "details": {},
                "field_errors": [
                    {"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
                    for item in errors
                ],
            }
        },
    )


def _gateway_path(request: Request) -> bool:
    return any(
        segment in request.url.path for segment in ("/gateway/", "/command/", "/job-to-cash/")
    )


@app.exception_handler(HTTPException)
async def safe_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    if not _gateway_path(request):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    detail: dict[str, object] = exc.detail if isinstance(exc.detail, dict) else {}
    message = str(detail.get("message", exc.detail))
    code = str(detail.get("code", "REQUEST_FAILED"))
    transport = getattr(request.state, "gateway_transport_context", {})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": transport.get("request_id", "unavailable"),
                "details": {},
                "field_errors": [],
            }
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.include_router(router)
app.include_router(membership_router)
app.include_router(access_organization_router)
app.include_router(me_router)
app.include_router(invitation_router)
app.include_router(invitation_accept_router)
app.include_router(source_system_router)
app.include_router(ingestion_router)
app.include_router(raw_lineage_router)
app.include_router(trust_router)
app.include_router(intelligence_router)
app.include_router(finding_router)
app.include_router(orchestration_router)
app.include_router(engine_router)
app.include_router(oikb_router)
app.include_router(operational_memory_router)
app.include_router(statistical_router)
app.include_router(forecasting_router)
app.include_router(reliability_router)
app.include_router(action_router)
app.include_router(ai_profile_router)
app.include_router(canonical_mapping_catalog_router)
app.include_router(canonical_mapping_tenant_router)
app.include_router(memory_effectiveness_router)
app.include_router(economics_router)
app.include_router(recovery_ledger_router)
app.include_router(recovery_portfolio_router)
app.include_router(recovery_workspace_router)
app.include_router(commercial_catalog_router)
app.include_router(commercial_tenant_router)
app.include_router(industry_pack_catalog_router)
app.include_router(industry_pack_tenant_router)
app.include_router(command_router)
app.include_router(job_to_cash_router)
app.include_router(gateway_router)
app.include_router(signature_catalog_router)
app.include_router(signature_tenant_router)
app.include_router(knowledge_graph_catalog_router)
app.include_router(knowledge_graph_tenant_router)
app.include_router(learning_router)
app.include_router(knowledge_pack_router)
app.include_router(causal_intelligence_catalog_router)
app.include_router(causal_intelligence_tenant_router)
app.include_router(decision_catalog_router)
app.include_router(decision_tenant_router)
app.include_router(decision_workspace_router)
app.include_router(value_scan_router)
app.include_router(executive_narrative_router)
app.include_router(workspace_catalog_router)
app.include_router(workspace_tenant_router)
app.include_router(analysis_case_router)
app.include_router(validation_router)
app.include_router(semantic_router)
app.include_router(semantic_review_router)
app.include_router(entities_router)
