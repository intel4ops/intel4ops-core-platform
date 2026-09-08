from io import BytesIO
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import INTELLIGENCE_EXECUTION_ROLES
from app.engines.trust_engine import TrustEngine
from app.services.customer_native_semantics_service import analyze_customer_native_datasets


router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    tags=["customer-native-routing"],
    dependencies=[
        Depends(
            require_commercial_entitlement(
                "intelligence.arithmetic", *INTELLIGENCE_EXECUTION_ROLES
            )
        )
    ],
)

trust_engine = TrustEngine()


async def _read_tabular(file: UploadFile) -> pd.DataFrame:
    content = await file.read()
    name = file.filename or "upload"
    if name.lower().endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(content))
    raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")


@router.post("/customer-native/semantic-routing")
async def semantic_route_customer_files(
    organization_id: UUID,
    files: list[UploadFile] = File(...),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_EXECUTION_ROLES)),
) -> dict[str, object]:
    """Interpret customer-native tabular files and identify eligible existing capabilities.

    This is a normal product-side advisory route. It accepts only customer
    files, performs Trust profiling, infers general operational semantics,
    identifies evidence-backed cross-dataset identifier relationships, and
    evaluates those inferred canonical concepts against the existing
    intelligence capability registry. It has no simulation or hidden-truth
    dependency and does not synthesize missing customer fields.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one customer file is required")

    datasets: list[tuple[str, pd.DataFrame]] = []
    trust: list[dict[str, object]] = []
    for file in files:
        name = file.filename or "upload"
        frame = await _read_tabular(file)
        datasets.append((name, frame))
        trust.append(trust_engine.profile(frame, name).model_dump(mode="json"))

    result = analyze_customer_native_datasets(datasets)
    result["organization_id"] = str(organization_id)
    result["trust"] = trust
    result["routing_mode"] = "ADVISORY_EXISTING_CAPABILITY_REGISTRY"
    result["customer_fields_synthesized"] = False
    return result
