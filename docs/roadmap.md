# Product roadmap

## Implemented in v0.1

- Public, MIT Graph Harness SDLC runtime imported at an auditable SHA.
- Original Coded Agents project contract and repo/branch fail-closed identity.
- Safe, idempotent, non-overwriting project governance scaffold.
- Producer -> Critic -> Fixer -> independent verification -> release gates.
- UiPath RPA/Windows and UiPath Coded Agent runtime gates; SHIP readback gate.
- Per-builder-attempt usage and cost accounting, including failed attempts, no raw conversation retention.
- Regression tests, documented provenance, and platform-neutral command-line interface.

## Later (not yet implemented)

- Signed human/agent actor identity and enterprise SSO integration.
- Native UiPath tenant/folder/config/secret adapters with scoped DEV/TEST/PROD permissions.
- Windows Studio automated compiler + smoke-test runner.
- Dynamic graph worker execution with external authorization hooks.
- Excel scorecard/report projections tied to the same Graph evidence hashes.
- Evaluator bundles for DU, migrations, and agentic orchestration.
