from uuid import uuid4

from app.validation.simulation import SimulationGenerator
from app.validation.suites import GOLDEN_SCENARIOS, CertificationSuites, GoldenScenarioSuite


def test_all_four_golden_scenarios_reconcile_to_approved_oracles() -> None:
    results = GoldenScenarioSuite().run(uuid4())
    assert tuple(result.scenario_code for result in results) == GOLDEN_SCENARIOS
    assert all(result.passed for result in results)
    assert all(result.assertion_count == 3 for result in results)


def test_tenant_isolation_and_idempotent_replay() -> None:
    generator = SimulationGenerator()
    first_org = uuid4()
    second_org = uuid4()
    first = generator.generate("PORT-CRANE-001", first_org, seed=77)
    replay = generator.generate("PORT-CRANE-001", first_org, seed=77)
    second = generator.generate("PORT-CRANE-001", second_org, seed=77)
    suites = CertificationSuites()
    assert suites.tenant_isolation(first, second).passed
    assert suites.idempotency(first, replay).passed


def test_authorization_fails_closed_for_each_required_control() -> None:
    suites = CertificationSuites()
    assert suites.authorization(
        authenticated=True,
        permitted=True,
        membership_active=True,
        client_active=True,
    ).passed
    for failed_control in (
        "authenticated",
        "permitted",
        "membership_active",
        "client_active",
    ):
        controls = {
            "authenticated": True,
            "permitted": True,
            "membership_active": True,
            "client_active": True,
        }
        controls[failed_control] = False
        assert not suites.authorization(**controls).passed


def test_security_rejects_secrets_and_unsafe_paths() -> None:
    suites = CertificationSuites()
    assert suites.security({"reference": "fixture-001"}, "scenario.json").passed
    assert not suites.security({"password": "redacted"}, "scenario.json").passed
    assert not suites.security({"reference": "fixture-001"}, "../scenario.json").passed


def test_resilience_requires_no_duplicates_and_failure_audit() -> None:
    suites = CertificationSuites()
    assert suites.resilience(
        original_count=10,
        replay_count=10,
        duplicate_findings=0,
        duplicate_actions=0,
        duplicate_usage=0,
        duplicate_ledger_entries=0,
        failure_audit_emitted=True,
    ).passed
    assert not suites.resilience(
        original_count=10,
        replay_count=11,
        duplicate_findings=1,
        duplicate_actions=0,
        duplicate_usage=0,
        duplicate_ledger_entries=0,
        failure_audit_emitted=False,
    ).passed


def test_observability_requires_correlated_tenant_safe_event() -> None:
    event = {
        "correlation_id": "corr-1",
        "organization_id": str(uuid4()),
        "operation": "golden.validate",
        "outcome": "passed",
        "duration_ms": 12,
        "occurred_at": "2026-07-27T00:00:00Z",
    }
    suites = CertificationSuites()
    assert suites.observability(event).passed
    event.pop("correlation_id")
    assert not suites.observability(event).passed
