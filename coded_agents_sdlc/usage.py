"""Import builder usage into the Graph Harness evidence ledger, preserving failures.

Only numeric aggregate fields are imported. Raw prompts, responses, API keys,
credentials, and account identity never enter the ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from graph_harness.model import EventType, ValidationError
from graph_harness.runtime import GraphRuntime


def _counter(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValidationError(f"{label} must be a non-negative integer")
    return value


def _amount(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(float(value)) or value < 0:
        raise ValidationError(f"{label} must be a finite non-negative number")
    return float(value)


def summarize_result(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("builder result must be a JSON object")
    if type(raw.get("is_error")) is not bool:
        raise ValidationError("builder result must explicitly report is_error true or false")
    model_usage = raw.get("modelUsage", {})
    if not isinstance(model_usage, dict):
        raise ValidationError("modelUsage must be an object when supplied")
    usage = raw.get("usage", {})
    if not isinstance(usage, dict):
        raise ValidationError("usage must be an object when supplied")
    primary = None
    primary_cost = -1.0
    for name, value in model_usage.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ValidationError("modelUsage entries must be named objects")
        cost = _amount(value.get("costUSD"), "modelUsage.costUSD")
        if cost is not None and cost > primary_cost:
            primary, primary_cost = name, cost

    tokens = {
        "input_tokens": _counter(usage.get("input_tokens"), "input_tokens"),
        "output_tokens": _counter(usage.get("output_tokens"), "output_tokens"),
        "cache_read_tokens": _counter(usage.get("cache_read_input_tokens"), "cache_read_input_tokens"),
        "cache_creation_tokens": _counter(usage.get("cache_creation_input_tokens"), "cache_creation_input_tokens"),
    }
    details = usage.get("output_tokens_details", {}) or {}
    if not isinstance(details, dict):
        raise ValidationError("output_tokens_details must be an object")
    tokens["thinking_tokens"] = _counter(details.get("thinking_tokens"), "thinking_tokens")
    if not usage and model_usage:
        names = {
            "input_tokens": "inputTokens", "output_tokens": "outputTokens",
            "cache_read_tokens": "cacheReadInputTokens",
            "cache_creation_tokens": "cacheCreationInputTokens",
            "thinking_tokens": "thinkingTokens",
        }
        for key, source in names.items():
            values = [_counter(value.get(source), f"modelUsage.{source}") for value in model_usage.values()]
            if any(value is not None for value in values):
                tokens[key] = sum(value or 0 for value in values)
    if tokens["thinking_tokens"] is not None and tokens["output_tokens"] is not None and tokens["thinking_tokens"] > tokens["output_tokens"]:
        raise ValidationError("thinking tokens are a subset of output tokens, not an additional category")
    total_cost = _amount(raw.get("total_cost_usd"), "total_cost_usd")
    if total_cost is None and model_usage and all("costUSD" in value for value in model_usage.values()):
        total_cost = round(sum(_amount(value["costUSD"], "modelUsage.costUSD") or 0 for value in model_usage.values()), 8)
    return {
        "outcome": "FAIL" if raw["is_error"] else "PASS",
        "model": primary,
        "reported_cost_usd": total_cost,
        "duration_ms": _counter(raw.get("duration_ms"), "duration_ms"),
        "turns": _counter(raw.get("num_turns"), "num_turns"),
        **tokens,
    }


def record_result(
    runtime: GraphRuntime, *, node: str, actor: str, result_path: Path,
    attempt: int, builder: str, effort: str | None, commit: str,
    delivery_artifact: str | None = None,
) -> dict[str, Any]:
    if attempt < 1 or type(attempt) is not int:
        raise ValidationError("attempt must be a positive integer")
    if not actor or not builder or not commit or any("\n" in text for text in (actor, builder, commit)):
        raise ValidationError("actor, builder, commit must be non-empty single-line values")
    if effort and (len(effort) > 60 or "\n" in effort):
        raise ValidationError("effort must be a short single-line label")
    try:
        contents = result_path.read_bytes()
        raw = json.loads(contents)
    except (OSError, ValueError) as error:
        raise ValidationError(f"invalid builder result: {error}") from error
    digest = hashlib.sha256(contents).hexdigest()
    summary = summarize_result(raw)
    state = runtime.state()
    if node not in state.nodes:
        raise ValidationError(f"node {node!r} not present in this project graph")
    for event in state.events:
        if event.event_type is EventType.EVIDENCE_RECORDED and event.payload.get("kind") == "builder_run":
            if event.payload.get("sha256") == digest:
                raise ValidationError("builder result already recorded; refusing to count the same run twice")
            if event.node_id == node and event.payload.get("metadata", {}).get("attempt") == attempt:
                raise ValidationError("attempt already recorded for this node; use the next attempt number")
    metadata = {"schema_version": "coded-agents.builder-usage.v1", "attempt": attempt, "builder": builder, "effort": effort, **summary}
    if delivery_artifact:
        if len(delivery_artifact) > 1024 or any(ord(c) < 32 for c in delivery_artifact):
            raise ValidationError("delivery artifact must be a safe single-line label/path")
        metadata["delivery_artifact"] = delivery_artifact
    event = runtime.record_evidence(
        node, actor=actor, kind="builder_run", result=summary["outcome"],
        artifact=result_path.name, sha256=digest,
        command="coded-agents-sdlc record-run (aggregate-only)", commit=commit,
        metadata=metadata,
    )
    return {"evidence_id": event.event_id, "node": node, "attempt": attempt, "summary": summary}


def usage_totals(runtime: GraphRuntime) -> dict[str, Any]:
    keys = ("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens", "cache_creation_tokens")
    totals: dict[str, Any] = {"attempts": 0, "failed_attempts": 0, "known_cost_attempts": 0, "reported_cost_usd": 0.0}
    totals.update({key: 0 for key in keys})
    for event in runtime.state().events:
        if event.event_type is not EventType.EVIDENCE_RECORDED or event.payload.get("kind") != "builder_run":
            continue
        metadata = event.payload.get("metadata") or {}
        totals["attempts"] += 1
        if event.payload.get("result") != "PASS":
            totals["failed_attempts"] += 1
        if metadata.get("reported_cost_usd") is not None:
            totals["known_cost_attempts"] += 1
            totals["reported_cost_usd"] += metadata["reported_cost_usd"]
        for key in keys:
            totals[key] += metadata.get(key) or 0
    totals["reported_cost_usd"] = round(totals["reported_cost_usd"], 6)
    totals["thinking_tokens_are_subset_of_output"] = True
    totals["cost_represents_reported_builder_estimate_not_invoice"] = True
    return totals
