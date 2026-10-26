"""Server entry point and private, explicit collection operations."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def serve() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(os.getenv("ACADEMY_SNAPSHOT_PATH", "data/snapshot.json")),
    )
    parser.add_argument("--frontend-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn

    from .app import create_app

    uvicorn.run(
        create_app(args.snapshot, args.frontend_dir),
        host=args.host,
        port=args.port,
        log_level="info",
        server_header=False,
        proxy_headers=False,
    )


def collect() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(os.getenv("ACADEMY_SNAPSHOT_PATH", "data/snapshot.json")),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.getenv("ACADEMY_COLLECTOR_STATE", "data/collector")),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("dry-run", "run"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--instructions", type=Path, default=Path("prompts/collector.md"))
        cmd.add_argument("--max-pages", type=int, default=80)
        cmd.add_argument("--max-resources", type=int, default=500)
        cmd.add_argument("--max-seconds", type=int, default=600)
        cmd.add_argument("--seed", action="append", default=[])
        cmd.add_argument("--seeds-file", type=Path)
        if name == "run":
            cmd.add_argument("--live", action="store_true", required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--session-id")
    resume.add_argument("--live", action="store_true", required=True)
    remaining = commands.add_parser("remaining")
    remaining.add_argument("run_id")
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("run_id")
    cleanup.add_argument("--live", action="store_true", required=True)
    for name in ("validate", "import"):
        cmd = commands.add_parser(name)
        cmd.add_argument("artifact", type=Path)
        if name == "import":
            cmd.add_argument("--method", choices=["manual", "fixture"], default="manual")
    args = parser.parse_args()

    from .collector import Collector, ManagedAgents, make_plan, session_request
    from .models import CollectionArtifact
    from .storage import SnapshotStore, bounded_json

    try:
        if args.command == "remaining":
            import uuid

            uuid.UUID(args.run_id)
            directory = args.state_dir / args.run_id
            journal = json.loads(bounded_json(directory / "journal.json"))
            try:
                receipts = json.loads(bounded_json(directory / "receipts.json"))
            except FileNotFoundError:
                receipts = {"requests": []}
            successful = sorted(
                {r["url"] for r in receipts.get("requests", []) if r.get("status") == 200}
            )
            print(
                json.dumps(
                    {
                        "runId": args.run_id,
                        "state": journal["state"],
                        "successfulUrls": successful,
                        "remainingSeedUrls": [
                            u for u in journal["plan"]["seedUrls"] if u not in successful
                        ],
                    },
                    indent=2,
                )
            )
            return
        if args.command in {"validate", "import"}:
            artifact = CollectionArtifact.model_validate_json(bounded_json(args.artifact))
            if args.command == "validate":
                print(json.dumps({"valid": True, "resources": len(artifact.resources)}))
            else:
                result = SnapshotStore(args.snapshot).publish(args.artifact, method=args.method)
                print(
                    json.dumps(
                        {"snapshotId": result.snapshot_id, "resources": len(result.resources)}
                    )
                )
            return
        if args.command in {"dry-run", "run"}:
            seeds = list(args.seed)
            if args.seeds_file:
                text = bounded_json(args.seeds_file).decode()
                if text.lstrip().startswith("["):
                    values = json.loads(text)
                    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
                        raise ValueError("Seed file must contain a JSON string array")
                else:
                    values = [x.strip() for x in text.splitlines() if x.strip()]
                seeds.extend(values)
            plan = make_plan(
                seed_urls=seeds or None,
                max_pages=args.max_pages,
                max_resources=args.max_resources,
                max_seconds=args.max_seconds,
            )
            request = session_request(plan, args.instructions.read_text())
            if args.command == "dry-run":
                print(
                    json.dumps(
                        {
                            "live": False,
                            "plan": plan.model_dump(mode="json", by_alias=True),
                            "agent": {
                                k: v for k, v in request["agent"].items() if k != "instructions"
                            },
                            "environment": {
                                k: v for k, v in request["environment"].items() if k != "files"
                            },
                            "inputFiles": [f["path"] for f in request["environment"]["files"]],
                        },
                        indent=2,
                    )
                )
                return
        from openai import OpenAI

        # Fixed official API destination; do not inherit an unrelated OPENAI_BASE_URL.
        with OpenAI(base_url="https://api.openai.com/v1", timeout=15, max_retries=0) as client:
            runner = Collector(args.state_dir, args.snapshot, ManagedAgents(client))
            if args.command == "run":
                result = runner.start(plan, request)
            elif args.command == "cleanup":
                result = runner.cleanup(args.run_id)
            else:
                result = runner.resume(args.run_id, session_id=args.session_id)
            print(
                json.dumps(
                    {
                        k: result.get(k)
                        for k in (
                            "runId",
                            "state",
                            "sessionId",
                            "turnId",
                            "snapshotId",
                            "remoteMayBeRunning",
                            "cleanup",
                        )
                    },
                    indent=2,
                )
            )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Collection failed: {exc}\n")
    except Exception:
        parser.exit(
            1, "Collection controller interrupted; inspect the saved journal before resuming.\n"
        )
