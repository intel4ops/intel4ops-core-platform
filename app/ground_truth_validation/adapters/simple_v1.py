from __future__ import annotations

from app.ground_truth_validation.normalizer import (
    ADAPTER_CODE,
    ADAPTER_VERSION,
    normalize_ground_truth,
)
from app.ground_truth_validation.ontology import NormalizedPackage


class SimpleV1Adapter:
    """Wraps the original P3.xxD.1B flat {expected_findings, ...} shape.
    Selected only when a caller's payload has no "schema_version"/
    "documents" package envelope -- i.e. it IS the whole flat payload."""

    adapter_code = ADAPTER_CODE
    adapter_version = ADAPTER_VERSION
    supported_schema_version = ADAPTER_CODE

    def can_handle(self, package_metadata: dict[str, object]) -> bool:
        declared = package_metadata.get("schema_version")
        if declared:
            return declared == self.adapter_code
        # No manifest, no declared schema, no document-role envelope at
        # all -- just a top-level expected_findings list. That is
        # unambiguously the V1 shape.
        return isinstance(package_metadata.get("expected_findings"), list) and not isinstance(
            package_metadata.get("documents"), dict
        )

    def normalize(self, package_documents: dict[str, object]) -> NormalizedPackage:
        return normalize_ground_truth(package_documents)


simple_v1_adapter = SimpleV1Adapter()
