# Model Capability Registry — Design Only (P3.xxE.2 section 26)

**Not implemented in P3.xxE.2.** This document exists so the eventual milestone that activates Intel4Ops's mathematical/scientific models (statistical, reliability, forecasting, decision) has a concrete interface to build against, and so P3.xxE.2's semantic contracts are designed with this consumer in mind (see `docs/p3xxe2-adaptive-field-interpretation-report.md`'s "P3.xxE.1A Integration" section on the read-only semantic-to-mapping bridge this registry would eventually sit downstream of).

## Purpose

Today, model/method activation across Statistical Intelligence, Reliability Intelligence, Forecasting Intelligence, and Decision Intelligence is registered per-domain (`app/registries/calculation_registry.py` and equivalents), each with its own ad hoc readiness/requirement checks. A `ModelCapabilityRegistry` would generalize this: one place that declares, for every registerable model/method, exactly what governed semantic and relationship inputs it needs before it's allowed to run — reusing the same registry-of-data-not-code pattern already established by `CanonicalConceptRegistry` (`app/semantic/concept_registry.py`), `EngineRegistry`, and `TrustRuleRegistry`.

## Proposed contract

```python
@dataclass(frozen=True)
class ModelCapabilityDeclaration:
    model_code: str
    model_version: str
    model_category: str  # e.g. "statistical", "reliability", "forecasting", "decision"

    required_concepts: frozenset[str]  # CanonicalConceptRegistry concept_codes
    optional_concepts: frozenset[str]

    required_relationships: frozenset[
        str
    ]  # P3.xxE.3 RelationshipType values (now real -- see below)
    optional_relationships: frozenset[str]

    required_measures: frozenset[str]  # quantity/monetary_amount-typed concepts specifically

    # P3.xxE.4 catch-up: a model whose readiness depends on operational
    # sequence/state, not just entity/relationship structure.
    required_activities: frozenset[
        str
    ]  # P3.xxE.4 ActivityType values (app/process/activity_type.py)
    required_activity_sequences: frozenset[tuple[str, str]]  # (from_type, to_type) PRECEDES pairs
    required_states: frozenset[str]  # canonical state names (app/process/state_normalization.py)
    minimum_process_confidence: float  # floor on CanonicalOperationalProcess.overall_confidence

    minimum_semantic_confidence: float  # e.g. 0.70 -- below this, a required concept's
    # effective interpretation isn't trusted as input
    minimum_relationship_confidence: float  # same idea, now that P3.xxE.3 exists

    currency_behavior: str  # "single_currency_only" | "multi_currency_aware" | "currency_agnostic"
    unit_behavior: str  # "single_unit_only" | "unit_aware" | "unit_agnostic"

    outputs: frozenset[str]  # what this model produces, for downstream chaining
    evidence_requirements: frozenset[str]  # what evidence must accompany a governed output
```

## How it would consume P3.xxE.1/E.1A/E.2/E.3/E.4

- `required_concepts`/`minimum_semantic_confidence` would be checked against the **effective semantic interpretation** contract P3.xxE.1A already exposes read-only (`GET .../semantic/effective`) — never the raw machine proposal, and never a decision with `human_validated=false` below the model's own confidence floor unless the model's own `minimum_semantic_confidence` is at or below `auto_accept_min` (0.90).
- A model whose `required_concepts` aren't all present at sufficient confidence would report a `BLOCKED`/`PARTIAL` readiness result (mirroring `IntelligenceReadinessResult`'s existing `READY|PARTIAL|BLOCKED` pattern from the P3.xxC.1 architecture), never silently run on incomplete governed inputs.
- **P3.xxE.3 catch-up** (this field was speculative when P3.xxE.2 wrote this doc; P3.xxE.3 has since shipped a real vocabulary): `required_relationships` now references `app/entities/relationship_type.py::RelationshipType` (`REFERENCES`/`BELONGS_TO`/`HAS`/`USES`/`GENERATES`/`PERFORMED_BY`/`LOCATED_AT`/`ASSOCIATED_WITH`), checked against `GET .../analysis-cases/{case_id}/relationships` at or above `minimum_relationship_confidence`. Live-corpus baseline (P3.xxE.3/E.4 certification, 11 real cases): **zero** `CanonicalCaseRelationship` rows corpus-wide — a model declaring any non-empty `required_relationships` would today report `BLOCKED` on every real case, an honest reflection of the corpus's actual structure, not a registry defect.
- **P3.xxE.4 (new)**: `required_activities`/`required_activity_sequences`/`required_states` would be checked against `GET .../analysis-cases/{case_id}/processes` (`CanonicalProcessActivity.activity_type`/`CanonicalProcessEdge.edge_type=PRECEDES` pairs/`CanonicalProcessActivity.state_value`) at or above `minimum_process_confidence`. Per plan review correction 1, only activities/states reaching a NAMED (non-GENERIC/non-raw) value ever satisfy a required-activity/required-state check — a GENERIC placeholder or an un-normalized raw state value never counts, regardless of its `activity_existence_confidence`/`state_existence_confidence`. Live baseline: real activities are readily discoverable (temporal/status fields exist widely), but named PRECEDES sequences and named state transitions are comparatively rare given most real timestamp/status fields sit at `accepted_with_flag`/`review_required` tier — a model with a `required_activity_sequences` dependency should expect `PARTIAL`/`BLOCKED` readiness on much of the real corpus today, not `READY`.

## Explicitly deferred

- No registry instance, no persistence, no API surface in this milestone.
- No wiring into any existing Statistical/Reliability/Forecasting/Decision registry.
- No adaptive activation logic (depends on P3.xxE.5).

This document is the only artifact P3.xxE.2 produces for this concept — a stable interface shape for a future milestone to implement against, not a commitment to its exact field list. P3.xxE.3/P3.xxE.4 have since added the relationship/process fields above without otherwise revising the shape.
