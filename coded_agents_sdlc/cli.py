"""Non-executing Coded Agents control-plane CLI.

Graph Harness CLI remains authoritative for state transitions and gates.
This CLI never runs workloads, publishes, deploys or alters external tenants.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from graph_harness.model import ValidationError

from .control import scaffold, verify
from .project import PLATFORMS
from .usage import record_result, usage_totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coded-agents-sdlc")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Plan or apply an idempotent governed-project scaffold")
    init.add_argument("--root", required=True)
    init.add_argument("--project-id", required=True)
    init.add_argument("--repository", required=True, help="Expected GitHub owner/repo")
    init.add_argument("--mode", choices=("MVP", "SHIP"), default="MVP")
    init.add_argument("--platform", choices=PLATFORMS, default="generic")
    init.add_argument("--branch", help="Optional explicit Git branch identity gate")
    init.add_argument("--apply", action="store_true", help="Required for filesystem writes; dry-run is the default")

    check = commands.add_parser("check", help="Read-only project identity, contract and hash-chain check")
    check.add_argument("--root", required=True)

    status = commands.add_parser("status", help="Read-only graph status and all-attempt token/cost totals")
    status.add_argument("--root", required=True)

    usage = commands.add_parser("record-run", help="Append aggregate builder metrics to the Graph event ledger")
    usage.add_argument("--root", required=True)
    usage.add_argument("--node", required=True)
    usage.add_argument("--actor", required=True)
    usage.add_argument("--result-file", required=True)
    usage.add_argument("--attempt", required=True, type=int)
    usage.add_argument("--builder", default="claude-code")
    usage.add_argument("--effort", default=None)
    usage.add_argument("--commit", required=True)
    usage.add_argument("--delivery-artifact")

    for command in (init, check, status, usage):
        command.add_argument("--pretty", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    if args.command == "init":
        return scaffold(root, args.project_id, args.repository, args.mode, args.platform, args.branch, apply=args.apply)
    report, runtime = verify(root)
    if args.command == "check":
        return report
    if args.command == "status":
        report["next_ready"] = runtime.ready_nodes()
        report["usage"] = usage_totals(runtime)
        return report
    if args.command == "record-run":
        return record_result(
            runtime, node=args.node, actor=args.actor,
            result_path=Path(args.result_file), attempt=args.attempt,
            builder=args.builder, effort=args.effort,
            commit=args.commit, delivery_artifact=args.delivery_artifact,
        )
    raise ValidationError(f"unsupported command {args.command}")


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    try:
        result = run(arguments)
        pretty = "--pretty" in arguments
        print(json.dumps(result, sort_keys=True, indent=2 if pretty else None))
        return 0
    except (ValidationError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
