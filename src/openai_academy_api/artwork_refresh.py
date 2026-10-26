"""Prepare a validated artwork-only snapshot from bounded public fetch receipts."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from .corrections import published_row
from .course_artwork import apply_course_artwork
from .models import (
    CollectionArtifact,
    Metadata,
    Resource,
    Snapshot,
    assemble_snapshot,
    metadata_hash,
)
from .security import public_academy_url


def prepare_artwork_refresh(
    snapshot: Snapshot, receipts: dict, *, previous: Snapshot | None = None
) -> tuple[Snapshot, CollectionArtifact]:
    requests = receipts.get("requests")
    if receipts.get("robotsChecked") is not True or not isinstance(requests, list):
        raise ValueError("Artwork refresh requires bounded public fetch receipts")
    times = {}
    for receipt in requests:
        if not isinstance(receipt, dict):
            raise ValueError("Malformed artwork fetch receipt")
        if receipt.get("status") != 200:
            continue
        url = public_academy_url(receipt["url"], discovery=True)
        size, digest = receipt.get("bytes"), receipt.get("sha256")
        if (
            type(size) is not int
            or size <= 0
            or not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
        ):
            raise ValueError("Successful artwork source receipt is incomplete")
        checked = datetime.fromisoformat(receipt["checkedAt"].replace("Z", "+00:00"))
        if checked.tzinfo is None or checked > datetime.now(UTC):
            raise ValueError("Artwork source receipt time is invalid")
        times[url] = max(checked, times.get(url, checked))
    if "https://academy.openai.com/robots.txt" not in times:
        raise ValueError("Artwork refresh requires a successful robots receipt")
    before = {resource.url: resource for resource in snapshot.resources}
    previous_rows = {
        resource.url: resource.model_dump(mode="json", by_alias=True)
        for resource in (previous.resources if previous else [])
    }
    data = apply_course_artwork(
        snapshot.model_dump(mode="json", by_alias=True), requests, previous=previous_rows
    )
    resources = []
    changed = False
    for row in data["resources"]:
        old = before[row["url"]]
        if row.get("artwork") != old.model_dump(mode="json", by_alias=True).get("artwork"):
            source = row["artwork"]["sourceUrl"]
            retained = previous_rows.get(row["url"], {}).get("artwork") == row["artwork"]
            if not retained and (source not in times or row["url"] not in times):
                raise ValueError("Updated artwork lacks a successful source receipt")
            row["provenance"]["fetchedAt"] = max(
                old.provenance.fetched_at,
                times.get(source, old.provenance.fetched_at),
                times.get(row["url"], old.provenance.fetched_at),
            ).isoformat()
            metadata = Metadata.model_validate(
                {key: value for key, value in row.items() if key not in {"id", "provenance"}}
            )
            row["provenance"]["contentHash"] = metadata_hash(metadata)
            resources.append(Resource.model_validate_json(json.dumps(row)))
            changed = True
        else:
            resources.append(old)
    refreshed = (
        assemble_snapshot(
            max(snapshot.generated_at, *times.values()),
            snapshot.categories,
            resources,
            snapshot.coverage,
        )
        if changed
        else snapshot
    )
    artifact = CollectionArtifact.model_validate_json(
        json.dumps(
            {
                "schemaVersion": 1,
                "generatedAt": refreshed.generated_at.isoformat(),
                "categories": [
                    item.model_dump(mode="json", by_alias=True) for item in refreshed.categories
                ],
                "resources": [
                    published_row(item.model_dump(mode="json", by_alias=True))
                    for item in refreshed.resources
                ],
                "coverage": [
                    item.model_dump(mode="json", by_alias=True) for item in refreshed.coverage
                ],
                "fetchReport": {
                    "requests": len(requests),
                    "robotsChecked": True,
                    "completedWithinLimits": True,
                },
            }
        )
    )
    return refreshed, artifact
