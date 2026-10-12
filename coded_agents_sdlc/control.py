"""Read-only verification and explicit, non-overwriting scaffold application."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from graph_harness.bootstrap.preflight import run_preflight
from graph_harness.model import EventType, NodeStatus, ProjectDefinition, ValidationError
from graph_harness.policy import PolicyLayer
from graph_harness.runtime import GraphRuntime

from .project import graph_definition, read_manifest, starter_files


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, text=True,
        check=False, timeout=10,
    )
    if result.returncode:
        raise ValidationError("repository identity not available; initialize Git and set a GitHub origin first")
    return result.stdout.strip()


def _origin_slug(origin: str) -> str:
    if origin.startswith("git@github.com:"):
        path = origin.split(":", 1)[1]
    else:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.query:
            raise ValidationError("origin must be a credential-free github.com HTTPS or SSH remote")
        path = parsed.path
    slug = path.strip("/").removesuffix(".git")
    if len(slug.split("/")) != 2:
        raise ValidationError("origin must identify exactly owner/repository")
    return slug


def assert_identity(root: Path, repository: str, branch: str | None) -> dict[str, Any]:
    root = root.resolve(strict=True)
    git_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if git_root != root:
        raise ValidationError(f"project identity violation: root {root} is nested under repository {git_root}")
    origin = _git(root, "remote", "get-url", "origin")
    actual = _origin_slug(origin)
    if actual.lower() != repository.lower():
        raise ValidationError(f"repository identity violation: expected {repository!r}, found {actual!r}")
    current_branch = _git(root, "branch", "--show-current")
    if branch is not None and current_branch != branch:
        raise ValidationError(f"branch identity violation: expected {branch!r}, found {current_branch!r}")
    return {"git_root": str(git_root), "repository": actual, "branch": current_branch, "head": _git(root, "rev-parse", "HEAD")}


def scaffold(root: Path, project_id: str, repository: str, mode: str, platform: str, branch: str | None, *, apply: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=False)
    if not root.is_dir():
        raise ValidationError(f"root must already exist: {root}")
    generated = starter_files(project_id, repository, mode, platform, branch)
    # No writes before the repository/branch identity gate. Dry runs may be used
    # to preview a new project before its Git remote has been configured.
    identity = assert_identity(root, repository, branch) if apply else None
    actions = []
    conflicts = []
    for relative, content in generated.items():
        destination = root / relative
        if destination.is_symlink():
            raise ValidationError(f"refusing to follow a symlink in scaffold target: {relative}")
        if not destination.exists():
            action = "create"
        elif not destination.is_file():
            action = "conflict"
        elif destination.read_text(encoding="utf-8") == content:
            action = "unchanged"
        elif relative == "AGENTS.md":
            action = "preserve-existing-instructions"
        else:
            action = "conflict"
        if action == "conflict":
            conflicts.append(relative)
        actions.append({"file": relative, "action": action})
    if apply and conflicts:
        raise ValidationError(f"existing governance contract conflicts: {conflicts}; no files written")
    if apply:
        for entry in actions:
            if entry["action"] == "create":
                target = root / entry["file"]
                # Guard existing directories against symlink redirection.
                relative_parent = target.parent.relative_to(root)
                current = root
                for part in relative_parent.parts:
                    current = current / part
                    if current.is_symlink():
                        raise ValidationError(f"refusing symlink parent in scaffold: {entry['file']}")
                    current.mkdir(exist_ok=True)
                with target.open("x", encoding="utf-8") as handle:
                    handle.write(generated[entry["file"]])
    return {"schema_version": "coded-agents.scaffold-plan.v1", "root": str(root), "dry_run": not apply, "identity": identity, "actions": actions, "conflicts": conflicts}


def verify(root: Path) -> tuple[dict[str, Any], GraphRuntime]:
    root = root.expanduser().resolve(strict=True)
    contract_dir = root / ".coded-agents"
    if contract_dir.is_symlink() or not contract_dir.is_dir():
        raise ValidationError("governance directory must exist and cannot be a symlink")
    for contract in ("project.json", "graph-project.json", "expected-identity.json", "policy.json", "events.jsonl"):
        if (contract_dir / contract).is_symlink():
            raise ValidationError(f"governance path cannot be a symlink: {contract}")
    manifest = read_manifest(root)
    identity = assert_identity(root, manifest["repository"], manifest["branch"])
    expected_graph = graph_definition(manifest["project_id"], manifest["mode"], manifest["platform"])
    graph_path = root / manifest["graph_project"]
    loaded = ProjectDefinition.from_path(graph_path)
    if json.loads(graph_path.read_text(encoding="utf-8")) != expected_graph:
        raise ValidationError("graph contract has drifted from the approved platform/mode template; review before proceeding")
    runtime = GraphRuntime.from_paths(graph_path, root / manifest["event_ledger"])
    state = runtime.state()  # verifies project identity, event revisions and hash chain
    _verify_actor_separation(state)
    policy = PolicyLayer.from_path(root / manifest["policy"])
    if policy.scope != "project":
        raise ValidationError("coded-agent policy must be scoped to project")
    expectation_file = root / manifest["preflight"]
    expect = json.loads(expectation_file.read_text(encoding="utf-8"))
    if expect.get("identity", {}).get("repository") != manifest["repository"] or expect.get("identity", {}).get("branch") != manifest["branch"]:
        if not (manifest["branch"] is None and "branch" not in expect.get("identity", {})):
            raise ValidationError("preflight expectation and project manifest have diverged")
    preflight = run_preflight(root, expectations_path=expectation_file)
    if not preflight.ok:
        raise ValidationError("identity/environment preflight failed: " + "; ".join(f.code for f in preflight.findings if f.level == "error"))
    result = {
        "schema_version": "coded-agents.check.v1",
        "ok": True,
        "project_id": manifest["project_id"],
        "platform": manifest["platform"],
        "mode": manifest["mode"],
        "repository": identity["repository"],
        "branch": identity["branch"],
        "head": identity["head"],
        "nodes": {key: value.status.value for key, value in state.nodes.items()},
        "event_count": len(state.events),
    }
    return result, runtime


def _verify_actor_separation(state: Any) -> None:
    """Semantic independence gate on top of Graph Harness evidence/kind checks.

    Actor labels do not prove human identity; organizational SSO/attestation must
    be layered separately before treating this as production identity assurance.
    """
    if state.nodes["VERIFY-INDEPENDENT"].status is not NodeStatus.DONE:
        return
    kinds_by_node = {
        "DEV-PRODUCER": "build_result",
        "REVIEW-CRITIC": "critic_review",
        "DEV-FIXER": "fixer_resolution",
        "VERIFY-INDEPENDENT": "independent_verification",
    }
    actors: dict[str, set[str]] = {node: set() for node in kinds_by_node}
    for event in state.events:
        if (event.event_type is EventType.EVIDENCE_RECORDED
                and event.node_id in kinds_by_node
                and event.payload.get("kind") == kinds_by_node[event.node_id]
                and event.payload.get("result", "").upper() in ("PASS", "SUCCESS")):
            # Only compare evidence attached to the current revision of its node.
            if event.node_revision == state.nodes[event.node_id].revision:
                actors[event.node_id].add(event.actor)
    if not actors["VERIFY-INDEPENDENT"]:
        raise ValidationError("independent verifier has no current-revision identity evidence")
    for implementer in ("DEV-PRODUCER", "REVIEW-CRITIC", "DEV-FIXER"):
        if actors[implementer] & actors["VERIFY-INDEPENDENT"]:
            raise ValidationError("verifier identity matches a producer/critic/fixer; independent verification is not independent")
