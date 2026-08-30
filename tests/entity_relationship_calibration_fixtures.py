"""P3.xxE.3 section 30: a small, hand-labeled, test-only entity/
relationship calibration benchmark -- never imported by any app/ module,
never a Validation Plane subsystem, no import of app.ground_truth_validation.
Same pattern and philosophy as tests/semantic_calibration_fixtures.py:
bounded, auditable, run through the REAL orchestration pipeline.

Each fixture is a multi-dataset AnalysisCase (relationships require 2+
datasets with co-occurring identifiers, unlike the single-dataframe
semantic calibration fixtures). Expected entities/relationships are
derived directly from the CSV generation formula below (auditable,
deterministic), not guessed and not copied from a prior run's output.

Coverage note (section 30's requested categories): composite-identifier
match and fuzzy/ambiguous-candidate match have NO live callers this
milestone (no compound-identifier concept is registered in
concept_registry.py, and fuzzy resolution is contracts-only per section
12's escape hatch -- see the P3.xxE.3 plan) -- their calibration metrics
are correctly NOT_AVAILABLE, not fabricated, matching the P3.xxE.2
precedent for the same situation."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DatasetEntityRelationshipFixture:
    filename: str
    dataframe: pd.DataFrame


@dataclass(frozen=True)
class EntityRelationshipCalibrationCase:
    name: str
    datasets: list[DatasetEntityRelationshipFixture]
    # (entity_type, canonical_key) set -- every entity expected to resolve.
    expected_entities: set[tuple[str, str]]
    # (left_entity_type, left_key, right_entity_type, right_key, relationship_type) --
    # every relationship expected to be discovered, with its expected type.
    expected_relationships: set[tuple[str, str, str, str, str]]
    # relationship keys (left_type, left_key, right_type, right_key) expected
    # to land in status CONFLICTED specifically (a subset check, since
    # status also depends on confidence which this fixture doesn't hand-pin).
    expected_conflicted: set[tuple[str, str, str, str]]
    rationale: str


def _clean_asset_work_order_case() -> EntityRelationshipCalibrationCase:
    n = 12
    events = pd.DataFrame(
        {
            "asset_id": [f"A-{(i % 4) + 1}" for i in range(n)],
            "work_order_id": [f"WO-{i + 1}" for i in range(n)],
            "event_date": [f"2026-01-{i + 1:02d}" for i in range(n)],
        }
    )
    work_orders = pd.DataFrame(
        {
            "work_order_id": [f"WO-{i + 1}" for i in range(n)],
            "asset_id": [f"A-{(i % 4) + 1}" for i in range(n)],
            "technician_id": [f"T-{i % 3}" for i in range(n)],
        }
    )

    expected_entities = {("ASSET", f"a-{k}") for k in range(1, 5)} | {
        ("WORK_ORDER", f"wo-{i + 1}") for i in range(n)
    }
    expected_relationships = {
        ("WORK_ORDER", f"wo-{i + 1}", "ASSET", f"a-{(i % 4) + 1}", "BELONGS_TO") for i in range(n)
    }
    return EntityRelationshipCalibrationCase(
        name="clean_asset_work_order",
        datasets=[
            DatasetEntityRelationshipFixture("events.csv", events),
            DatasetEntityRelationshipFixture("work_orders.csv", work_orders),
        ],
        expected_entities=expected_entities,
        expected_relationships=expected_relationships,
        expected_conflicted=set(),
        rationale=(
            "Each work order consistently references exactly one asset across both "
            "datasets -- a clean many-to-one BELONGS_TO relationship, no contradicting "
            "evidence anywhere. technician_id has no cross-dataset corroboration and "
            "caps below auto_accept, so PERSON entities are correctly absent."
        ),
    )


def _conflicting_reassignment_case() -> EntityRelationshipCalibrationCase:
    n = 12
    events = pd.DataFrame(
        {
            "asset_id": [f"A-{(i % 4) + 1}" for i in range(n)],
            "work_order_id": [f"WO-{i + 1}" for i in range(n)],
            "event_date": [f"2026-01-{i + 1:02d}" for i in range(n)],
        }
    )
    # Deliberately shifted mapping: the SAME work_order_id values now
    # reference a DIFFERENT asset than in `events`, for every single row --
    # a genuine cross-dataset cardinality contradiction.
    reassignments = pd.DataFrame(
        {
            "asset_id": [f"A-{((i + 1) % 4) + 1}" for i in range(n)],
            "work_order_id": [f"WO-{i + 1}" for i in range(n)],
            "reassigned_date": [f"2026-02-{i + 1:02d}" for i in range(n)],
        }
    )

    expected_entities = {("ASSET", f"a-{k}") for k in range(1, 5)} | {
        ("WORK_ORDER", f"wo-{i + 1}") for i in range(n)
    }
    # Both directions are real, contradictory evidence -- the relationship
    # exists (structurally) but must never resolve to a single confident
    # cardinality; conflict is checked separately below, not the type.
    expected_relationships: set[tuple[str, str, str, str, str]] = set()
    expected_conflicted = {
        ("WORK_ORDER", f"wo-{i + 1}", "ASSET", f"a-{(i % 4) + 1}") for i in range(n)
    } | {("WORK_ORDER", f"wo-{i + 1}", "ASSET", f"a-{((i + 1) % 4) + 1}") for i in range(n)}
    return EntityRelationshipCalibrationCase(
        name="conflicting_reassignment",
        datasets=[
            DatasetEntityRelationshipFixture("events.csv", events),
            DatasetEntityRelationshipFixture("reassignments.csv", reassignments),
        ],
        expected_entities=expected_entities,
        expected_relationships=expected_relationships,
        expected_conflicted=expected_conflicted,
        rationale=(
            "Every work_order_id maps to a DIFFERENT asset_id in `reassignments` than in "
            "`events` -- a genuine, deliberate cardinality contradiction across datasets. "
            "The correct behavior is CONFLICTED, never a silently-picked winner."
        ),
    )


CALIBRATION_CASES = [_clean_asset_work_order_case(), _conflicting_reassignment_case()]
