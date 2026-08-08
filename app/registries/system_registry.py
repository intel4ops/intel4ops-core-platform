"""Governed, static registry of customer-declared systems in use.

Metadata only: no credentials, no endpoints, no connection health, no
connector execution. This records what the customer says they use so a
future Connect package can recommend integrations and mapping templates --
it does not implement any of that itself.
"""

from dataclasses import dataclass

SYSTEM_CATEGORIES: tuple[str, ...] = (
    "erp",
    "accounting",
    "cmms_eam",
    "crm",
    "mes",
    "scada",
    "wms",
    "tms",
    "spreadsheet",
    "database",
    "custom",
    "other",
)


@dataclass(frozen=True)
class SystemDefinition:
    code: str
    display_name: str
    category: str
    description: str
    allows_custom_label: bool = False


SYSTEMS: tuple[SystemDefinition, ...] = (
    SystemDefinition("sap", "SAP", "erp", "SAP ERP."),
    SystemDefinition("oracle", "Oracle", "erp", "Oracle ERP / E-Business Suite / Fusion."),
    SystemDefinition(
        "microsoft_dynamics", "Microsoft Dynamics", "erp", "Microsoft Dynamics 365 / NAV / AX."
    ),
    SystemDefinition("odoo", "Odoo", "erp", "Odoo ERP."),
    SystemDefinition("erpnext", "ERPNext", "erp", "ERPNext."),
    SystemDefinition("quickbooks", "QuickBooks", "accounting", "Intuit QuickBooks."),
    SystemDefinition("sage", "Sage", "accounting", "Sage accounting / ERP."),
    SystemDefinition("netsuite", "NetSuite", "erp", "Oracle NetSuite."),
    SystemDefinition("maximo", "Maximo", "cmms_eam", "IBM Maximo."),
    SystemDefinition("ifs", "IFS", "erp", "IFS Applications."),
    SystemDefinition("infor", "Infor", "erp", "Infor ERP/EAM suite."),
    SystemDefinition("salesforce", "Salesforce", "crm", "Salesforce CRM."),
    SystemDefinition("cmms", "CMMS", "cmms_eam", "A computerized maintenance management system."),
    SystemDefinition("mes", "MES", "mes", "A manufacturing execution system."),
    SystemDefinition("scada", "SCADA", "scada", "A SCADA system."),
    SystemDefinition("wms", "WMS", "wms", "A warehouse management system."),
    SystemDefinition("tms", "TMS", "tms", "A transportation management system."),
    SystemDefinition("excel", "Excel", "spreadsheet", "Microsoft Excel or similar spreadsheets."),
    SystemDefinition(
        "custom_erp",
        "Custom ERP",
        "custom",
        "An in-house or bespoke ERP system.",
        allows_custom_label=True,
    ),
    SystemDefinition(
        "custom_database",
        "Custom Database",
        "database",
        "An in-house or bespoke database.",
        allows_custom_label=True,
    ),
    SystemDefinition(
        "other",
        "Other",
        "other",
        "A system not yet in the governed list.",
        allows_custom_label=True,
    ),
)

_SYSTEMS_BY_CODE: dict[str, SystemDefinition] = {item.code: item for item in SYSTEMS}


def get_system(code: str) -> SystemDefinition | None:
    return _SYSTEMS_BY_CODE.get(code)


def is_valid_system_code(code: str) -> bool:
    return code in _SYSTEMS_BY_CODE


def list_systems() -> tuple[SystemDefinition, ...]:
    return SYSTEMS
