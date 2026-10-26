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
    parser.add_argument("--env-file", type=Path)
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
        cmd.add_argument("--from-frontier", action="store_true")
        if name == "run":
            cmd.add_argument("--live", action="store_true", required=True)
            cmd.add_argument("--daily", action="store_true")
    resume = commands.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--session-id")
    resume.add_argument("--live", action="store_true", required=True)
    remaining = commands.add_parser("remaining")
    remaining.add_argument("run_id")
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("run_id")
    cleanup.add_argument("--live", action="store_true", required=True)
    acknowledge = commands.add_parser("acknowledge")
    acknowledge.add_argument("run_id")
    purge_cache = commands.add_parser("purge-cache")
    purge_cache.add_argument("--live", action="store_true", required=True)
    frontier = commands.add_parser("frontier")
    steps = frontier.add_subparsers(dest="step", required=True)
    bootstrap = steps.add_parser("bootstrap")
    bootstrap.add_argument("artifact", type=Path)
    bootstrap.add_argument("receipts", type=Path)
    preview = steps.add_parser("plan")
    preview.add_argument("--max-pages", type=int, default=30)
    preview.add_argument("--passes", type=int, default=1)
    for name in ("validate", "validate-snapshot", "import"):
        cmd = commands.add_parser(name)
        cmd.add_argument("artifact", type=Path)
        if name == "import":
            cmd.add_argument("--method", choices=["manual", "fixture"], default="manual")
    args = parser.parse_args()

    from .collector import Collector, ManagedAgents, make_plan, session_request
    from .models import CollectionArtifact, Snapshot
    from .storage import SnapshotStore, bounded_json

    try:
        if args.command == "frontier":
            from .frontier import Frontier, simulate

            store = Frontier(args.state_dir)
            if args.step == "bootstrap":
                artifact = json.loads(bounded_json(args.artifact))
                receipts = json.loads(bounded_json(args.receipts))
                if not isinstance(artifact, dict) or not isinstance(receipts, dict):
                    raise ValueError("Artifact and receipts must be JSON objects")
                result = store.record(artifact, receipts, run_id=receipts.get("runId"))
                print(json.dumps(result, indent=2))
                return
            if not 2 <= args.max_pages <= 500 or not 1 <= args.passes <= 30:
                raise ValueError("Use --max-pages 2..500 and --passes 1..30")
            state = store.read()
            # One page of each pass is reserved for robots.txt.
            passes = simulate(state, args.max_pages - 1, args.passes)
            print(
                json.dumps(
                    {
                        "live": False,
                        "queued": len(state["urls"]),
                        "unfetched": sum(
                            1 for e in state["urls"].values() if not e["lastFetchedAt"]
                        ),
                        "passes": [{"day": i + 1, "urls": urls} for i, urls in enumerate(passes)],
                    },
                    indent=2,
                )
            )
            return
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
        if args.command == "validate-snapshot":
            snapshot = Snapshot.model_validate_json(bounded_json(args.artifact))
            print(
                json.dumps(
                    {
                        "valid": True,
                        "resources": len(snapshot.resources),
                        "snapshotId": snapshot.snapshot_id,
                    }
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
        if args.command == "acknowledge":
            result = Collector(args.state_dir, args.snapshot, None).acknowledge(args.run_id)
            print(
                json.dumps(
                    {k: result.get(k) for k in ("runId", "state", "acknowledgedAt")}, indent=2
                )
            )
            return
        from .edge import PurgeError, purge_from_environment

        # Deployment settings only; checked before any billable call. Never sent to the session.
        purge = purge_from_environment() if args.command != "cleanup" else None
        if args.command == "purge-cache":
            if purge is None:
                raise ValueError("Cloudflare purge settings are missing from the environment")
            try:
                purge_id = purge()
            except PurgeError as exc:
                parser.exit(1, f"Cache purge failed: {exc}\n")
            print(
                json.dumps(
                    {"hostname": purge.hostname, "state": "accepted", "purgeId": purge_id},
                    indent=2,
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
            if args.from_frontier:
                from .frontier import Frontier, next_pass

                # Explicit seeds and robots.txt share the page budget; an empty frontier
                # falls back to the default listing seeds.
                seeds.extend(
                    next_pass(Frontier(args.state_dir).read(), args.max_pages - 1 - len(seeds))
                )
            plan = make_plan(
                seed_urls=seeds or None,
                max_pages=args.max_pages,
                max_resources=args.max_resources,
                max_seconds=args.max_seconds,
            )
            request = session_request(plan, args.instructions.read_text())
            if args.command == "run" and args.daily:
                import uuid

                from .storage import now

                daily_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"academy-collector:{args.state_dir.resolve()}:{now().date().isoformat()}",
                )
                plan = plan.model_copy(update={"run_id": str(daily_id)})
                request = session_request(plan, args.instructions.read_text())
                saved_path = args.state_dir / plan.run_id / "journal.json"
                if saved_path.exists():
                    saved = json.loads(bounded_json(saved_path))
                    if (
                        saved.get("state") == "published"
                        and saved.get("cleanup", {}).get("state") == "complete"
                    ):
                        print(json.dumps({"runId": plan.run_id, "dailyAlreadyComplete": True}))
                        return
                    raise ValueError("Today's run requires review/recovery; no daily resubmission")
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
                            "edgePurge": {"hostname": purge.hostname} if purge else None,
                        },
                        indent=2,
                    )
                )
                return
        from .credentials import collector_api_key, collector_client, key_fingerprint

        key = collector_api_key(args.env_file)
        with collector_client(key) as client:
            runner = Collector(
                args.state_dir,
                args.snapshot,
                ManagedAgents(client),
                credential_fingerprint=key_fingerprint(key),
                purge=purge,
            )
            if args.command == "run":
                result = runner.start(plan, request, daily=args.daily)
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
                            "edgePurge",
                        )
                    },
                    indent=2,
                )
            )
        if (result.get("edgePurge") or {}).get("state") == "failed":
            parser.exit(
                3,
                "Snapshot published, but the Cloudflare cache purge failed. Do not rerun "
                "collection; retry only the purge with: academy-collector purge-cache --live\n",
            )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Collection failed: {exc}\n")
    except Exception:
        parser.exit(
            1, "Collection controller interrupted; inspect the saved journal before resuming.\n"
        )
