from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Section 5: governed canonical concepts -- operational MEANING, never a
# client column name. Modeled on this codebase's existing declarative
# registry convention (app/domain_registry.py, app/ground_truth_validation/
# family_registry.py, app/registries/rule_registry.py): data/configuration
# entries in one file, never scattered if/else branches through
# orchestration logic. Adding a new industry's vocabulary is an entry here,
# never a code change to app/semantic/*.py.
# ---------------------------------------------------------------------------


class CanonicalConceptType(StrEnum):
    IDENTIFIER = "identifier"
    TIMESTAMP = "timestamp"
    QUANTITY = "quantity"
    MONETARY_AMOUNT = "monetary_amount"
    CODE = "code"
    STATUS = "status"
    TEXT = "text"


@dataclass(frozen=True)
class CanonicalConcept:
    concept_code: str
    concept_type: str
    description: str
    aliases: frozenset[str]
    expected_value_patterns: frozenset[str] = frozenset()
    compatible_dataset_roles: frozenset[str] = frozenset()
    compatible_entity_types: frozenset[str] = frozenset()
    version: str = "1.0"
    active: bool = True


class CanonicalConceptRegistry:
    def __init__(self) -> None:
        self._concepts: dict[str, CanonicalConcept] = {}

    def register(self, concept: CanonicalConcept) -> None:
        self._concepts[concept.concept_code] = concept

    def get(self, concept_code: str) -> CanonicalConcept | None:
        return self._concepts.get(concept_code)

    def all(self) -> list[CanonicalConcept]:
        return list(self._concepts.values())

    def active(self) -> list[CanonicalConcept]:
        return [c for c in self._concepts.values() if c.active]

    def find_by_alias(self, source_name: str) -> list[CanonicalConcept]:
        """Every active concept whose alias set contains this normalized
        name -- may be more than one (genuine ambiguity is real evidence
        for the confidence engine, never silently resolved here)."""
        normalized = _normalize(source_name)
        return [
            c
            for c in self._concepts.values()
            if c.active and normalized in {_normalize(a) for a in c.aliases}
        ]

    def compatible_with_role(self, dataset_role: str) -> list[CanonicalConcept]:
        return [
            c
            for c in self._concepts.values()
            if c.active
            and (not c.compatible_dataset_roles or dataset_role in c.compatible_dataset_roles)
        ]


def _normalize(name: str) -> str:
    return "".join(ch for ch in name.strip().lower() if ch.isalnum() or ch == "_")


def build_default_canonical_concept_registry() -> CanonicalConceptRegistry:
    registry = CanonicalConceptRegistry()
    registry.register(
        CanonicalConcept(
            concept_code="asset_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of a physical or logical operational asset.",
            aliases=frozenset({"asset_id", "vehicle_id", "equipment_id", "unit_id", "machine_id"}),
            expected_value_patterns=frozenset({"alpha_dash_digits", "digits"}),
            compatible_dataset_roles=frozenset({"master", "reference", "event", "transaction"}),
            compatible_entity_types=frozenset({"ASSET"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="work_order_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of a unit of scheduled or performed work.",
            # P3.xxE.2 section 16: a few French/German equivalents included
            # directly as registry data (not a runtime language branch) --
            # proves the deterministic alias mechanism generalizes beyond
            # English without any code change; see tests/test_semantic_multilingual.py.
            aliases=frozenset(
                {
                    "work_order_id",
                    "order_id",
                    "job_id",
                    "ticket_id",
                    "wo_id",
                    "service_order_id",
                    "numero_commande",
                    "bestellnummer",
                }
            ),
            compatible_dataset_roles=frozenset({"work_order", "transaction", "event"}),
            compatible_entity_types=frozenset({"WORK_ORDER"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="customer_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of the customer/client party in a transaction.",
            aliases=frozenset(
                {
                    "customer_id",
                    "client_id",
                    "account_id",
                    "buyer_id",
                    "numero_client",
                    "kundennummer",
                }
            ),
            compatible_dataset_roles=frozenset({"master", "invoice", "contract"}),
            compatible_entity_types=frozenset({"CUSTOMER"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="invoice_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of a billing document.",
            aliases=frozenset({"invoice_id", "bill_id", "invoice_number"}),
            compatible_dataset_roles=frozenset({"invoice", "ledger"}),
            compatible_entity_types=frozenset({"INVOICE"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="technician_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of the person who performed the work.",
            aliases=frozenset({"technician_id", "employee_id", "worker_id", "engineer_id"}),
            compatible_dataset_roles=frozenset({"labor", "work_order"}),
            compatible_entity_types=frozenset({"PERSON"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="part_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of a physical part, item, or material.",
            aliases=frozenset({"part_id", "item_id", "sku", "material_id"}),
            compatible_dataset_roles=frozenset({"inventory", "work_order"}),
            compatible_entity_types=frozenset({"PART"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="event_timestamp",
            concept_type=CanonicalConceptType.TIMESTAMP.value,
            description="When an event or activity actually occurred.",
            aliases=frozenset(
                {"event_date", "date", "occurred_at", "event_timestamp", "timestamp"}
            ),
            expected_value_patterns=frozenset({"iso_date"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="scheduled_timestamp",
            concept_type=CanonicalConceptType.TIMESTAMP.value,
            description="When work or an event was planned/scheduled to occur.",
            aliases=frozenset({"scheduled_date", "scheduled_at", "planned_date", "due_date"}),
            expected_value_patterns=frozenset({"iso_date"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="completed_timestamp",
            concept_type=CanonicalConceptType.TIMESTAMP.value,
            description="When work or an event was actually completed.",
            aliases=frozenset({"completed_date", "completed_at", "closed_date", "finished_at"}),
            expected_value_patterns=frozenset({"iso_date"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="quantity",
            concept_type=CanonicalConceptType.QUANTITY.value,
            description="A counted or measured amount of something, not currency.",
            aliases=frozenset({"quantity", "qty", "count", "units"}),
            compatible_dataset_roles=frozenset({"inventory", "measurement"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="unit_price",
            concept_type=CanonicalConceptType.MONETARY_AMOUNT.value,
            description="Price per unit of a good or service, in a specific currency.",
            # P3.xxE.2 section 8: "amount" deliberately shared with
            # invoice_amount/cost_amount below -- a bare "amount" column is
            # genuinely ambiguous without more context, matching the
            # spec's own worked example. This is real, data-only ambiguity
            # (never resolved here), letting the ambiguity engine actually
            # exercise ACCEPTED_WITH_FLAG/REVIEW_REQUIRED on a tied score
            # rather than never seeing a multi-candidate field at all.
            aliases=frozenset({"unit_price", "price", "rate", "amount"}),
            compatible_dataset_roles=frozenset({"invoice", "inventory"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="invoice_amount",
            concept_type=CanonicalConceptType.MONETARY_AMOUNT.value,
            description="Total monetary amount billed on a document, in a specific currency.",
            aliases=frozenset(
                {"invoice_amount", "total_amount", "amount_due", "bill_amount", "amount"}
            ),
            compatible_dataset_roles=frozenset({"invoice", "ledger"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="cost_amount",
            concept_type=CanonicalConceptType.MONETARY_AMOUNT.value,
            description="Monetary cost incurred, in a specific currency.",
            aliases=frozenset({"cost_amount", "cost", "expense_amount", "amount"}),
            compatible_dataset_roles=frozenset({"invoice", "ledger", "work_order"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="currency_code",
            concept_type=CanonicalConceptType.CODE.value,
            description="ISO-style currency code governing an adjacent monetary amount.",
            aliases=frozenset({"currency", "currency_code", "ccy"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="status",
            concept_type=CanonicalConceptType.STATUS.value,
            description="Lifecycle state of the record's subject (order, asset, contract, ...).",
            aliases=frozenset({"status", "state", "lifecycle_status"}),
        )
    )
    return registry


default_canonical_concept_registry = build_default_canonical_concept_registry()
