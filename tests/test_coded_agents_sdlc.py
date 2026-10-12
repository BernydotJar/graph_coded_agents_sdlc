"""Independent contract tests for the original coded-agent integration layer."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from coded_agents_sdlc.cli import main
from coded_agents_sdlc.control import assert_identity, scaffold, verify
from coded_agents_sdlc.project import graph_definition, policy_definition
from coded_agents_sdlc.usage import record_result, summarize_result, usage_totals
from graph_harness.model import ProjectDefinition, ValidationError
from graph_harness.policy import ActionRequest, Decision, PolicyLayer, evaluate_action, resolve_policy


class CodedAgentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.repo = "ExampleOrg/graph-test-project"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "seed.txt"], check=True)
        env = {**os.environ, "GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "seed"], env=env, check=True)
        subprocess.run(["git", "-C", str(self.root), "remote", "add", "origin", "https://github.com/ExampleOrg/graph-test-project.git"], check=True)

    def _apply(self, platform: str = "generic", mode: str = "MVP"):
        return scaffold(self.root, "my-eval", self.repo, mode, platform, "main", apply=True)

    def test_dry_run_no_writes(self):
        initial = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if ".git" not in p.parts)
        plan = scaffold(self.root, "my-eval", self.repo, "MVP", "generic", "main")
        after = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if ".git" not in p.parts)
        self.assertTrue(plan["dry_run"])
        self.assertEqual(initial, after)
        self.assertEqual(6, len(plan["actions"]))

    def test_apply_is_idempotent_and_tracks_clean_graph(self):
        first = self._apply()
        second = self._apply()
        self.assertEqual(6, sum(a["action"] == "create" for a in first["actions"]))
        self.assertTrue(all(a["action"] == "unchanged" for a in second["actions"]))
        result, runtime = verify(self.root)
        self.assertTrue(result["ok"])
        self.assertEqual("my-eval", result["project_id"])
        self.assertEqual(8, len(result["nodes"]))
        self.assertEqual(["GOV-IDENTITY"], runtime.ready_nodes())

    def test_preserves_existing_project_instructions(self):
        content = "# Our own AGENTS.md\n"
        (self.root / "AGENTS.md").write_text(content)
        plan = self._apply()
        self.assertIn("preserve-existing-instructions", [a["action"] for a in plan["actions"]])
        self.assertEqual(content, (self.root / "AGENTS.md").read_text())
        self.assertTrue(verify(self.root)[0]["ok"])

    def test_existing_contract_conflict_is_atomic(self):
        folder = self.root / ".coded-agents"
        folder.mkdir()
        (folder / "policy.json").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "no files written"):
            self._apply()
        self.assertEqual("keep", (folder / "policy.json").read_text())
        self.assertFalse((folder / "project.json").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_fail_closed_on_repository_identity_mismatch(self):
        with self.assertRaisesRegex(ValidationError, "repository identity violation"):
            scaffold(self.root, "my-eval", "OtherOrg/other-repo", "MVP", "generic", "main", apply=True)
        self.assertFalse((self.root / ".coded-agents").exists())

    def test_fail_closed_on_branch_identity_mismatch(self):
        with self.assertRaisesRegex(ValidationError, "branch identity violation"):
            scaffold(self.root, "my-eval", self.repo, "MVP", "generic", "wrong-branch", apply=True)
        self.assertFalse((self.root / ".coded-agents").exists())

    def test_nested_git_root_is_rejected(self):
        child = self.root / "child"
        child.mkdir()
        with self.assertRaisesRegex(ValidationError, "nested under repository"):
            scaffold(child, "my-eval", self.repo, "MVP", "generic", "main", apply=True)

    def test_symlink_parent_denied(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / ".coded-agents").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, "symlink"):
            self._apply()
        self.assertEqual([], list(outside.iterdir()))

    def test_tampered_manifest_detected(self):
        self._apply()
        manifest_file = self.root / ".coded-agents" / "project.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["repository"] = "OtherOrg/elsewhere"
        manifest_file.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValidationError, "identity violation"):
            verify(self.root)

    def test_tampered_graph_detected(self):
        self._apply()
        graph_file = self.root / ".coded-agents" / "graph-project.json"
        graph = json.loads(graph_file.read_text())
        graph["nodes"][-1]["depends_on"] = ["GOV-IDENTITY"]
        graph_file.write_text(json.dumps(graph))
        with self.assertRaisesRegex(ValidationError, "graph contract has drifted"):
            verify(self.root)

    def test_platform_gates_and_dependency_order(self):
        graph = graph_definition("my-eval", "SHIP", "uipath-rpa")
        self.assertEqual("graph-harness.project.v1", graph["schema_version"])
        ids = [n["id"] for n in graph["nodes"]]
        self.assertEqual(["GOV-IDENTITY", "GOV-SCOPE", "SPEC-DELIVERY", "DEV-PRODUCER", "REVIEW-CRITIC", "DEV-FIXER", "VERIFY-INDEPENDENT", "RELEASE-GATE"], ids)
        self.assertEqual(["DEV-FIXER"], graph["nodes"][6]["depends_on"])
        self.assertEqual(["independent", "windows-runtime"], graph["nodes"][6]["gates"]["done"])
        self.assertEqual(["release", "deployment-readback"], graph["nodes"][7]["gates"]["done"])
        self.assertEqual(["independent", "coded-agent-runtime"], graph_definition("my-eval", "MVP", "uipath-coded-agent")["nodes"][6]["gates"]["done"])
        ProjectDefinition.from_mapping(graph)

    def test_safety_policy_approval_cannot_override_absolute_deny(self):
        layer = PolicyLayer.from_mapping(policy_definition())
        policy = resolve_policy((layer,))
        blocked = evaluate_action(policy, ActionRequest(command="git reset --hard", approved=True))
        self.assertEqual(Decision.DENY, blocked.decision)
        guarded = evaluate_action(policy, ActionRequest(command="git push origin main", approved=False))
        self.assertEqual(Decision.DENY, guarded.decision)
        permitted = evaluate_action(policy, ActionRequest(command="git push origin feat/approved", approved=True))
        self.assertEqual(Decision.ALLOW, permitted.decision)

    def test_usage_record_success_failure_and_no_raw_secret(self):
        self._apply()
        report, runtime = verify(self.root)
        success = {
            "is_error": False, "duration_ms": 12340, "num_turns": 4,
            "total_cost_usd": 2.125,
            "modelUsage": {"claude-eval-model": {"costUSD": 2.125}},
            "usage": {"input_tokens": 100, "output_tokens": 300,
                       "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 400,
                       "output_tokens_details": {"thinking_tokens": 70}},
            "result": "PRIVATE PROMPT AND SECRET PASSWORD MUST NEVER BE IN THE LEDGER",
        }
        f1 = self.root / "run-1.json"
        f1.write_text(json.dumps(success))
        receipt = record_result(runtime, node="DEV-PRODUCER", actor="builder", result_path=f1, attempt=1, builder="claude-code", effort="xhigh", commit="abc")
        self.assertEqual("PASS", receipt["summary"]["outcome"])
        failure = {**success, "is_error": True, "total_cost_usd": 0.5, "num_turns": 2}
        f2 = self.root / "run-2.json"
        f2.write_text(json.dumps(failure))
        receipt = record_result(runtime, node="DEV-PRODUCER", actor="builder", result_path=f2, attempt=2, builder="claude-code", effort="xhigh", commit="abc")
        self.assertEqual("FAIL", receipt["summary"]["outcome"])
        totals = usage_totals(runtime)
        self.assertEqual(2, totals["attempts"])
        self.assertEqual(1, totals["failed_attempts"])
        self.assertAlmostEqual(2.625, totals["reported_cost_usd"])
        self.assertEqual(600, totals["output_tokens"])
        self.assertEqual(140, totals["thinking_tokens"])
        ledger = (self.root / ".coded-agents" / "events.jsonl").read_text()
        self.assertNotIn("PRIVATE PROMPT", ledger)
        self.assertNotIn("SECRET PASSWORD", ledger)
        self.assertIn('"builder_run"', ledger)
        with self.assertRaisesRegex(ValidationError, "already recorded"):
            record_result(runtime, node="DEV-PRODUCER", actor="builder", result_path=f2, attempt=2, builder="claude-code", effort="xhigh", commit="abc")
        self.assertTrue(verify(self.root)[0]["ok"])

    def test_tokens_cannot_double_count_thinking(self):
        with self.assertRaisesRegex(ValidationError, "subset of output tokens"):
            summarize_result({"is_error": False, "usage": {"output_tokens": 1, "output_tokens_details": {"thinking_tokens": 2}}})

    def test_malformed_settings_rejected_without_file_writes(self):
        with self.assertRaises(ValidationError):
            scaffold(self.root, "../../../escape", self.repo, "MVP", "generic", "main", apply=True)
        self.assertFalse((self.root / ".coded-agents").exists())

    def test_cli_dry_run_and_check(self):
        self.assertEqual(0, main(["init", "--root", str(self.root), "--project-id", "my-eval", "--repository", self.repo, "--branch", "main"]))
        self.assertEqual(0, main(["init", "--root", str(self.root), "--project-id", "my-eval", "--repository", self.repo, "--branch", "main", "--apply"]))
        self.assertEqual(0, main(["check", "--root", str(self.root)]))
        self.assertEqual(0, main(["status", "--root", str(self.root)]))


if __name__ == "__main__":
    unittest.main()

# Additional regression checks for the public control-plane adapter.
from types import SimpleNamespace
from graph_harness.model import EventType, NodeStatus
from coded_agents_sdlc.control import _verify_actor_separation


class VerifierIdentityTests(unittest.TestCase):
    def _state(self, verifier_actor: str):
        def evidence(node, kind, actor):
            return SimpleNamespace(
                event_type=EventType.EVIDENCE_RECORDED, node_id=node, actor=actor,
                node_revision=0, payload={"kind": kind, "result": "PASS"},
            )
        nodes = {
            name: SimpleNamespace(status=NodeStatus.DONE, revision=0)
            for name in ("DEV-PRODUCER", "REVIEW-CRITIC", "DEV-FIXER", "VERIFY-INDEPENDENT")
        }
        events = [
            evidence("DEV-PRODUCER", "build_result", "producer"),
            evidence("REVIEW-CRITIC", "critic_review", "critic"),
            evidence("DEV-FIXER", "fixer_resolution", "fixer"),
            evidence("VERIFY-INDEPENDENT", "independent_verification", verifier_actor),
        ]
        return SimpleNamespace(nodes=nodes, events=events)

    def test_verifier_cannot_be_the_producer(self):
        with self.assertRaisesRegex(ValidationError, "not independent"):
            _verify_actor_separation(self._state("producer"))

    def test_verifier_cannot_be_critic_or_fixer(self):
        for actor in ("critic", "fixer"):
            with self.subTest(actor=actor):
                with self.assertRaisesRegex(ValidationError, "not independent"):
                    _verify_actor_separation(self._state(actor))

    def test_separate_verifier_actor_passes(self):
        _verify_actor_separation(self._state("external-verifier"))
