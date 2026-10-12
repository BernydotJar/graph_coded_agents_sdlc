# UiPath-specific runtime evidence

The framework supports two distinct platforms. The `uipath-rpa` product is a Studio Process/Library project containing XAML; proof requires Windows Studio/Robot execution. The `uipath-coded-agent` product is a native SDK-based UiPath Coded Agent; proof requires its own runtime/evaluation run. Their governance is shared but deployment formats and tests are **not** interchangeable.

The `coded-agents-sdlc init` command creates only governance metadata, not a deployable UiPath project. Use the current official UiPath skills and `uip` CLI to scaffold platform-owned files. Do **not** synthesize `bindings.json`, hand-author generated manifests, or claim a Coded Agent merely because a folder exists.

For Windows RPA verification: open `project.json` in Studio; restore dependencies; run native validation and compilation; execute both happy and forced-failure paths in Robot; record exact Windows/Studio/Robot versions, command output, project SHA, artifact hash, and the independent verifier's identity; and avoid modifying a real tenant. A Linux ARM64 XML-parser pass is not a `windows_runtime` PASS.

For Coded Agent verification: preserve the chosen official framework, regenerate SDK-derived bindings, execute its smoke evaluation set, verify actual runtime behavior, and record the results as `coded_agent_runtime`. Publish/deploy only with separate explicit authority and destination readback. MVP can complete without live deployment; SHIP requires a distinct `deployment_readback` gate.

Use Graph Harness `record-evidence`, `evaluate-gate` and `transition` to capture proofs and close gates. If a runtime check fails, preserve failure evidence and enter localized repair rather than overwriting a previous successful record.
