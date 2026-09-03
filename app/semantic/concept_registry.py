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
    # P3.xxI.2A: sibling-concept corroboration (app/semantic/
    # sibling_concept_corroboration.py) -- generic, concept-declared,
    # exact-match evidence distinguishing concepts that otherwise share
    # aliases/roles too closely for DATASET_ROLE_COMPATIBILITY or
    # NEIGHBOR_FIELD_CONTEXT to ever separate. requires_sibling_concepts:
    # ALL must be present among OTHER fields' alias matches on the SAME
    # dataset for this concept to receive the corroboration bonus.
    # excludes_sibling_concepts: if ANY is present among siblings, the
    # bonus is withheld even when requires_sibling_concepts is satisfied.
    # Empty (the default) means this concept never participates -- most
    # concepts have no ambiguous sibling to disambiguate from and don't
    # need this.
    requires_sibling_concepts: frozenset[str] = frozenset()
    excludes_sibling_concepts: frozenset[str] = frozenset()
    # Alternative exact sibling contexts. Each inner set is independently
    # sufficient; this lets one concept have more than one legitimate shape
    # (for example, a unit price beside quantity OR a governed rate beside a
    # contract reference) without weakening the confidence threshold.
    alternative_sibling_concept_sets: tuple[frozenset[str], ...] = ()
    # P3.xxI.2B live-certification fix: per-alternative exclusions, parallel
    # to alternative_sibling_concept_sets (same length when non-empty; empty
    # means no per-alternative exclusion applies, preserving every existing
    # concept's behavior unchanged). The single global excludes_sibling_concepts
    # above is concept-wide and therefore too coarse once a concept has
    # several alternatives with genuinely different exclusion needs -- e.g.
    # unit_price's "quantity" alternative (Form A, same-row rate) must never
    # be excluded by a co-located status field, while its "contract_id"
    # alternative (a rate-card row) legitimately must be, since a real
    # billing document (invoices.csv) also carries contract_id.
    alternative_exclude_sibling_concept_sets: tuple[frozenset[str], ...] = ()


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
            # P3.xxV.2F: work_order and contract added -- a physical/
            # logical asset is generically the subject of a work order
            # (maintenance/service performed ON it) and can generically be
            # the subject of a contract (a lease/service agreement FOR a
            # specific asset), not just appear in master/reference/event/
            # transaction-shaped datasets. Not blindly extended to every
            # DatasetRole value -- only the two with direct evidence.
            compatible_dataset_roles=frozenset(
                {"master", "reference", "event", "transaction", "work_order", "contract"}
            ),
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
            # P3.xxV.2F: labor and invoice added -- a unit of work is
            # generically the subject a labor/time record was logged
            # against, and generically the subject an invoice bills for.
            # P3.xxI.2: inventory added -- a parts/materials consumption
            # record (quantity + part identifier) linked to a work order
            # is generically inventory-shaped by role_classifier.py's own
            # own scoring (quantity+part-like identifier both present),
            # even though work_order_id is the column that actually links
            # it back to the work it was consumed against.
            compatible_dataset_roles=frozenset(
                {"work_order", "transaction", "event", "labor", "invoice", "inventory"}
            ),
            compatible_entity_types=frozenset({"WORK_ORDER"}),
            alternative_sibling_concept_sets=(frozenset({"contract_id"}),),
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
            concept_code="contract_id",
            concept_type=CanonicalConceptType.IDENTIFIER.value,
            description="Identifier of the commercial agreement governing a transaction.",
            aliases=frozenset({"contract_id", "agreement_id", "rate_card_id"}),
            compatible_dataset_roles=frozenset(
                {"contract", "work_order", "invoice", "transaction", "reference"}
            ),
            alternative_sibling_concept_sets=(
                frozenset({"work_order_id"}),
                frozenset({"hourly_rate"}),
                frozenset({"unit_price"}),
            ),
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
            # P3.xxV.2I: maintenance_date/dispatch_date added -- both are
            # real, evidenced raw column names in this corpus's own CSVs
            # (Rental's maintenance.csv/dispatch.csv) that carry exactly
            # this meaning (when a maintenance event / dispatch activity
            # actually occurred), just spelled with an industry-specific
            # noun instead of the generic "event"/"date". Not a blind
            # <noun>_date pattern match -- each addition is a specific,
            # observed alias, mirroring the P3.xxV.2F asset_id precedent.
            #
            # Deliberately NOT given compatible_dataset_roles (left at the
            # class default, empty): tried during implementation, then
            # reverted -- app/semantic/neighbor_context.py's
            # NEIGHBOR_FIELD_CONTEXT corroboration is symmetric and keys
            # off ANY role overlap between two DIFFERENT concepts, so
            # giving this concept role compatibility also retroactively
            # corroborated co-occurring IDENTIFIER concepts (asset_id's
            # own roles overlap heavily with any role set broad enough to
            # cover real corpus datasets), pushing an unrelated asset_id
            # decision from accepted_with_flag to auto_accepted in one
            # existing regression fixture
            # (tests/test_capability_governed_activation.py) -- a genuine,
            # confirmed, out-of-scope side effect on entity confidence.
            # Reverted; the alias additions above, combined with the
            # existing, unmodified CROSS_DATASET_OVERLAP mechanism's
            # pattern-class evidence (app/semantic/cross_dataset_context.py,
            # requires no role compatibility), already reach auto_accepted
            # on real corpus-shaped data -- confirmed live, see the Fix #6
            # report, Section D.
            aliases=frozenset(
                {
                    "event_date",
                    "date",
                    "occurred_at",
                    "event_timestamp",
                    "timestamp",
                    "maintenance_date",
                    "dispatch_date",
                    "entry_date",
                }
            ),
            expected_value_patterns=frozenset({"iso_date"}),
            alternative_sibling_concept_sets=(
                frozenset({"work_order_id"}),
                frozenset({"contract_id"}),
            ),
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
            concept_code="effective_from_timestamp",
            concept_type=CanonicalConceptType.TIMESTAMP.value,
            description="Start of a reference record's governed applicability interval.",
            aliases=frozenset({"effective_from", "valid_from", "start_date"}),
            expected_value_patterns=frozenset({"iso_date"}),
            requires_sibling_concepts=frozenset({"contract_id"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="effective_to_timestamp",
            concept_type=CanonicalConceptType.TIMESTAMP.value,
            description="End of a reference record's governed applicability interval.",
            aliases=frozenset({"effective_to", "valid_to", "end_date"}),
            expected_value_patterns=frozenset({"iso_date"}),
            requires_sibling_concepts=frozenset({"contract_id"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="unit_of_measure",
            concept_type=CanonicalConceptType.CODE.value,
            description="Unit governing a quantity or per-unit rate.",
            aliases=frozenset({"unit_of_measure", "uom", "unit", "rate_basis"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="quantity",
            concept_type=CanonicalConceptType.QUANTITY.value,
            description="A counted or measured amount of something, not currency.",
            # Generic count/quantity spellings only. P3.xxI.2B models
            # explicitly hourly duration separately so its unit meaning is
            # preserved across a dataset boundary.
            aliases=frozenset({"quantity", "qty", "count", "units"}),
            # P3.xxI.2: work_order/labor added -- a consumption record
            # (parts used, hours logged) linked to a work order is
            # generically quantity-bearing, not just literal inventory/
            # measurement-shaped datasets.
            compatible_dataset_roles=frozenset({"inventory", "measurement", "work_order", "labor"}),
            # P3.xxI.2: a counted/measured quantity is always numeric --
            # plain integer counts ("digits") or a fractional measure
            # ("decimal"), never free text. Every other IDENTIFIER concept
            # in this registry already declares its own expected shape
            # (asset_id: alpha_dash_digits/digits); quantity previously
            # declared none at all.
            expected_value_patterns=frozenset({"digits", "decimal"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="duration_hours",
            concept_type=CanonicalConceptType.QUANTITY.value,
            description="A measured duration explicitly expressed in hours.",
            aliases=frozenset({"hours", "hrs", "hours_reported", "labor_hours"}),
            compatible_dataset_roles=frozenset({"labor", "work_order", "measurement"}),
            expected_value_patterns=frozenset({"digits", "decimal"}),
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
            # Explicit hourly-rate spellings are modeled separately by
            # P3.xxI.2B so the unit basis survives cross-dataset lookup.
            aliases=frozenset({"unit_price", "price", "rate", "amount"}),
            # P3.xxI.2: labor/contract added -- a rate quoted on a service
            # contract or applied on a labor-time record is generically a
            # unit price, not just an invoice/inventory line.
            # P3.xxI.2A: "work_order" deliberately REMOVED (was added in
            # P3.xxI.2). Confirmed live (docs/p3xxi2a-governed-actual-
            # billing-evidence-remediation.md Section D) that this blanket
            # role grant made unit_price score identically to cost_amount
            # on any work-order-linked dataset, including genuine
            # invoice-shaped ones -- exactly the ambiguity this concept's
            # own ANY-role NEIGHBOR_FIELD_CONTEXT can't break (that
            # component corroborates via role overlap, which is symmetric
            # across all three monetary concepts here by design). The
            # PRECISE signal for "this is a per-unit rate, not a billed
            # total" is requires_sibling_concepts below (a co-located
            # quantity), not a blanket role grant.
            compatible_dataset_roles=frozenset({"invoice", "inventory", "labor", "contract"}),
            # P3.xxI.2A: the decisive, concept-specific signal Form A
            # (quantity x unit_price) actually needs -- a rate is only
            # legible as a RATE when a quantity to multiply it by is
            # co-located on the same dataset.
            requires_sibling_concepts=frozenset({"quantity"}),
            alternative_sibling_concept_sets=(
                frozenset({"quantity"}),
                frozenset({"contract_id"}),
            ),
            # P3.xxI.2B live-certification fix: the "contract_id" alternative
            # above (added for genuine rate-card datasets, e.g.
            # service_contracts.csv keyed by contract_id) also matched real
            # Wave 1 invoices.csv, which carries its OWN contract_id column
            # alongside status -- silently re-tying unit_price against
            # invoice_amount and regressing invoice_amount back to
            # accepted_with_flag (confirmed live: FIELDMAINT-001 dropped
            # from the P3.xxI.2A-certified 6 findings to 0). A genuine
            # rate-card row never carries a document lifecycle field; that
            # combination is invoices.csv's own shape, governed to
            # invoice_amount instead, never this concept -- mirrors
            # invoice_amount's own excludes={"quantity"} rule below,
            # applied in the opposite direction. PER-ALTERNATIVE, not
            # global: the "quantity" alternative (Form A, same-row rate)
            # must win regardless of a co-located status field -- a
            # consumption record that also happens to track its own
            # lifecycle status is still legitimately Form A evidence.
            alternative_exclude_sibling_concept_sets=(
                frozenset(),  # "quantity" alternative: no exclusion
                frozenset({"status"}),  # "contract_id" alternative: excluded by status
            ),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="hourly_rate",
            concept_type=CanonicalConceptType.MONETARY_AMOUNT.value,
            description="Monetary rate explicitly applicable per hour.",
            aliases=frozenset({"hourly_rate", "labor_rate", "rate_per_hour"}),
            expected_value_patterns=frozenset({"digits", "decimal"}),
            compatible_dataset_roles=frozenset({"contract", "reference", "labor"}),
            requires_sibling_concepts=frozenset({"contract_id"}),
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
            # P3.xxI.2A: a billing document's own lifecycle field
            # (open/closed/paid/...) co-located with a bare "amount" is
            # reusable, generic evidence this is a billed total, not a
            # per-unit rate or an internal cost reference -- observed live
            # on real invoice-shaped Wave 1 data (invoice_id, work_order_id,
            # status all present; no quantity/rate pair). Excludes quantity
            # explicitly: a row that also carries its own quantity is Form
            # A's territory (unit_price), never simultaneously this
            # concept's, even if a status field happens to be present too.
            requires_sibling_concepts=frozenset({"status"}),
            excludes_sibling_concepts=frozenset({"quantity"}),
        )
    )
    registry.register(
        CanonicalConcept(
            concept_code="cost_amount",
            concept_type=CanonicalConceptType.MONETARY_AMOUNT.value,
            description="Monetary cost incurred, in a specific currency.",
            aliases=frozenset({"cost_amount", "cost", "expense_amount", "amount"}),
            # P3.xxI.2A: "work_order" role grant narrowed off the shared
            # blanket set for the same reason as unit_price above -- see
            # requires_sibling_concepts for the precise replacement signal.
            compatible_dataset_roles=frozenset({"invoice", "ledger"}),
            # P3.xxI.2A: a bare cost/expense reference tied directly to a
            # work order, with neither a billing-document identity
            # (invoice_id) nor a rate basis (quantity) alongside it, is the
            # residual shape this concept represents -- an internal
            # reference figure, not a customer-facing invoice total and not
            # a per-unit rate.
            requires_sibling_concepts=frozenset({"work_order_id"}),
            excludes_sibling_concepts=frozenset({"invoice_id", "quantity"}),
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
