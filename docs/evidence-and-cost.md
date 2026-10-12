# Model usage and independent delivery evidence

`record-run` reads a local Claude Code compatible JSON result, validates numeric token/cost fields, calculates the raw result's SHA-256, and appends only metadata to the hashed Graph Harness event ledger. It **does not** store the prompt, full model response, credentials, customer data or raw result file. Every attempt gets an explicit positive attempt number, and duplicate data/attempts are rejected.

The ledger distinguishes direct input tokens, output tokens, cache-read tokens, cache-creation tokens and thinking tokens. **Thinking tokens are included within output tokens**, not added to them. Provider-reported USD figures are estimates, not reconciled invoices. All attempts — successful or failed, including quota errors — count toward totals. `known_cost_attempts` signals whether some costs were not supplied.

Run `python3 -m coded_agents_sdlc status --root /path/to/project --pretty` for all-attempt totals. Keep an external workbook or dashboard as a reporting projection if needed; it must not replace the append-only evidence store or turn a partially verified build into a runtime success.

The independent verification graph gate is different from the builder's usage event. A compiled package or `uip` command return code is not automatically Windows Robot, agent runtime, deployed tenant, or user acceptance evidence.
