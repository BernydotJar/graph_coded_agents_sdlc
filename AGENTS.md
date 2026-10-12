# Graph Coded Agents SDLC engineering contract

This repo is NOT a customer project. `graph_harness/` is the MIT-licensed upstream execution kernel; `coded_agents_sdlc/` is an independently written adapter. Keep the kernel's event integrity, approvals and revision semantics authoritative, and implement new product adapters outside the kernel.

Before changing code, verify repository Git root, owner/remote, current branch, HEAD and dirty state. Never route a task into an unrelated project, discard uncommitted work, or force-push. Only publish changes through reviewed, authorized operations.

Do not import or adapt any proprietary/confidential source files, hooks or templates into this public repository. License and provenance must remain auditable.

Use the lifecycle: scope → spec → Producer → Critic → Fixer → Independent Verifier → Release Gate → persistent evidence. Treat static XML, package compilation, Windows Robot execution and hosted readback as distinct proof levels.

Quality gate: run `python3 -m unittest discover -s tests -v`, `git diff --check`, and CLI identity/preflight smoke tests. Fail closed on wrong repo, branch or missing authorization. For UiPath, use the official UiPath CLI and skills for product scaffolding; never hand-author platform-generated configuration or claim native execution without runtime evidence.
