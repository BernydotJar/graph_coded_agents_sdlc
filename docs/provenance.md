# Provenance and license

Graph Coded Agents SDLC is maintained as an independent open-source project.

## Public Graph Harness SDLC baseline

The execution runtime, policy/control-plane primitives, graph schemas, tests, and selected supporting documentation originate in the publicly licensed [Graph Harness SDLC](https://github.com/BernydotJar/Graph-harness-sdlc) repository at commit `168b740045293089720964bdc0d2bda79828b5c8` (MIT). The upstream [MIT LICENSE](../LICENSE) is preserved here. The [integrity manifest](upstream-manifest.json) records a SHA-256 digest for every byte-identical imported upstream file.

## Coded Agents integration

The `coded_agents_sdlc/` Python package, Coded Agents tests, project onboarding instructions, and UiPath integration documentation are original extensions built with the public Graph Harness interfaces. Some imported MIT documentation was editorially updated to describe this project; those changed files are not claimed to be byte-identical in the upstream manifest.

Review repository identity, licensing, the manifest and the full diff before any future synchronization. The graph execution engine remains the source of truth for approvals, state transitions, evidence hashes and localized repair.
