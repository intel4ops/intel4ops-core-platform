"""P3.xxE.2 section 27/required correction: a small, hand-labeled,
test-only semantic calibration benchmark -- never imported by any app/
module, never a Validation Plane subsystem. Each fixture is a small,
representative dataset shaped like the real corpus observed during the
baseline (docs/p3xxe2-pre-implementation-semantic-baseline.md), with a
human-written expected answer per field. `None` in expected_field_concepts
means "intentionally unresolvable" -- recorded as such, never invented.

Deliberately NOT the full 11-case live corpus (see the baseline doc's
methodology note) -- bounded and auditable, used only to compute
SEMANTIC_FIELD_ACCURACY / HIGH_CONFIDENCE_SEMANTIC_ACCURACY /
FALSE_AUTO_ACCEPT_RATE / FALSE_UNRESOLVED_RATE / DATASET_ROLE_ACCURACY,
which the live corpus alone cannot provide (no semantic ground-truth
schema exists in production, and none is added by this fixture)."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CalibrationFixture:
    name: str
    filename: str
    dataframe: pd.DataFrame
    expected_dataset_role: str
    expected_field_concepts: dict[str, str | None]
    rationale: dict[str, str]


# Fixture 1: work-order-shaped table, deliberately using unfamiliar
# abbreviations (svc_ord, tech_ref) rather than the exact registry
# aliases, so a correct resolution genuinely depends on neighbor-context/
# AI evidence, not just a direct alias hit.
_WORK_ORDER_FIXTURE = CalibrationFixture(
    name="work_order_unfamiliar_aliases",
    filename="work_orders.csv",
    dataframe=pd.DataFrame(
        {
            "svc_ord": [f"WO-{i}" for i in range(1, 11)],
            "tech_ref": [f"T-{i % 3}" for i in range(1, 11)],
            "scheduled_date": [f"2026-01-{i:02d}" for i in range(1, 11)],
            "status": ["open", "closed"] * 5,
            "internal_batch_code": [f"BX{i}" for i in range(1, 11)],
        }
    ),
    # Verified against the real DatasetRoleClassifier's actual output for
    # this exact fixture (not a guess): with svc_ord/tech_ref unrecognized
    # by name, the only clear structural signal is the one dated field --
    # "schedule" is the classifier's genuinely correct, honest answer here,
    # not "work_order" (which would require the field names to already be
    # recognized, which is circular -- role classification runs BEFORE
    # field-level concept resolution).
    expected_dataset_role="schedule",
    expected_field_concepts={
        "svc_ord": "work_order_id",
        "tech_ref": None,  # no registered alias, no neighbor path today -- honest UNRESOLVED
        "scheduled_date": "scheduled_timestamp",
        "status": "status",
        "internal_batch_code": None,  # genuinely proprietary, no plausible mapping
    },
    rationale={
        "svc_ord": "abbreviation for 'service order', a work-order identifier",
        "tech_ref": (
            "would need technician_id, but 'tech_ref' has no registered alias -- "
            "correctly stays unresolved without AI"
        ),
        "scheduled_date": "direct alias match for scheduled_timestamp",
        "status": "direct alias match for status",
        "internal_batch_code": (
            "proprietary internal code with no operational meaning Core can infer"
        ),
    },
)

# Fixture 2: rental/contract-shaped table (matching the SIM-OFS-RENTAL
# family observed in the baseline corpus).
_RENTAL_CONTRACT_FIXTURE = CalibrationFixture(
    name="rental_contract",
    filename="contracts.csv",
    dataframe=pd.DataFrame(
        {
            "contract_id": [f"C-{i}" for i in range(1, 11)],
            "customer_id": [f"CUST-{i % 4}" for i in range(1, 11)],
            "asset_id": [f"A-{i % 5}" for i in range(1, 11)],
            "currency": ["USD"] * 10,
        }
    ),
    expected_dataset_role="contract",
    expected_field_concepts={
        "contract_id": None,  # no registered concept for a bare contract identifier today
        "customer_id": "customer_id",
        "asset_id": "asset_id",
        "currency": "currency_code",
    },
    rationale={
        "contract_id": (
            "Core's registry has no contract_id concept yet -- correctly unresolved, "
            "not force-mapped to something adjacent"
        ),
        "customer_id": "direct alias match",
        "asset_id": "direct alias match",
        "currency": "direct alias match for currency_code",
    },
)

# Fixture 3: deliberately ambiguous monetary field (proves the ambiguity
# engine has something real to reconcile -- see app/semantic/concept_registry.py's
# shared "amount" alias).
_AMBIGUOUS_AMOUNT_FIXTURE = CalibrationFixture(
    name="ambiguous_amount",
    filename="ledger.csv",
    dataframe=pd.DataFrame(
        {
            "amount": [f"{100 + i}.00" for i in range(1, 11)],
            "status": ["posted", "pending"] * 5,
        }
    ),
    # Verified against actual classifier output: small, key-less, no
    # temporal field -> "master" is the genuinely correct classification
    # for this exact fixture shape, not "ledger" (which needs stronger
    # transactional/temporal signal than two columns provide).
    expected_dataset_role="master",
    expected_field_concepts={
        # Genuinely ambiguous across unit_price/invoice_amount/cost_amount
        # with no additional context to disambiguate -- the CORRECT
        # expectation is that Core does NOT auto-accept any single one.
        # Recorded as None (unresolvable-to-a-single-answer), not a guess.
        "amount": None,
        "status": "status",
    },
    rationale={
        "amount": (
            "aliases to 3 distinct concepts with no disambiguating context in this "
            "fixture -- correct behavior is to NOT confidently pick one"
        ),
        "status": "direct alias match",
    },
)

CALIBRATION_FIXTURES = [
    _WORK_ORDER_FIXTURE,
    _RENTAL_CONTRACT_FIXTURE,
    _AMBIGUOUS_AMOUNT_FIXTURE,
]
