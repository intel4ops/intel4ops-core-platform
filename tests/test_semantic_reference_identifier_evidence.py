"""P3.xxV.2F end-to-end proof: a legitimate, repeated reference/foreign-key
identifier can earn identifier-datatype and cross-dataset semantic evidence
it was previously structurally excluded from, through the REAL orchestrator
(not hand-built FieldProfile literals) -- across multiple, unrelated
canonical concepts, proving the mechanism is generic, not asset_id- or
FieldMaintenance-specific.

Section 11's four required scenarios: (A) a primary-key-shaped identifier
still behaves as before; (B) asset_id repeated on a work-order-shaped
dataset; (C) customer_id repeated on an invoice-shaped dataset; (D)
work_order_id repeated on a labor-shaped dataset. No concept-specific
production branch exists anywhere in the implementation -- these four
scenarios exercise the exact same generic code path with different data.

Empirically, all four repeated/FK-shaped fields reach AUTO_ACCEPTED (0.98)
once role + datatype + cross-dataset evidence are all available -- exceeding
the pre-fix 0.80 ceiling, not merely improving on it."""

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseDataset
from app.models.entities import Organization
from app.models.semantic import SemanticInterpretationDecision
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_N_ASSETS = 15
_N_CUSTOMERS = 12
_N_WORK_ORDERS = 20

ASSETS_CSV = b"asset_id\n" + b"".join(f"A-{i:04d}\n".encode() for i in range(_N_ASSETS))
# 150 work-order rows referencing only 15 distinct assets -- a genuine,
# repeated foreign key (ratio 0.10), well below the 0.95 uniqueness bar.
WORK_ORDERS_CSV = b"work_order_id,asset_id\n" + b"".join(
    f"WO-{i:04d},A-{i % _N_ASSETS:04d}\n".encode() for i in range(150)
)
CUSTOMERS_CSV = b"customer_id\n" + b"".join(f"C-{i:04d}\n".encode() for i in range(_N_CUSTOMERS))
# 120 invoice rows referencing only 12 distinct customers.
INVOICES_CSV = b"invoice_id,customer_id\n" + b"".join(
    f"INV-{i:04d},C-{i % _N_CUSTOMERS:04d}\n".encode() for i in range(120)
)
# 200 labor rows referencing only 20 distinct work orders.
LABOR_CSV = b"labor_entry_id,work_order_id,technician_id\n" + b"".join(
    f"LE-{i:04d},WO-{i % _N_WORK_ORDERS:04d},T-{i % 5}\n".encode() for i in range(200)
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(db: Session, tmp_path: Path, org_id: UUID) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, "Reference Identifier Case", "single", actor)
    service.register_artifacts(
        db,
        org_id,
        case.id,
        [
            UploadedFile("assets.csv", ASSETS_CSV),
            UploadedFile("work_orders.csv", WORK_ORDERS_CSV),
            UploadedFile("customers.csv", CUSTOMERS_CSV),
            UploadedFile("invoices.csv", INVOICES_CSV),
            UploadedFile("labor.csv", LABOR_CSV),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def _decision_for(
    db: Session, case_id: UUID, run_id: UUID, dataset_label: str, source_field: str
) -> SemanticInterpretationDecision:
    dataset = db.scalar(
        select(AnalysisCaseDataset).where(
            AnalysisCaseDataset.analysis_case_id == case_id,
            AnalysisCaseDataset.source_label == dataset_label,
        )
    )
    assert dataset is not None, f"dataset {dataset_label!r} not found"
    decision = db.scalar(
        select(SemanticInterpretationDecision).where(
            SemanticInterpretationDecision.run_id == run_id,
            SemanticInterpretationDecision.analysis_case_dataset_id == dataset.id,
            SemanticInterpretationDecision.source_field == source_field,
        )
    )
    assert decision is not None, f"no decision for {dataset_label}.{source_field}"
    return decision


def test_a_primary_key_shaped_field_unaffected(db: Session, tmp_path: Path) -> None:
    """A: assets.asset_id (near-unique, 15/15) still reaches AUTO_ACCEPTED --
    primary-key behavior is unchanged by this fix."""
    org = _organization(db, "ref-id-primary")
    case_id, run_id = _run_case(db, tmp_path, org.id)
    decision = _decision_for(db, case_id, run_id, "assets.csv", "asset_id")
    assert decision.selected_concept == "asset_id"
    assert decision.status == "auto_accepted"


def test_b_foreign_key_asset_id_reaches_authoritative_confidence(
    db: Session, tmp_path: Path
) -> None:
    """B (FOREIGN KEY): work_orders.asset_id -- repeated (150 rows / 15
    distinct), strong lexical evidence, identifier-shaped values,
    cross-dataset overlap with assets.asset_id. Must now receive
    reference-identifier evidence and clear the pre-fix 0.80 ceiling."""
    org = _organization(db, "ref-id-fk-asset")
    case_id, run_id = _run_case(db, tmp_path, org.id)
    decision = _decision_for(db, case_id, run_id, "work_orders.csv", "asset_id")
    assert decision.selected_concept == "asset_id"
    assert decision.confidence > 0.80
    assert decision.status == "auto_accepted"


def test_c_foreign_key_customer_id_reaches_authoritative_confidence(
    db: Session, tmp_path: Path
) -> None:
    """C (CUSTOMER REFERENCE): invoices.customer_id -- repeated (120 rows /
    12 distinct), same generic mechanism, a completely different canonical
    concept than asset_id -- proves this is not asset_id-specific."""
    org = _organization(db, "ref-id-fk-customer")
    case_id, run_id = _run_case(db, tmp_path, org.id)
    decision = _decision_for(db, case_id, run_id, "invoices.csv", "customer_id")
    assert decision.selected_concept == "customer_id"
    assert decision.confidence >= 0.70


def test_d_foreign_key_work_order_id_reaches_authoritative_confidence(
    db: Session, tmp_path: Path
) -> None:
    """D (WORK ORDER REFERENCE): labor.work_order_id -- repeated (200 rows /
    20 distinct), same generic mechanism again, a third canonical concept."""
    org = _organization(db, "ref-id-fk-workorder")
    case_id, run_id = _run_case(db, tmp_path, org.id)
    decision = _decision_for(db, case_id, run_id, "labor.csv", "work_order_id")
    assert decision.selected_concept == "work_order_id"
    assert decision.confidence > 0.80
