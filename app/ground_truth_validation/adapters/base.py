from __future__ import annotations

from typing import Protocol

from app.ground_truth_validation.ontology import NormalizedPackage


class GroundTruthFormatError(ValueError):
    """Raised by an adapter when a package it accepted (can_handle=True)
    turns out to be malformed -- never silently coerced into something
    plausible-looking."""


class GroundTruthPackageAdapter(Protocol):
    """Converts one heterogeneous authored truth package (arbitrary
    documents + optional manifest) into the NormalizedPackage ontology
    (app/ground_truth_validation/ontology.py). An adapter is keyed to a
    *schema shape*, never to a simulation identifier -- see section 4/19:
    SIM-OFS-FIELDMAINT-005 exercises an adapter, it does not define one."""

    adapter_code: str
    adapter_version: str
    supported_schema_version: str

    def can_handle(self, package_metadata: dict[str, object]) -> bool:
        """package_metadata carries whatever is available for role
        detection when no manifest declares an explicit schema_version:
        typically {"schema_version": ..., "manifest": {...} | None,
        "document_roles": [...], "documents": {role: raw_content}}."""
        ...

    def normalize(self, package_documents: dict[str, object]) -> NormalizedPackage:
        """package_documents maps a role name (declared or detected) to
        that document's raw parsed content, plus a reserved "manifest" key
        for the manifest document if one was supplied."""
        ...
