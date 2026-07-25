from dataclasses import dataclass
from enum import StrEnum


class CalculationOperation(StrEnum):
    COUNT = "count"
    DISTINCT_COUNT = "distinct_count"
    SUM = "sum"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    RATIO = "ratio"
    PERCENTAGE = "percentage"
    ABSOLUTE_VARIANCE = "absolute_variance"
    PERCENTAGE_VARIANCE = "percentage_variance"
    RECONCILIATION = "reconciliation"


@dataclass(frozen=True)
class CalculationDefinition:
    code: str
    version: str
    name: str
    description: str
    operation: CalculationOperation
    required_parameters: tuple[str, ...]
    output_unit: str | None = None
    supports_currency: bool = False
    analytical_level: str = "arithmetic"
    status: str = "active"
    canonical_fields: tuple[str, ...] = ()
    evidence_contract: str | None = None
    unit_policy: str | None = None
    currency_policy: str | None = None
    scope_correction: str | None = None
    domain_owner: str | None = None


class DefinitionNotFoundError(ValueError):
    pass


class DuplicateDefinitionError(ValueError):
    pass


class CalculationRegistry:
    def __init__(self, definitions: list[CalculationDefinition] | None = None) -> None:
        self._definitions: dict[tuple[str, str], CalculationDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: CalculationDefinition) -> None:
        key = (definition.code, definition.version)
        if key in self._definitions:
            raise DuplicateDefinitionError(
                f"Calculation {definition.code} version {definition.version} is registered"
            )
        self._definitions[key] = definition

    def get(self, code: str, version: str) -> CalculationDefinition:
        try:
            return self._definitions[(code, version)]
        except KeyError as exc:
            raise DefinitionNotFoundError(
                f"Calculation {code} version {version} is not registered"
            ) from exc

    def list(self) -> list[CalculationDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]


def default_calculation_registry() -> CalculationRegistry:
    definitions = [
        CalculationDefinition(
            "record_count",
            "1.0",
            "Record count",
            "Count submitted records.",
            CalculationOperation.COUNT,
            (),
        ),
        CalculationDefinition(
            "distinct_count",
            "1.0",
            "Distinct count",
            "Count distinct non-null field values.",
            CalculationOperation.DISTINCT_COUNT,
            ("field",),
        ),
        CalculationDefinition(
            "sum",
            "1.0",
            "Sum",
            "Sum non-null numeric field values.",
            CalculationOperation.SUM,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "average",
            "1.0",
            "Average",
            "Arithmetic mean of non-null numeric values.",
            CalculationOperation.AVERAGE,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "minimum",
            "1.0",
            "Minimum",
            "Minimum non-null numeric field value.",
            CalculationOperation.MINIMUM,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "maximum",
            "1.0",
            "Maximum",
            "Maximum non-null numeric field value.",
            CalculationOperation.MAXIMUM,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "ratio",
            "1.0",
            "Ratio",
            "Divide numerator by denominator.",
            CalculationOperation.RATIO,
            ("numerator", "denominator"),
            output_unit="ratio",
        ),
        CalculationDefinition(
            "percentage",
            "1.0",
            "Percentage",
            "Numerator as a percentage of denominator.",
            CalculationOperation.PERCENTAGE,
            ("numerator", "denominator"),
            output_unit="percent",
        ),
        CalculationDefinition(
            "absolute_variance",
            "1.0",
            "Absolute variance",
            "Actual minus comparison value.",
            CalculationOperation.ABSOLUTE_VARIANCE,
            ("actual", "comparison"),
            supports_currency=True,
        ),
        CalculationDefinition(
            "percentage_variance",
            "1.0",
            "Percentage variance",
            "Actual minus comparison as a percentage of comparison.",
            CalculationOperation.PERCENTAGE_VARIANCE,
            ("actual", "comparison"),
            output_unit="percent",
        ),
        CalculationDefinition(
            "reconciliation",
            "1.0",
            "Reconciliation difference",
            "Left total minus right total.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            supports_currency=True,
        ),
        *_approved_oikb_seed_definitions(),
    ]
    return CalculationRegistry(definitions)


_EVIDENCE_CONTRACT = (
    "Tenant-matched dataset, source-system, lineage and bounded record evidence; "
    "definition and input fingerprints; calculation parameters and result."
)


def _seed(
    code: str,
    name: str,
    description: str,
    operation: CalculationOperation,
    required_parameters: tuple[str, ...],
    canonical_fields: tuple[str, ...],
    unit_policy: str,
    currency_policy: str,
    scope_correction: str,
    domain_owner: str,
    *,
    supports_currency: bool = False,
) -> CalculationDefinition:
    return CalculationDefinition(
        code=code,
        version="1.0.0",
        name=name,
        description=description,
        operation=operation,
        required_parameters=required_parameters,
        supports_currency=supports_currency,
        canonical_fields=canonical_fields,
        evidence_contract=_EVIDENCE_CONTRACT,
        unit_policy=unit_policy,
        currency_policy=currency_policy,
        scope_correction=scope_correction,
        domain_owner=domain_owner,
    )


def _approved_oikb_seed_definitions() -> list[CalculationDefinition]:
    currency_policy = "One ISO currency per execution; mixed or missing currencies block; no FX."
    reconciliation_scope = (
        "Caller supplies governed, scope-aligned totals; matching, grouping, conversion and "
        "percentage/rule evaluation remain explicit separate steps."
    )
    return [
        _seed(
            "SHARED.QUALITY.DIRECT_QUALITY_COST",
            "Direct quality cost",
            "Sum directly observed quality-event costs, excluding modeled lost capacity.",
            CalculationOperation.SUM,
            ("field",),
            (
                "issue_type",
                "direct_cost",
                "currency",
                "product_service_id",
                "asset_id",
                "operation_id",
                "evidence_id",
            ),
            "Currency amount.",
            currency_policy,
            "Caller supplies governed direct-cost events; lost-capacity estimates are excluded.",
            "Quality Cost and Finance Control Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.FINANCE.OUTSTANDING_BALANCE",
            "Outstanding balance",
            "Calculate posted invoice balance after completed matched payments.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("invoice_id", "gross_amount", "payment_amount", "payment_status", "currency"),
            "Currency amount.",
            currency_policy,
            "Overdue/date logic, credits, disputes, unapplied or reversed payments are excluded.",
            "Finance / Accounts Receivable Control Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.FINANCE.DISCOUNT_VARIANCE",
            "Discount variance",
            "Compare actual discount with a governed approved discount baseline.",
            CalculationOperation.ABSOLUTE_VARIANCE,
            ("actual", "comparison"),
            ("actual_discount", "approved_discount", "comparison_basis", "currency"),
            "Amount or percent basis must be declared; this seed returns absolute variance.",
            currency_policy,
            "The baseline is governed; uncontrolled peer benchmarking is excluded.",
            "Pricing and Finance Control Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.PROCUREMENT.PURCHASE_PRICE_VARIANCE",
            "Purchase price variance",
            "Compare actual unit purchase cost with a governed valid benchmark cost.",
            CalculationOperation.ABSOLUTE_VARIANCE,
            ("actual", "comparison"),
            ("actual_unit_cost", "benchmark_unit_cost", "item_id", "unit_of_measure", "currency"),
            "Currency per identical item unit.",
            currency_policy,
            "Quantity exposure, statistical benchmarks and unit conversion are excluded.",
            "Procurement Control Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.PROCUREMENT.THREE_WAY_MATCH_DIFFERENCE",
            "Three-way match difference",
            "Reconcile invoice amount with governed PO/receipt-supported amount.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("invoice_amount", "supported_amount", "currency", "matching_key_policy"),
            "Currency amount.",
            currency_policy,
            reconciliation_scope + " Fuzzy matching and arbitrary joins are excluded.",
            "Accounts Payable and Procurement Control Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.ASSET.MAINTENANCE_COST_VARIANCE",
            "Maintenance cost variance",
            "Compare governed actual maintenance cost per unit with its benchmark.",
            CalculationOperation.ABSOLUTE_VARIANCE,
            ("actual", "comparison"),
            ("actual_cost_per_unit", "benchmark_cost_per_unit", "output_unit", "currency"),
            "Currency per identical declared output unit.",
            currency_policy,
            "Caller supplies cost-per-unit values; ratio construction and zero-output "
            "handling precede this seed.",
            "Asset Maintenance and Finance Control Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.FINANCE.REVENUE_RECONCILIATION",
            "Revenue reconciliation",
            "Reconcile governed revenue and receipt totals.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("revenue_total", "receipt_total", "period", "currency"),
            "Currency amount.",
            currency_policy,
            reconciliation_scope + " Ranking, fuzzy matching and fraud inference are excluded.",
            "Controller and Revenue Assurance Owner",
            supports_currency=True,
        ),
        _seed(
            "SHARED.FINANCE.BUDGET_VARIANCE",
            "Budget variance",
            "Compare governed actual-plus-commitment spend with an approved budget.",
            CalculationOperation.ABSOLUTE_VARIANCE,
            ("actual", "comparison"),
            ("spend_and_commitment_total", "budget_amount", "period", "cost_center", "currency"),
            "Currency amount.",
            currency_policy,
            "Caller supplies a de-duplicated spend/commitment total; percentage and "
            "threshold rules are separate.",
            "FP&A Budget Control Owner",
            supports_currency=True,
        ),
        _seed(
            "MOBILITY.REVENUE.FAREBOX_RECONCILIATION",
            "Farebox reconciliation",
            "Reconcile governed fare revenue and settlement totals.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("fare_total", "settlement_total", "route_or_depot", "period", "currency"),
            "Currency amount.",
            currency_policy,
            reconciliation_scope
            + " Ridership estimation, fraud conclusions and route ranking are excluded.",
            "Mobility Fare Revenue Control Owner",
            supports_currency=True,
        ),
        _seed(
            "MANUFACTURING.MATERIAL.MASS_BALANCE_VARIANCE",
            "Material mass-balance variance",
            "Reconcile governed material input and output totals.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("input_total", "output_total", "operation_or_batch", "period", "unit"),
            "One identical physical unit per execution; no implicit conversion.",
            "Not applicable.",
            reconciliation_scope + " Inferred yield and optimization are excluded.",
            "Manufacturing Material Control Owner",
        ),
        _seed(
            "OIL_GAS.CUSTODY.CUSTODY_TRANSFER_BALANCE",
            "Custody-transfer balance",
            "Reconcile governed custody-transfer source and destination volumes.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("source_volume", "destination_volume", "transfer_id", "standardized_basis", "unit"),
            "Identical standardized volume basis and unit; no implicit conversion.",
            "Not applicable.",
            reconciliation_scope + " Uncertainty modeling and leak conclusions are excluded.",
            "Oil and Gas Custody Measurement Owner",
        ),
        _seed(
            "OIL_GAS.PRODUCTION.NETWORK_ALLOCATION_VARIANCE",
            "Network allocation variance",
            "Reconcile governed allocated and measured production totals.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("allocated_total", "measured_total", "facility", "period", "unit"),
            "One identical standardized volume or mass unit per execution.",
            "Not applicable.",
            reconciliation_scope
            + " Probabilistic allocation and network optimization are excluded.",
            "Oil and Gas Production Allocation Owner",
        ),
        _seed(
            "UTILITY.WATER.DMA_WATER_BALANCE",
            "DMA water balance",
            "Reconcile governed system input and authorized-consumption water volumes.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            ("system_input_total", "authorized_consumption_total", "dma_id", "period", "unit"),
            "Identical water-volume unit and reporting period; no implicit conversion.",
            "Not applicable.",
            reconciliation_scope
            + " Leak localization, forecasting and pressure optimization are excluded.",
            "Utility Water Balance Owner",
        ),
    ]
