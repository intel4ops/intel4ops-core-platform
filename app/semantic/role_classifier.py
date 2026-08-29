from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.semantic.profiler import DatasetProfile

# ---------------------------------------------------------------------------
# Section 4: dataset ROLE classification (MASTER/TRANSACTION/EVENT/...),
# never an industry or business domain. Classification always considers
# the WHOLE dataset profile -- a single field (asset_id, amount, date)
# must never independently force a role. Every scored role carries its
# supporting evidence so the decision is explainable, never opaque.
# ---------------------------------------------------------------------------


class DatasetRole(StrEnum):
    MASTER = "master"
    TRANSACTION = "transaction"
    EVENT = "event"
    SNAPSHOT = "snapshot"
    LEDGER = "ledger"
    SCHEDULE = "schedule"
    WORK_ORDER = "work_order"
    INVOICE = "invoice"
    LABOR = "labor"
    INVENTORY = "inventory"
    MEASUREMENT = "measurement"
    REFERENCE = "reference"
    DOCUMENT = "document"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RoleScore:
    role: str
    confidence: float
    evidence: list[str]


@dataclass(frozen=True)
class DatasetRoleInterpretation:
    dataset_label: str
    primary_role: str
    confidence: float
    evidence: list[str]
    secondary_roles: list[str] = field(default_factory=list)
    alternative_roles: list[RoleScore] = field(default_factory=list)


def _lower_names(profile: DatasetProfile) -> set[str]:
    return {f.source_field.lower() for f in profile.fields}


def _score_roles(profile: DatasetProfile) -> list[RoleScore]:
    names = _lower_names(profile)
    scores: list[RoleScore] = []

    def field_matches(*substrings: str) -> list[str]:
        return sorted({n for n in names if any(s in n for s in substrings)})

    # WORK_ORDER: an order/ticket-like identifier + lifecycle/status +
    # temporal span + at least one entity reference -- combined evidence,
    # never one field alone (section 4 example is deliberately mirrored).
    order_id_hits = field_matches("work_order", "order_id", "ticket", "job_id", "wo_id")
    status_hits = field_matches("status", "state")
    span_hits = [f.source_field for f in profile.fields if f.is_date_like]
    entity_ref_hits = [
        f.source_field
        for f in profile.fields
        if f.source_field.lower().endswith("_id") and f.source_field not in order_id_hits
    ]
    if order_id_hits and status_hits and len(span_hits) >= 1:
        evidence = [
            f"order/ticket-like identifier: {order_id_hits}",
            f"lifecycle/status field(s): {status_hits}",
            f"temporal field(s): {span_hits[:3]}",
        ]
        confidence = 0.6 + 0.15 * min(len(entity_ref_hits), 2) + (0.1 if len(span_hits) >= 2 else 0)
        if entity_ref_hits:
            evidence.append(f"entity reference(s): {entity_ref_hits[:3]}")
        scores.append(RoleScore(DatasetRole.WORK_ORDER.value, min(confidence, 0.97), evidence))

    # INVOICE: currency-like/amount field + invoice-like identifier or
    # dataset-level ledger/transaction shape.
    invoice_id_hits = field_matches("invoice", "bill_id")
    amount_hits = [
        f.source_field for f in profile.fields if f.is_currency_like or f.detected_currency_codes
    ]
    if invoice_id_hits and amount_hits:
        scores.append(
            RoleScore(
                DatasetRole.INVOICE.value,
                0.85,
                [
                    f"invoice-like identifier: {invoice_id_hits}",
                    f"currency-like field(s): {amount_hits}",
                ],
            )
        )
    elif profile.is_ledger_like and amount_hits and field_matches("customer", "client", "bill"):
        scores.append(
            RoleScore(
                DatasetRole.INVOICE.value,
                0.55,
                [
                    "dataset has ledger-like shape (currency + identifiers + dates)",
                    f"currency-like field(s): {amount_hits}",
                    "billing-context field present",
                ],
            )
        )

    # LABOR: hours/time-entry field + person-like identifier.
    hours_hits = field_matches("hours", "hrs", "labor", "time_entry")
    person_hits = field_matches("technician", "employee", "worker", "person")
    if hours_hits and (person_hits or entity_ref_hits):
        scores.append(
            RoleScore(
                DatasetRole.LABOR.value,
                0.65 + (0.15 if person_hits else 0),
                [
                    f"hours/labor field(s): {hours_hits}",
                    f"person-like reference(s): {person_hits or entity_ref_hits[:2]}",
                ],
            )
        )

    # INVENTORY: quantity/stock field + part/item-like identifier.
    qty_hits = field_matches("quantity", "qty", "stock", "on_hand")
    part_hits = field_matches("part", "item", "sku", "material")
    if qty_hits and part_hits:
        scores.append(
            RoleScore(
                DatasetRole.INVENTORY.value,
                0.7,
                [
                    f"quantity-like field(s): {qty_hits}",
                    f"part/item-like identifier(s): {part_hits}",
                ],
            )
        )

    # SCHEDULE: dataset with a scheduled/planned temporal field + no
    # currency, no lifecycle-close status.
    scheduled_hits = field_matches("scheduled", "planned", "due")
    if scheduled_hits and not amount_hits:
        scores.append(
            RoleScore(
                DatasetRole.SCHEDULE.value,
                0.55,
                [f"scheduled/planned field(s): {scheduled_hits}"],
            )
        )

    # CONTRACT / DOCUMENT: identifier + no numeric measurement shape, low
    # row count, reference-like.
    contract_hits = field_matches("contract", "agreement")
    if contract_hits:
        scores.append(
            RoleScore(
                DatasetRole.CONTRACT.value, 0.6, [f"contract-like identifier: {contract_hits}"]
            )
        )

    # MEASUREMENT: dataset-level shape only (no single field forces this).
    if profile.is_measurement_like:
        numeric_fields = [f.source_field for f in profile.fields if f.is_numeric_like]
        scores.append(
            RoleScore(
                DatasetRole.MEASUREMENT.value,
                0.6,
                [
                    "multiple numeric fields alongside a temporal field, no currency-like field",
                    f"numeric field(s): {numeric_fields[:4]}",
                ],
            )
        )

    # LEDGER: dataset-level shape.
    if profile.is_ledger_like:
        scores.append(
            RoleScore(
                DatasetRole.LEDGER.value,
                0.55,
                ["dataset-level evidence: currency-like + identifier + temporal fields together"],
            )
        )

    # TRANSACTION: dataset-level shape (weaker/more generic than the
    # above specializations, so scored lower -- specializations should
    # usually win when present).
    if profile.is_transaction_like:
        scores.append(
            RoleScore(
                DatasetRole.TRANSACTION.value,
                0.5,
                ["dataset-level evidence: currency-like + identifier + temporal fields together"],
            )
        )

    # EVENT: append/event-like dataset shape.
    if profile.is_append_or_event_like and not scores:
        scores.append(
            RoleScore(
                DatasetRole.EVENT.value,
                0.45,
                [
                    "high-cardinality identifier(s) with temporal field(s), "
                    "not a small reference table"
                ],
            )
        )

    # SNAPSHOT: dataset-level shape.
    if profile.is_snapshot_like:
        scores.append(
            RoleScore(
                DatasetRole.SNAPSHOT.value,
                0.45,
                ["multiple temporal fields plus a status/state field, not a transaction shape"],
            )
        )

    # MASTER / REFERENCE: small, key-defined, no temporal fields at all --
    # dataset-level shape, deliberately the last, weakest-evidence
    # fallback family so specializations above win when present.
    if profile.is_master_or_reference_like:
        label = (
            DatasetRole.MASTER.value
            if profile.candidate_primary_keys
            else DatasetRole.REFERENCE.value
        )
        scores.append(
            RoleScore(
                label,
                0.5 if profile.candidate_primary_keys else 0.4,
                ["small, key-defined dataset with no temporal fields"],
            )
        )

    return scores


class DatasetRoleClassifier:
    def classify(self, profile: DatasetProfile) -> DatasetRoleInterpretation:
        scores = sorted(_score_roles(profile), key=lambda s: s.confidence, reverse=True)
        if not scores:
            return DatasetRoleInterpretation(
                dataset_label=profile.dataset_label,
                primary_role=DatasetRole.UNKNOWN.value,
                confidence=0.0,
                evidence=["no whole-dataset role evidence combination matched"],
                secondary_roles=[],
                alternative_roles=[],
            )
        best = scores[0]
        secondary = [s.role for s in scores[1:3] if s.confidence >= 0.4]
        return DatasetRoleInterpretation(
            dataset_label=profile.dataset_label,
            primary_role=best.role,
            confidence=best.confidence,
            evidence=best.evidence,
            secondary_roles=secondary,
            alternative_roles=scores[1:],
        )


dataset_role_classifier = DatasetRoleClassifier()
