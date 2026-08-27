from uuid import uuid4

import pandas as pd

from app.models.analysis_case import EntityLinkStatus
from app.services.entity_resolution_service import DatasetEntityInput, entity_resolution_service


def test_matches_asset_across_datasets_by_exact_canonical_id() -> None:
    maint_df = pd.DataFrame({"asset_id": ["V1", "V2"]})
    ops_df = pd.DataFrame({"asset_id": ["V1", "V3"]})
    links = entity_resolution_service.resolve(
        [
            DatasetEntityInput(uuid4(), uuid4(), maint_df),
            DatasetEntityInput(uuid4(), uuid4(), ops_df),
        ]
    )
    by_key = {link.canonical_key: link for link in links if link.entity_type == "asset"}
    assert by_key["V1"].status == EntityLinkStatus.MATCHED.value
    assert len(by_key["V1"].source_dataset_ids) == 2
    assert by_key["V2"].status == EntityLinkStatus.UNRESOLVED.value
    assert by_key["V3"].status == EntityLinkStatus.UNRESOLVED.value


def test_no_fuzzy_matching_different_identifiers_never_link() -> None:
    df_a = pd.DataFrame({"asset_id": ["V1"]})
    df_b = pd.DataFrame({"asset_id": ["v1"]})  # different case -- must NOT fuzzy-match
    links = entity_resolution_service.resolve(
        [
            DatasetEntityInput(uuid4(), uuid4(), df_a),
            DatasetEntityInput(uuid4(), uuid4(), df_b),
        ]
    )
    statuses = {link.canonical_key: link.status for link in links}
    assert statuses["V1"] == EntityLinkStatus.UNRESOLVED.value
    assert statuses["v1"] == EntityLinkStatus.UNRESOLVED.value


def test_resolves_operational_event_and_location_entity_types_independently() -> None:
    ops_df = pd.DataFrame({"operational_event_id": ["T1"], "route_id": ["R1"]})
    ops_df2 = pd.DataFrame({"operational_event_id": ["T1"], "route_id": ["R1"]})
    links = entity_resolution_service.resolve(
        [
            DatasetEntityInput(uuid4(), uuid4(), ops_df),
            DatasetEntityInput(uuid4(), uuid4(), ops_df2),
        ]
    )
    entity_types = {(link.entity_type, link.entity_subtype) for link in links}
    assert ("operational_event", None) in entity_types
    assert ("location", "route") in entity_types
