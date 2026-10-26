"""Static hosted setup check: robots must succeed before any agent input."""

from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from .fetch_public import ROBOTS_URL, PublicFetcher
except ImportError:  # Standalone copy mounted next to fetch_public.py.
    from fetch_public import ROBOTS_URL, PublicFetcher


def main() -> None:
    workspace = Path("/workspace")
    output = workspace / "outputs/preflight.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    proof = {
        "schemaVersion": 1,
        "proxyPresent": {
            name: bool(os.environ.get(name))
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            )
        },
        "robotsChecked": False,
    }
    output.write_text(json.dumps(proof))
    print(json.dumps(proof), flush=True)
    try:
        plan = json.loads((workspace / "input/collection-plan.json").read_text())
        fetcher = PublicFetcher(plan, workspace)
        fetcher.fetch(ROBOTS_URL)
        receipts = json.loads(fetcher.receipts_path.read_text())
        proof["robotsChecked"] = receipts.get("robotsChecked") is True
        proof["requests"] = len(receipts["requests"])
        if not proof["robotsChecked"]:
            raise ValueError("No verified robots response")
    except Exception as exc:
        proof["errorType"] = type(exc).__name__
        output.write_text(json.dumps(proof))
        print(json.dumps(proof), flush=True)
        raise SystemExit(1) from None
    output.write_text(json.dumps(proof))
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    main()
