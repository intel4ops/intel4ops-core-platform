"""P3.xxI.2A Section 15: generic sibling-concept corroboration. Distinct
from test_semantic_neighbor_context.py -- that mechanism corroborates via
ROLE overlap (too coarse to separate unit_price/invoice_amount/cost_amount,
which share nearly identical compatible_dataset_roles by design). This
module's mechanism checks each concept's own declared EXACT
requires_sibling_concepts/excludes_sibling_concepts.

Two test groups:
  1. Direct unit tests against generate_sibling_concept_corroboration_evidence()
     -- no DB needed, mirrors test_semantic_neighbor_context.py's own shape.
  2. End-to-end tests through generate_candidates() + reconcile() -- proves
     the full pipeline (alias + datatype + role + sibling evidence, summed
     and thresholded) actually reaches AUTO_ACCEPTED / stays ambiguous, not
     just that the isolated evidence component exists.
"""

from app.semantic.candidate_generator import generate_candidates
from app.semantic.concept_registry import default_canonical_concept_registry
from app.semantic.confidence_engine import reconcile
from app.semantic.neighbor_context import generate_neighbor_context_evidence
from app.semantic.profiler import DatasetProfile, FieldProfile
from app.semantic.role_classifier import DatasetRoleInterpretation
from app.semantic.sibling_concept_corroboration import (
    generate_sibling_concept_corroboration_evidence,
)

_NUMERIC_FIELD_NAMES = {"amount", "quantity", "unit_price", "cost", "total_amount"}


def _field(name: str) -> FieldProfile:
    # Real "amount"/"quantity"-shaped columns are numeric in production
    # data (confirmed live -- DATATYPE_COMPATIBILITY applies there); this
    # helper reflects that instead of defaulting every field to
    # non-numeric, which would silently understate every monetary
    # concept's real-world baseline score.
    numeric = name in _NUMERIC_FIELD_NAMES
    return FieldProfile(
        source_field=name,
        physical_type="float64" if numeric else "object",
        null_count=0,
        row_count=10,
        null_rate=0.0,
        distinct_count=10,
        uniqueness_ratio=1.0,
        is_numeric_like=numeric,
    )


def _dataset(fields: list[str]) -> DatasetProfile:
    field_profiles = [_field(f) for f in fields]
    return DatasetProfile(
        dataset_label="ds.csv",
        row_count=10,
        column_count=len(fields),
        fields=field_profiles,
        candidate_grain=[],
        candidate_primary_keys=[],
        candidate_foreign_keys=[],
        is_append_or_event_like=False,
        is_snapshot_like=False,
        is_master_or_reference_like=False,
        is_transaction_like=False,
        is_ledger_like=False,
        is_measurement_like=False,
    )


def _role(primary: str) -> DatasetRoleInterpretation:
    return DatasetRoleInterpretation(
        dataset_label="ds.csv",
        primary_role=primary,
        confidence=0.9,
        evidence=[],
        secondary_roles=[],
        alternative_roles=[],
    )


# ---------------------------------------------------------------------------
# Group 1: isolated evidence-component unit tests
# ---------------------------------------------------------------------------


def test_a_invoice_shaped_siblings_corroborate_invoice_amount() -> None:
    dataset = _dataset(["invoice_id", "work_order_id", "status", "amount"])
    field = dataset.fields[3]  # amount
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"unit_price", "invoice_amount", "cost_amount"},
        default_canonical_concept_registry,
    )
    concepts = {c.candidate_concept for c in candidates}
    assert concepts == {"invoice_amount"}
    assert candidates[0].evidence_components[0].component_type == "sibling_concept_corroboration"


def test_b_quantity_sibling_corroborates_unit_price() -> None:
    dataset = _dataset(["work_order_id", "quantity", "unit_price"])
    field = dataset.fields[2]  # unit_price
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"unit_price", "invoice_amount", "cost_amount"},
        default_canonical_concept_registry,
    )
    concepts = {c.candidate_concept for c in candidates}
    assert concepts == {"unit_price"}


def test_c_amount_alone_no_siblings_no_corroboration_for_any_candidate() -> None:
    dataset = _dataset(["amount"])
    field = dataset.fields[0]
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"unit_price", "invoice_amount", "cost_amount"},
        default_canonical_concept_registry,
    )
    assert candidates == []


def test_d_cost_shaped_context_favors_cost_amount_not_invoice_amount() -> None:
    dataset = _dataset(["work_order_id", "cost"])
    field = dataset.fields[1]  # cost
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"unit_price", "invoice_amount", "cost_amount"},
        default_canonical_concept_registry,
    )
    concepts = {c.candidate_concept for c in candidates}
    assert concepts == {"cost_amount"}


def test_cost_amount_withheld_when_invoice_id_also_present() -> None:
    """cost_amount's excludes_sibling_concepts={"invoice_id", "quantity"} --
    a genuine billing document (invoice_id present) never gets misread as
    an internal cost reference merely because a work_order_id also links
    it."""
    dataset = _dataset(["work_order_id", "invoice_id", "cost"])
    field = dataset.fields[2]
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"unit_price", "invoice_amount", "cost_amount"},
        default_canonical_concept_registry,
    )
    assert candidates == []


def test_e_invoice_shaped_evidence_ignores_dataset_role_entirely() -> None:
    """Section 8: this module never reads DatasetRoleInterpretation at all
    -- the isolated function call above already proves sibling-column
    evidence works independent of role classification; this test makes
    that independence explicit by never constructing a role at all."""
    dataset = _dataset(["invoice_id", "work_order_id", "status", "amount"])
    field = dataset.fields[3]
    # No role argument exists on this function's signature -- sibling
    # corroboration is structurally incapable of depending on dataset role.
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"invoice_amount"},
        default_canonical_concept_registry,
    )
    assert len(candidates) == 1
    assert candidates[0].candidate_concept == "invoice_amount"


def test_f_conflicting_evidence_quantity_presence_rules_out_invoice_amount() -> None:
    """A field with BOTH a status sibling (invoice-shaped) AND a quantity
    sibling (rate-shaped) is genuinely conflicting evidence for
    invoice_amount specifically: invoice_amount's own
    excludes_sibling_concepts={"quantity"} means the co-located quantity
    rules it out even though status alone would have satisfied its
    requirement -- a same-row rate interpretation (unit_price) always
    takes precedence over a billed-total interpretation when both signals
    are present, never left as a coin-flip between the two."""
    dataset = _dataset(["work_order_id", "status", "quantity", "amount"])
    field = dataset.fields[3]
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1",
        dataset,
        field,
        {"unit_price", "invoice_amount", "cost_amount"},
        default_canonical_concept_registry,
    )
    concepts = {c.candidate_concept for c in candidates}
    assert concepts == {"unit_price"}


def test_no_candidate_concepts_produces_no_sibling_evidence() -> None:
    dataset = _dataset(["invoice_id", "status", "amount"])
    field = dataset.fields[2]
    assert (
        generate_sibling_concept_corroboration_evidence(
            "ds-1", dataset, field, set(), default_canonical_concept_registry
        )
        == []
    )


def test_sibling_evidence_excludes_the_field_itself() -> None:
    dataset = _dataset(["amount"])
    field = dataset.fields[0]
    candidates = generate_sibling_concept_corroboration_evidence(
        "ds-1", dataset, field, {"invoice_amount"}, default_canonical_concept_registry
    )
    assert candidates == []


# ---------------------------------------------------------------------------
# Group 2: end-to-end through generate_candidates() + reconcile()
# ---------------------------------------------------------------------------


def test_invoice_shaped_amount_reaches_auto_accepted_as_invoice_amount() -> None:
    dataset = _dataset(["invoice_id", "work_order_id", "invoice_date", "status", "amount"])
    role = _role("work_order")  # the exact live-observed misclassification
    field = next(f for f in dataset.fields if f.source_field == "amount")
    candidates = generate_candidates(
        "ds-1", dataset, role, field, default_canonical_concept_registry
    )
    concept_codes = {c.candidate_concept for c in candidates}
    neighbor = generate_neighbor_context_evidence(
        "ds-1", dataset, field, concept_codes, default_canonical_concept_registry
    )
    sibling = generate_sibling_concept_corroboration_evidence(
        "ds-1", dataset, field, concept_codes, default_canonical_concept_registry
    )
    decision = reconcile("ds-1", "amount", candidates + neighbor + sibling)
    assert decision.selected_concept == "invoice_amount"
    assert decision.status == "auto_accepted"


def test_rate_shaped_amount_reaches_auto_accepted_as_unit_price() -> None:
    dataset = _dataset(["work_order_id", "quantity", "amount"])
    role = _role("inventory")
    field = next(f for f in dataset.fields if f.source_field == "amount")
    candidates = generate_candidates(
        "ds-1", dataset, role, field, default_canonical_concept_registry
    )
    concept_codes = {c.candidate_concept for c in candidates}
    sibling = generate_sibling_concept_corroboration_evidence(
        "ds-1", dataset, field, concept_codes, default_canonical_concept_registry
    )
    decision = reconcile("ds-1", "amount", candidates + sibling)
    assert decision.selected_concept == "unit_price"
    assert decision.status == "auto_accepted"


def test_bare_amount_alone_remains_ambiguous_not_auto_accepted() -> None:
    """The key false-positive guard (Section 10): a lone 'amount' column
    with no siblings at all must never be overconfidently auto-accepted as
    any single concept."""
    dataset = _dataset(["amount"])
    role = _role("unknown")
    field = dataset.fields[0]
    candidates = generate_candidates(
        "ds-1", dataset, role, field, default_canonical_concept_registry
    )
    decision = reconcile("ds-1", "amount", candidates)
    assert decision.status != "auto_accepted"
