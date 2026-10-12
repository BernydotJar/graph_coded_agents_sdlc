"""Original, non-destructive project contracts for governed coded-agent delivery.

Graph Harness is the authoritative execution kernel. This module only builds
project-specific governance artifacts and never creates a UiPath runtime project.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from graph_harness.model import ProjectDefinition, ValidationError
from graph_harness.policy import PolicyLayer

SCHEMA = "coded-agents.control.v1"
PLATFORMS = ("generic", "uipath-rpa", "uipath-coded-agent")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_settings(project_id: str, repository: str, mode: str, platform: str, branch: str | None) -> None:
    if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
        raise ValidationError("project_id must be 2-128 safe characters (letters, digits, ., _, -)")
    if not isinstance(repository, str) or not _REPO.fullmatch(repository) or ".." in repository or repository.startswith(("-", ".")):
        raise ValidationError("repository must be a valid owner/repo slug, never a URL with credentials")
    if mode not in ("MVP", "SHIP"):
        raise ValidationError("mode must be MVP or SHIP")
    if platform not in PLATFORMS:
        raise ValidationError(f"platform must be one of {', '.join(PLATFORMS)}")
    if branch is not None and (not isinstance(branch, str) or not branch or branch.startswith("-") or any(c.isspace() for c in branch)):
        raise ValidationError("branch must be a non-empty Git branch without whitespace")


def _gate(id: str, *kinds: str) -> dict[str, Any]:
    return {"id": id, "required_evidence_kinds": list(kinds), "blocking": True}


def _node(id: str, title: str, status: str, dependencies: list[str], gates: dict[str, list[str]], role: str) -> dict[str, Any]:
    return {
        "id": id,
        "kind": "delivery-control",
        "title": title,
        "status": status,
        "depends_on": dependencies,
        "capability": role,
        "gates": gates,
        "allowed_paths": [],
        "metadata": {"assigned_role": role, "scope_writes_require_explicit_authorization": True},
    }


def graph_definition(project_id: str, mode: str, platform: str) -> dict[str, Any]:
    gates = [
        _gate("identity", "identity_preflight"),
        _gate("scope", "scope_contract"),
        _gate("spec", "requirements", "design"),
        _gate("producer", "build_result"),
        _gate("critic", "critic_review"),
        _gate("fixer", "fixer_resolution"),
        _gate("independent", "independent_verification"),
        _gate("release", "release_authorization"),
    ]
    verify_gates = ["independent"]
    if platform == "uipath-rpa":
        gates.append(_gate("windows-runtime", "windows_runtime"))
        verify_gates.append("windows-runtime")
    elif platform == "uipath-coded-agent":
        gates.append(_gate("coded-agent-runtime", "coded_agent_runtime"))
        verify_gates.append("coded-agent-runtime")
    release_gates = ["release"]
    if mode == "SHIP":
        gates.append(_gate("deployment-readback", "deployment_readback"))
        release_gates.append("deployment-readback")
    nodes = [
        _node("GOV-IDENTITY", "Verify repository and execution identity", "approved", [], {"done": ["identity"]}, "identity-verifier"),
        _node("GOV-SCOPE", "Approve scope and execution authority", "spec_ready", ["GOV-IDENTITY"], {"approved": ["scope"], "done": ["scope"]}, "human-approver"),
        _node("SPEC-DELIVERY", "Specify requirements and acceptance contract", "pending", ["GOV-SCOPE"], {"review": ["spec"], "done": ["spec"]}, "spec-author"),
        _node("DEV-PRODUCER", "Implement the scoped slice", "pending", ["SPEC-DELIVERY"], {"review": ["producer"], "done": ["producer"]}, "producer"),
        _node("REVIEW-CRITIC", "Adversarial and contract review", "pending", ["DEV-PRODUCER"], {"done": ["critic"]}, "critic"),
        _node("DEV-FIXER", "Resolve critic findings or document no-op", "pending", ["REVIEW-CRITIC"], {"done": ["fixer"]}, "fixer"),
        _node("VERIFY-INDEPENDENT", "Independent verification and platform runtime evidence", "pending", ["DEV-FIXER"], {"done": verify_gates}, "independent-verifier"),
        _node("RELEASE-GATE", "Human release decision and deployment readback", "pending", ["VERIFY-INDEPENDENT"], {"done": release_gates}, "release-manager"),
    ]
    payload = {"schema_version": "graph-harness.project.v1", "project_id": project_id, "mode": mode, "gate_definitions": gates, "nodes": nodes}
    ProjectDefinition.from_mapping(payload)
    return payload


def policy_definition() -> dict[str, Any]:
    payload = {
        "schema_version": "graph-harness.policy.v1",
        "scope": "project",
        "safety": {
            "deny_command_patterns": [
                r"(?i)\bgit\s+push\b[^\n]*\s--force\b",
                r"(?i)\bgit\s+reset\s+--hard\b",
            ],
            "warn_command_patterns": [],
            "deny_path_patterns": ["**/.env", "**/.env.*", "**/.claude/.credentials.json", "**/secrets/**"],
            "approval_required_patterns": [
                r"(?i)\bgit\s+push\b",
                r"(?i)\buip\s+(?:rpa\s+)?(?:publish|deploy|pack)\b",
                r"(?i)\b(?:terraform|tofu)\s+apply\b",
                r"(?i)\bkubectl\s+apply\b",
            ],
            "secret_patterns": [],
        },
        "preferences": {"verification_style": "evidence-first"},
    }
    PolicyLayer.from_mapping(payload)
    return payload


def starter_files(project_id: str, repository: str, mode: str, platform: str, branch: str | None) -> dict[str, str]:
    validate_settings(project_id, repository, mode, platform, branch)
    identity: dict[str, Any] = {"repository": repository}
    if branch is not None:
        identity["branch"] = branch
    preflight = {
        "schema_version": "graph-harness.preflight.v1",
        "identity": identity,
        "environment": {"python": ">=3.11", "require_commands": ["git"]},
    }
    manifest = {
        "schema_version": SCHEMA,
        "project_id": project_id,
        "repository": repository,
        "branch": branch,
        "mode": mode,
        "platform": platform,
        "graph_project": ".coded-agents/graph-project.json",
        "event_ledger": ".coded-agents/events.jsonl",
        "policy": ".coded-agents/policy.json",
        "preflight": ".coded-agents/expected-identity.json",
    }
    notes = (
        "# Coded Agents delivery contract\n\n"
        "This is governance metadata, not a replacement for native platform projects.\n"
        "Use the Graph Harness CLI for state transitions, evidence, and gate evaluations.\n"
        "Never treat a green static check as runtime evidence. For UiPath RPA,\n"
        "independent Windows Studio/Robot runtime evidence is a required gate.\n"
        "A release action requires separate explicit human authority and post-action readback.\n"
        "Do not store credentials, private prompts, or customer data in the event ledger.\n"
    )
    agents = (
        "# Coded Agents project instructions\n\n"
        f"Project identity: `{project_id}` (`{repository}`).\n"
        "Before modifying a repository, run `coded-agents-sdlc check --root .`.\n"
        "Follow `.coded-agents/graph-project.json` and the append-only event ledger;\n"
        "never bypass an approval, independent verification, or release gate.\n"
        "Use Graph Harness policy checks before external side effects.\n"
        "Use official product tooling for project generation and preserve existing work.\n"
        "Do not publish, deploy, change cloud infrastructure, or spend funds without explicit authorization.\n"
        "Keep builder model, runtime platform, and evidence level separately identified.\n"
    )
    def pretty(data: dict[str, Any]) -> str:
        return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return {
        ".coded-agents/project.json": pretty(manifest),
        ".coded-agents/graph-project.json": pretty(graph_definition(project_id, mode, platform)),
        ".coded-agents/expected-identity.json": pretty(preflight),
        ".coded-agents/policy.json": pretty(policy_definition()),
        ".coded-agents/README.md": notes,
        "AGENTS.md": agents,
    }


def read_manifest(root: Path) -> dict[str, Any]:
    path = root / ".coded-agents/project.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValidationError(f"missing/invalid contract {path}: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
        raise ValidationError("invalid coded-agent project contract schema")
    validate_settings(manifest.get("project_id"), manifest.get("repository"), manifest.get("mode"), manifest.get("platform"), manifest.get("branch"))
    expected_files = {
        "graph_project": ".coded-agents/graph-project.json",
        "event_ledger": ".coded-agents/events.jsonl",
        "policy": ".coded-agents/policy.json",
        "preflight": ".coded-agents/expected-identity.json",
    }
    for key, value in expected_files.items():
        if manifest.get(key) != value:
            raise ValidationError(f"contract {key} must be {value!r}")
    return manifest
