"""Evidence-conditioned corrections and cover retention, applied before publication.

A private ``corrections.json`` in the collector state directory lists known extractor errors:

    {"schemaVersion": 1, "corrections": [{"url": "...", "sourceSha256": "<64 hex>",
      "fields": {"duration.pathMinutes": null}, "reason": "..."}]}

A correction applies only while today's primary receipt for ``url`` has the same
``sourceSha256`` as the page it was verified against. When the page changes, the new
extraction is not published for that URL: the published record, if any, stays as it is
and the journal asks for review. Corrections never overwrite newer source evidence.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .storage import bounded_json

CORRECTIONS_FILE = "corrections.json"


def load(state_dir: Path) -> list[dict]:
    try:
        value = json.loads(bounded_json(state_dir / CORRECTIONS_FILE))
    except FileNotFoundError:
        return []
    items = value.get("corrections") if isinstance(value, dict) else None
    if value.get("schemaVersion") != 1 or not isinstance(items, list):
        raise ValueError("Unsupported corrections file")
    for item in items:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("url"), str)
            or re.fullmatch(r"[a-f0-9]{64}", str(item.get("sourceSha256"))) is None
            or not isinstance(item.get("fields"), dict)
            or not item["fields"]
            or not isinstance(item.get("reason"), str)
        ):
            raise ValueError("Each correction needs url, sourceSha256, fields and reason")
    return items


def _set(row: dict, path: str, value: object) -> None:
    *parents, leaf = path.split(".")
    target = row
    for key in parents:
        if not isinstance(target.get(key), dict):
            raise ValueError(f"Correction path {path} does not exist")
        target = target[key]
    if leaf not in target:
        raise ValueError(f"Correction path {path} does not exist")
    target[leaf] = copy.deepcopy(value)


def published_row(resource: dict) -> dict:
    """Turn a published resource back into a collection row with its original evidence."""
    row = {k: v for k, v in resource.items() if k != "id"}
    source = resource["provenance"]
    row["provenance"] = {"sourceUrls": source["sourceUrls"], "fetchedAt": source["fetchedAt"]}
    return row


def apply(
    artifact: dict,
    *,
    receipts: dict[str, str],
    previous: dict[str, dict],
    corrections: list[dict],
) -> tuple[dict, list[dict]]:
    """Return the artifact to publish and review notes. Inputs are not modified.

    ``receipts`` maps fetched URLs to page SHA-256 values. ``previous`` maps URLs to
    currently published rows from ``published_row``.
    """
    artifact = copy.deepcopy(artifact)
    by_url: dict[str, list[dict]] = {}
    for item in corrections:
        by_url.setdefault(item["url"], []).append(item)
    rows, notes = [], []
    for row in artifact["resources"]:
        url, old = row["url"], previous.get(row["url"])
        items = by_url.get(url, [])
        if any(item["sourceSha256"] != receipts.get(url) for item in items):
            # Leave the row out: the snapshot merge keeps the published record and its provenance.
            notes.append({"url": url, "state": "held-for-review", "reason": "source changed"})
            continue
        for item in items:
            for path, value in item["fields"].items():
                _set(row, path, value)
            notes.append({"url": url, "state": "corrected", "fields": sorted(item["fields"])})
        if row.get("artwork") is None and old is not None and old.get("artwork"):
            # An extractor omission is not evidence that a verified cover was removed.
            row["artwork"] = copy.deepcopy(old["artwork"])
            sources = row["provenance"]["sourceUrls"]
            if old["artwork"]["sourceUrl"] not in sources:
                sources.append(old["artwork"]["sourceUrl"])
            notes.append({"url": url, "state": "cover-retained"})
        rows.append(row)
    artifact["resources"] = rows
    _recount(artifact)
    return artifact, notes


def _recount(artifact: dict) -> None:
    """Keep coverage counts consistent after held rows were left out."""
    for item in artifact["coverage"]:
        count = sum(item["categoryId"] in r["categoryIds"] for r in artifact["resources"])
        if count != item["collected"]:
            item["collected"] = count
            if item.get("discovered") is not None and item["discovered"] < count:
                item["discovered"] = None
            if item["state"] == "complete" and item.get("discovered") != count:
                item["state"] = "partial"
