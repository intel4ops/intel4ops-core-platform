from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalMappingProfile:
    profile_code: str
    industry_pack_code: str
    entity_types: tuple[str, ...]
    event_types: tuple[str, ...]
    metric_types: tuple[str, ...]
    required_mapping_templates: tuple[str, ...]


CANONICAL_MAPPING_PROFILES: tuple[CanonicalMappingProfile, ...] = (
    CanonicalMappingProfile(
        profile_code="job_to_cash",
        industry_pack_code="PACK-J2C",
        entity_types=("customer", "job", "invoice", "payment"),
        event_types=("job_completed", "invoice_issued", "payment_received"),
        metric_types=("job_revenue", "invoice_balance", "days_to_cash"),
        required_mapping_templates=(
            "job_to_cash_customer",
            "job_to_cash_job",
            "job_to_cash_invoice",
            "job_to_cash_payment",
        ),
    ),
    CanonicalMappingProfile(
        profile_code="oilfield_services",
        industry_pack_code="OILFIELD-SERVICES",
        entity_types=("customer", "asset", "technician", "job", "invoice"),
        event_types=("job_dispatched", "service_performed", "invoice_issued"),
        metric_types=("productive_hours", "nonproductive_time", "job_margin"),
        required_mapping_templates=(
            "oilfield_customer",
            "oilfield_asset",
            "oilfield_service_job",
            "oilfield_invoice",
        ),
    ),
)
